"""Streaming HTTP workspace with bounded uploads, downloads and file jobs."""

import asyncio
import io
import os
import re
import secrets
import stat
import threading
import time
import uuid
import zipfile
from pathlib import Path
from urllib.parse import quote, urlsplit

from aiohttp import web

from ..core import ConfigStore
from ..file_icons import ICON_PALETTES, ICON_SPECS
from .filesystem import SharedRoot

ROOT = Path(__file__).resolve().parents[1]
STATE = web.AppKey("workspace", object)


class Workspace:
    def __init__(self, root, state_directory=None):
        self.fs = SharedRoot(root, trash_directory=Path(state_directory) / "Trash" if state_directory else None)
        self.token = secrets.token_urlsafe(32)
        self.uploads, self.tasks, self.archives = {}, {}, {}
        self.upload_limit, self.download_limit = asyncio.Semaphore(2), asyncio.Semaphore(2)
        self.mutation_lock = asyncio.Lock()
        self.closing = False
        self.workers, self.stream_cancellations = set(), set()
        self.reserved_uploads = 0

    async def run(self, function, *args, **kwargs):
        """A cancelled request must not close a descriptor still used by its worker."""
        task = asyncio.create_task(asyncio.to_thread(function, *args, **kwargs))
        self.workers.add(task)
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            await asyncio.shield(task)
            raise
        finally:
            self.workers.discard(task)

    def expire(self):
        now = time.monotonic()
        for key, value in list(self.uploads.items()):
            if not value.get("active") and now - value["created"] > 900:
                value["upload"].abort()
                del self.uploads[key]
        self.archives = {key: value for key, value in self.archives.items() if now - value["created"] < 300}

    def shutdown(self):
        self.closing = True
        for task in self.tasks.values():
            task["cancel"].set()
        for cancelled in self.stream_cancellations:
            cancelled.set()
        for value in list(self.uploads.values()):
            self.cancel_upload(value)

    def cancel_upload(self, value):
        value["cancel"].set()
        receiver = value.get("receiver")
        if receiver and not receiver.cancelling():
            receiver.cancel()

    async def close(self):
        self.shutdown()
        await asyncio.gather(*(task["future"] for task in self.tasks.values()), return_exceptions=True)
        await asyncio.gather(*self.workers, return_exceptions=True)
        for value in self.uploads.values():
            value["upload"].abort()
        self.fs.close()

    def report(self, task):
        return {key: value for key, value in task.items() if key not in ("future", "cancel")}

    async def job(self, task, paths, destination, policy):
        async with self.mutation_lock:
            task["state"] = "running"
            started = time.monotonic()

            def work():
                def progress(count):
                    task["doneBytes"] += count
                    task["speed"] = task["doneBytes"] / max(.01, time.monotonic() - started)
                for path in paths:
                    if task["cancel"].is_set():
                        task["state"] = "cancelled"
                        return
                    task["current"] = path
                    try:
                        if task["action"] == "trash":
                            self.fs.trash(path)
                        else:
                            result = self.fs.transfer(path, destination, move=task["action"] == "move",
                                                      policy=policy, cancelled=task["cancel"], progress=progress)
                            if result is None:
                                task["skipped"] += 1
                                continue
                        task["doneItems"] += 1
                    except InterruptedError:
                        task["state"] = "cancelled"
                        return
                    except (OSError, ValueError) as error:
                        task["errors"].append({"path": path, "reason": str(error)})
                task["state"] = "failed" if task["errors"] else "completed"
            await self.run(work)


@web.middleware
async def boundary(request, handler):
    workspace = request.app[STATE]
    if workspace.closing:
        raise web.HTTPServiceUnavailable(reason="Network access has stopped")
    # Hostname-based rebinding and cross-origin browser writes are rejected.
    try:
        host = urlsplit("http://" + request.host).hostname
    except ValueError:
        host = None
    local = request.transport.get_extra_info("sockname")[0]
    if host not in {local, "localhost" if local in ("127.0.0.1", "::1") else local}:
        return web.json_response({"error": "Invalid server address"}, status=403)
    if request.method not in ("GET", "HEAD"):
        origin = request.headers.get("Origin")
        if (request.headers.get("X-UDeck-Request") != workspace.token or
                origin and origin != f"{request.scheme}://{request.host}" or
                request.headers.get("Sec-Fetch-Site") == "cross-site"):
            return web.json_response({"error": "Open this action from the Files page"}, status=403)
    workspace.expire()
    try:
        response = await handler(request)
    except web.HTTPException as error:
        return web.json_response({"error": error.reason}, status=error.status)
    except ConnectionResetError:
        raise
    except FileExistsError as error:
        return web.json_response({"error": str(error), "code": "conflict"}, status=409)
    except FileNotFoundError:
        return web.json_response({"error": "The file or folder is no longer available"}, status=404)
    except PermissionError:
        return web.json_response({"error": "Permission denied"}, status=403)
    except (ValueError, TypeError, KeyError, OSError) as error:
        return web.json_response({"error": str(error)}, status=400)
    if not response.prepared:
        static = request.path.startswith("/assets/")
        cache = "public, max-age=86400" if request.path.startswith(("/assets/font/", "/assets/icon/")) else "no-cache" if static else "no-store"
        response.headers.update({"X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer",
                                 "Cache-Control": cache, "X-Frame-Options": "DENY",
                                 "Content-Security-Policy": "default-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"})
    return response


async def body(request):
    value = await request.json()
    if not isinstance(value, dict):
        raise ValueError("Expected an object")
    return value


async def configuration(request):
    fs = request.app[STATE]
    preferences = ConfigStore().data["preferences"]
    return web.json_response({"name": fs.fs.path.name or "/", "theme": preferences["theme"],
                              "language": preferences["language"], "requestToken": fs.token})


async def files(request):
    query = request.query
    offset, limit = max(0, int(query.get("offset", 0))), min(500, max(1, int(query.get("limit", 200))))
    workspace = request.app[STATE]
    result = await workspace.run(workspace.fs.listing, query.get("path", ""),
                                     hidden=query.get("hidden") == "1", query=query.get("query", ""),
                                     sort=query.get("sort", "name"), descending=query.get("descending") == "1",
                                     offset=offset, limit=limit)
    return web.json_response(result)


async def folder(request):
    value = await body(request)
    async with request.app[STATE].mutation_lock:
        path = await request.app[STATE].run(request.app[STATE].fs.mkdir, value["path"],
                                          parents=bool(value.get("parents")), policy=value.get("policy", "error"))
    return web.json_response({"ok": True, "path": path})


async def rename(request):
    value = await body(request)
    async with request.app[STATE].mutation_lock:
        await request.app[STATE].run(request.app[STATE].fs.rename, value["path"], value["name"])
    return web.json_response({"ok": True})


async def conflicts(request):
    workspace = request.app[STATE]
    value = await body(request)
    paths = workspace.fs.distinct(value["paths"])
    def inspect():
        with workspace.fs.directory(value.get("destination", "")) as fd:
            return [Path(path).name for path in paths if workspace.fs.information(fd, Path(path).name)]
    return web.json_response({"conflicts": await workspace.run(inspect)})


async def upload_create(request):
    workspace = request.app[STATE]
    if len(workspace.uploads) + workspace.reserved_uploads >= 8:
        raise web.HTTPTooManyRequests(reason="Wait for the current uploads")
    value = await body(request)
    workspace.reserved_uploads += 1
    upload = None
    def create():
        nonlocal upload
        upload = workspace.fs.begin_upload(value["path"], value["size"], value.get("policy", "error"), parents=bool(value.get("parents")))
    try:
        await workspace.run(create)
    except BaseException:
        if upload:
            upload.abort()
        raise
    finally:
        workspace.reserved_uploads -= 1
    key = uuid.uuid4().hex
    workspace.uploads[key] = {"upload": upload, "created": time.monotonic(), "cancel": threading.Event(), "active": False}
    return web.json_response({"id": key, "name": upload.name})


async def upload_write(request):
    workspace = request.app[STATE]
    value = workspace.uploads[request.match_info["id"]]
    if value["active"]:
        raise ValueError("Upload is already running")
    value["active"] = True
    upload = value["upload"]
    try:
        if request.content_length != upload.size:
            raise ValueError("Upload size does not match")
        async def receive():
            async with workspace.upload_limit:
                async for chunk in request.content.iter_chunked(256 * 1024):
                    if value["cancel"].is_set():
                        raise ValueError("Upload cancelled")
                    await workspace.run(upload.write, chunk)
                if value["cancel"].is_set():
                    raise ValueError("Upload cancelled")
                async with workspace.mutation_lock:
                    return await workspace.run(upload.commit, value["cancel"])
        receiver = value["receiver"] = asyncio.create_task(receive())
        try:
            name = await receiver
        except asyncio.CancelledError:
            if not value["cancel"].is_set():
                raise
            raise ValueError("Upload cancelled") from None
        return web.json_response({"ok": True, "name": name})
    finally:
        upload.abort()
        workspace.uploads.pop(request.match_info["id"], None)


async def upload_cancel(request):
    workspace = request.app[STATE]
    value = workspace.uploads.get(request.match_info["id"])
    if value:
        workspace.cancel_upload(value)
        if not value["active"]:
            value["upload"].abort()
            workspace.uploads.pop(request.match_info["id"], None)
    return web.json_response({"ok": True})


def attachment(name):
    return "attachment; filename=download; filename*=UTF-8''" + quote(name, safe="")


async def download(request):
    workspace = request.app[STATE]
    async with workspace.download_limit:
        stream = workspace.fs.open_file(request.query["path"])
        cancelled = threading.Event()
        workspace.stream_cancellations.add(cancelled)
        response = None
        try:
            size = os.fstat(stream.fileno()).st_size
            start, end, status = 0, size - 1, 200
            value = request.headers.get("Range")
            if value:
                match = re.fullmatch(r"bytes=(\d*)-(\d*)", value)
                if not match or not any(match.groups()) or not size:
                    raise web.HTTPRequestRangeNotSatisfiable()
                left, right = match.groups()
                start = int(left) if left else max(0, size - int(right))
                end = min(size - 1, int(right)) if left and right else size - 1
                if start > end or start >= size:
                    raise web.HTTPRequestRangeNotSatisfiable()
                status = 206
            headers = {"Content-Type": "application/octet-stream", "Content-Length": str(max(0, end - start + 1)),
                       "Content-Disposition": attachment(Path(request.query["path"]).name), "Accept-Ranges": "bytes", "X-Content-Type-Options": "nosniff"}
            if status == 206:
                headers["Content-Range"] = f"bytes {start}-{end}/{size}"
            response = web.StreamResponse(status=status, headers=headers)
            await response.prepare(request)
            stream.seek(start)
            remaining = end - start + 1
            while remaining > 0:
                if cancelled.is_set():
                    raise ConnectionResetError("Network access has stopped")
                chunk = await workspace.run(stream.read, min(256 * 1024, remaining))
                if not chunk:
                    raise OSError("File changed during download")
                await response.write(chunk)
                remaining -= len(chunk)
            await response.write_eof()
            return response
        except OSError as error:
            if response and response.prepared:
                if request.transport:
                    request.transport.close()
                raise ConnectionResetError("Download interrupted") from error
            raise
        finally:
            workspace.stream_cancellations.discard(cancelled)
            stream.close()


async def task_create(request):
    workspace = request.app[STATE]
    value = await body(request)
    if value["action"] not in ("copy", "move", "trash") or value.get("policy", "error") not in ("error", "keep", "skip", "replace"):
        raise ValueError("Unsupported operation")
    paths = workspace.fs.distinct(value["paths"])
    pending = [task for task in workspace.tasks.values() if task["state"] in ("queued", "running")]
    if len(pending) >= 16:
        raise web.HTTPTooManyRequests(reason="Wait for the current file tasks")
    if len(workspace.tasks) >= 64:
        for key, task in list(workspace.tasks.items()):
            if task["state"] not in ("queued", "running"):
                del workspace.tasks[key]
                break
    task = {"id": uuid.uuid4().hex, "action": value["action"], "state": "queued", "current": "",
            "doneBytes": 0, "doneItems": 0, "totalItems": len(paths), "skipped": 0, "speed": 0,
            "errors": [], "cancel": threading.Event()}
    workspace.tasks[task["id"]] = task
    task["future"] = asyncio.create_task(workspace.job(task, paths, value.get("destination", ""), value.get("policy", "error")))
    return web.json_response(workspace.report(task))


async def task_status(request):
    workspace = request.app[STATE]
    return web.json_response(workspace.report(workspace.tasks[request.match_info["id"]]))


async def task_cancel(request):
    request.app[STATE].tasks[request.match_info["id"]]["cancel"].set()
    return web.json_response({"ok": True})


async def archive_create(request):
    workspace = request.app[STATE]
    if len(workspace.archives) >= 16:
        raise web.HTTPTooManyRequests(reason="Wait for the current downloads")
    paths = workspace.fs.distinct((await body(request))["paths"])
    def validate():
        for count, _ in enumerate(workspace.fs.walk(paths)):
            if count >= 100000:
                raise ValueError("Choose fewer files for one download")
    await workspace.run(validate)
    key = uuid.uuid4().hex
    workspace.archives[key] = {"paths": paths, "created": time.monotonic()}
    return web.json_response({"id": key})


class ZipSink(io.RawIOBase):
    def __init__(self, loop, queue, cancelled):
        self.loop, self.queue, self.cancelled, self.position = loop, queue, cancelled, 0

    def writable(self):
        return True

    def tell(self):
        return self.position

    def write(self, data):
        if self.cancelled.is_set():
            raise InterruptedError("Download cancelled")
        if data:
            pending = asyncio.run_coroutine_threadsafe(self.queue.put(bytes(data)), self.loop)
            while not pending.done():
                if self.cancelled.wait(.02):
                    pending.cancel()
                    raise InterruptedError("Download cancelled")
            pending.result()
        self.position += len(data)
        return len(data)


async def archive_download(request):
    workspace = request.app[STATE]
    ticket = workspace.archives.pop(request.match_info["id"])
    async with workspace.download_limit:
        queue, cancelled = asyncio.Queue(maxsize=4), threading.Event()
        workspace.stream_cancellations.add(cancelled)
        loop = asyncio.get_running_loop()
        def produce():
            try:
                with zipfile.ZipFile(ZipSink(loop, queue, cancelled), "w", compression=zipfile.ZIP_STORED, allowZip64=True) as archive:
                    for path, info in workspace.fs.walk(ticket["paths"], cancelled):
                        if stat.S_ISDIR(info.st_mode):
                            archive.writestr(path + "/", b"")
                        else:
                            with workspace.fs.open_file(path) as source, archive.open(path, "w", force_zip64=True) as target:
                                while chunk := source.read(256 * 1024):
                                    target.write(chunk)
                return None
            except (OSError, ValueError) as error:
                return error
        future = asyncio.create_task(workspace.run(produce))
        response = web.StreamResponse(headers={"Content-Type": "application/zip", "Content-Disposition": attachment("uDeck-files.zip")})
        try:
            await response.prepare(request)
            while not future.done() or not queue.empty():
                try:
                    chunk = await asyncio.wait_for(queue.get(), .1)
                    await response.write(chunk)
                except TimeoutError:
                    pass
            error = await future
            if error:
                if request.transport:
                    request.transport.close()
                raise ConnectionResetError("Archive interrupted") from error
            await response.write_eof()
            return response
        finally:
            cancelled.set()
            await asyncio.shield(future)
            workspace.stream_cancellations.discard(cancelled)


async def asset(request):
    name = request.match_info.get("name", "index.html")
    fixed = {"logo.svg": ROOT / "assets/branding/udeck.svg"}
    if name in fixed:
        return web.FileResponse(fixed[name])
    if name.startswith("font/") and name[5:] in {"SairaSemiCondensed-Regular.ttf", "SairaSemiCondensed-Medium.ttf", "LXGWWenKaiScreen.ttf"}:
        return web.FileResponse(ROOT / "fonts" / name[5:])
    if name in {"index.html", "app.js", "style.css"}:
        return web.FileResponse(Path(__file__).parent / "web" / name)
    if name.startswith("icon/"):
        kind = name[5:].removeprefix("udeck-file-")
        glyph, palette = ICON_SPECS.get(kind, ICON_SPECS["unknown"])
        background, foreground = ICON_PALETTES[palette]
        source = (ROOT / "assets/file-icons" / (glyph + ".svg")).read_text()
        content = source.partition(">")[2].rsplit("</svg>", 1)[0]
        svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect x="1" y="1" width="62" height="62" rx="13" fill="{background}"/><svg x="10" y="10" width="44" height="44" viewBox="0 0 24 24" fill="none" stroke="{foreground}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">{content}</svg></svg>'
        return web.Response(text=svg, content_type="image/svg+xml")
    raise web.HTTPNotFound()


def create_app(root, *, state_directory=None):
    app = web.Application(middlewares=[boundary], client_max_size=1024 * 1024)
    app[STATE] = Workspace(root, state_directory)
    app.add_routes([web.get("/api/config", configuration), web.get("/api/files", files),
                    web.post("/api/folders", folder), web.post("/api/rename", rename), web.post("/api/conflicts", conflicts),
                    web.post("/api/uploads", upload_create), web.put("/api/uploads/{id}", upload_write),
                    web.delete("/api/uploads/{id}", upload_cancel), web.get("/api/download", download),
                    web.post("/api/tasks", task_create), web.get("/api/tasks/{id}", task_status),
                    web.delete("/api/tasks/{id}", task_cancel), web.post("/api/archives", archive_create),
                    web.get("/api/archives/{id}", archive_download), web.get("/", asset), web.get("/assets/{name:.*}", asset)])
    async def shutdown(_app):
        app[STATE].shutdown()
    async def cleanup(_app):
        await app[STATE].close()
    app.on_shutdown.append(shutdown)
    app.on_cleanup.append(cleanup)
    return app
