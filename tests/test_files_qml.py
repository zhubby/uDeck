import json
import os
import subprocess
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import pytest


def run_probe(tmp_path, language, theme, size, preview_url=""):
    result = subprocess.run(
        [sys.executable, str(Path(__file__).with_name("files_qml_probe.py")), str(tmp_path), language, theme,
         str(size[0]), str(size[1]), preview_url],
        env={**os.environ, "PYTHONPATH": "src", "QT_QPA_PLATFORM": "offscreen", "QT_QUICK_BACKEND": "software"},
        capture_output=True, text=True, timeout=25,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout.strip().splitlines()[-1])
    assert report["qmlErrors"] == []
    assert report["selectionCount"] == 1
    assert (tmp_path / "files.png").stat().st_size > 10000


@pytest.mark.parametrize("language", ["en", "zh_CN"])
@pytest.mark.parametrize("theme", ["classic", "dark"])
@pytest.mark.parametrize("size", [(1280, 720), (960, 600)])
def test_files_workspace_renders_with_controller_navigation(tmp_path, language, theme, size):
    run_probe(tmp_path, language, theme, size)


def test_files_preview_waits_for_a_delayed_image(tmp_path):
    class PreviewHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            data = (tmp_path / "preview.png").read_bytes()
            time.sleep(0.35)
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            try:
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def log_message(self, format, *args):
            pass

    with ThreadingHTTPServer(("127.0.0.1", 0), PreviewHandler) as server:
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            run_probe(tmp_path, "en", "classic", (1280, 720),
                      f"http://127.0.0.1:{server.server_port}/preview.png")
        finally:
            server.shutdown()
            thread.join(timeout=5)
