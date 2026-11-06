"""Confined EPUB/TXT resource server. ZIPs are read in place, never extracted."""

import html
import json
import mimetypes
import secrets
import threading
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlsplit

from ..i18n import tr


class BookServer:
    def __init__(self, item, position, preferences):
        self.token = secrets.token_urlsafe(32)
        self.item, self.position, self.preferences = item, position, preferences
        self.archive = None
        self.text = None
        self.lock = threading.Lock()
        self.closed = False
        self.entries = {}
        path = Path(item["path"])
        if path.suffix.lower() == ".epub":
            self.archive = zipfile.ZipFile(path)
            infos = self.archive.infolist()
            if len(infos) > 20000 or sum(i.file_size for i in infos) > 1024 * 1024 * 1024:
                self.archive.close()
                raise ValueError(tr("EPUB archive is too large"))
            for info in infos:
                name = info.filename
                if info.is_dir():
                    continue
                if (name.startswith("/") or ".." in PurePosixPath(name).parts
                        or "\\" in name or info.file_size > 64 * 1024 * 1024 or name in self.entries):
                    self.archive.close()
                    raise ValueError(tr("Invalid EPUB archive entry"))
                self.entries[name] = info.file_size
        else:
            if path.stat().st_size > 64 * 1024 * 1024:
                raise ValueError(tr("Text file exceeds 64 MiB"))
            raw = path.read_bytes()
            for encoding in ("utf-8-sig", "utf-16" if raw[:2] in (b"\xff\xfe", b"\xfe\xff") else "utf-8", "gb18030"):
                try:
                    self.text = raw.decode(encoding)
                    break
                except UnicodeError:
                    continue
            if self.text is None:
                raise ValueError(tr("Unsupported text encoding (UTF-8, UTF-16 and GB18030 supported)"))
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                route = unquote(urlsplit(self.path).path)
                prefix = "/" + owner.token + "/"
                if not route.startswith(prefix) or owner.closed:
                    self.send_error(404)
                    return
                try:
                    data, mime, csp = owner.resource(route[len(prefix):])
                except (KeyError, OSError, ValueError, zipfile.BadZipFile):
                    self.send_error(404)
                    return
                self.send_response(200)
                self.send_header("Content-Type", mime)
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Content-Security-Policy", csp)
                self.end_headers()
                try:
                    self.wfile.write(data)
                except (BrokenPipeError, ConnectionResetError):
                    pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.url = f"http://127.0.0.1:{self.server.server_port}/{self.token}/index.html"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def resource(self, route):
        base = Path(__file__).with_name("reader_web")
        csp = ("default-src 'none'; script-src 'nonce-" + self.token + "' 'strict-dynamic'; "
               "style-src 'self' blob: 'unsafe-inline'; img-src 'self' blob: data:; "
               "font-src 'self' blob: data:; connect-src 'self' blob:; frame-src blob:; "
               "object-src 'none'; base-uri 'none'; form-action 'none'")
        if route == "index.html":
            text = (base / "index.html").read_text().replace("@NONCE@", html.escape(self.token))
            return text.encode(), "text/html; charset=utf-8", csp
        if route == "config.json":
            config = {"session": self.token, "format": self.item["format"], "title": self.item["title"],
                      "position": self.position, "preferences": self.preferences, "entries": self.entries}
            return json.dumps(config).encode(), "application/json", csp
        if route == "text.txt" and self.text is not None:
            return self.text.encode(), "text/plain; charset=utf-8", csp
        if route.startswith("book/") and self.archive:
            name = route[5:]
            if name not in self.entries:
                raise KeyError(name)
            with self.lock:
                if self.closed:
                    raise OSError(tr("Book closed"))
                data = self.archive.read(name)
            mime = mimetypes.guess_type(name)[0] or "application/octet-stream"
            return data, mime, csp
        if route == "reader.js" or (route.startswith("foliate/") and route[8:] in {
                "view.js", "epub.js", "epubcfi.js", "progress.js", "overlayer.js", "text-walker.js",
                "paginator.js", "fixed-layout.js", "search.js"}):
            return (base / route).read_bytes(), "text/javascript", csp
        raise KeyError(route)

    def close(self):
        if self.closed:
            return
        with self.lock:
            self.closed = True
            if self.archive:
                self.archive.close()
        # shutdown can wait on the serve loop; keep it off the UI thread.
        threading.Thread(target=self.server.shutdown, daemon=True).start()
        self.server.server_close()
