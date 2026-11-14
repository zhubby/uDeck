"""Real local images and HTTP responses exercise thumbnail matching and publication."""

import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from PySide6.QtCore import QCoreApplication
from PySide6.QtGui import QImage
from PySide6.QtTest import QTest


def image_file(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    image = QImage(4, 6, QImage.Format.Format_RGB32)
    image.fill(0xFF115599)
    assert image.save(str(path), "PNG")
    return path.read_bytes()


def wait_for(predicate, seconds=5):
    deadline = time.monotonic() + seconds
    while not predicate() and time.monotonic() < deadline:
        QTest.qWait(10)
    assert predicate()


@pytest.fixture
def application():
    return QCoreApplication.instance() or QCoreApplication([])


def test_custom_playlist_uses_each_entry_database_and_flexible_names(tmp_path):
    from udeck.apps.emulator.thumbnails import find_thumbnails

    root = tmp_path / "Nintendo - Game Boy"
    file = root / "Named_Boxarts/ROM.png"
    image_file(file)
    snap = root / "Named_Snaps/Q_Bert_s Qubes.png"
    image_file(snap)
    item = {"path": "/roms/ROM.gb", "title": "Q*Bert`s Qubes (USA)",
            "dbName": "Nintendo - Game Boy", "album": "Custom"}
    images = find_thumbnails(item, tmp_path)
    assert images["Named_Boxarts"] == file.as_uri()
    assert images["Named_Snaps"] == snap.as_uri()
    assert "Named_Titles" not in images


def test_local_label_matching_and_directory_traversal_are_bounded(tmp_path):
    from udeck.apps.emulator.thumbnails import find_thumbnails

    target = tmp_path / "Atari - 2600/Named_Titles/Q_bert (USA).png"
    image_file(target)
    item = {"path": "/roms/a.a26", "title": "Q*bert (USA)", "dbName": "Atari - 2600"}
    assert find_thumbnails(item, tmp_path)["Named_Titles"] == target.as_uri()
    item["dbName"] = "../Atari - 2600"
    assert find_thumbnails(item, tmp_path) == {}


@pytest.fixture
def server(tmp_path):
    png = image_file(tmp_path / "fixture.png")
    requests = []
    release = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def handle(self):
            try:
                super().handle()
            except (BrokenPipeError, ConnectionResetError):
                pass  # Cancellation and timeout deliberately close the connection.

        def do_GET(self):
            requests.append(self.path)
            if "/Slow" in self.path:
                release.wait(3)
            if "Named_Boxarts/Original.png" in self.path:
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.end_headers()
                try:
                    self.wfile.write(png)
                except (BrokenPipeError, ConnectionResetError):
                    pass
            elif "Named_Titles" in self.path:
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"not an image")
            else:
                self.send_error(404)

        def log_message(self, *args):
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_port}/", requests, png, release
    release.set()
    httpd.shutdown()
    httpd.server_close()
    thread.join()


def test_downloader_checks_responses_and_keeps_custom_images(application, tmp_path, server):
    from udeck.apps.emulator.thumbnails import ThumbnailDownloader

    base, requests, png, _ = server
    root = tmp_path / "thumbnails"
    custom = root / "Nintendo - Game Boy/Named_Snaps/Original.png"
    image_file(custom)
    before = custom.read_bytes()
    downloader = ThumbnailDownloader(base_url=base)
    downloader.start([{"path": "/roms/Original.gb", "title": "Original", "dbName": "Nintendo - Game Boy"}], root)
    wait_for(lambda: not downloader.running)
    assert (root / "Nintendo - Game Boy/Named_Boxarts/Original.png").read_bytes() == png
    assert custom.read_bytes() == before
    assert not (root / "Nintendo - Game Boy/Named_Titles/Original.png").exists()
    assert not any("Named_Snaps" in path for path in requests)
    assert downloader.status["saved"] == 1 and downloader.status["failed"] == 1


def test_cancel_aborts_pending_requests_and_never_publishes_partial_image(application, tmp_path, server):
    from udeck.apps.emulator.thumbnails import ThumbnailDownloader

    base, requests, _, release = server
    downloader = ThumbnailDownloader(base_url=base)
    downloader.start([{"path": "/roms/Slow.gb", "title": "Slow", "dbName": "Nintendo - Game Boy"}], tmp_path)
    wait_for(lambda: bool(requests))
    downloader.cancel()
    release.set()
    wait_for(lambda: not downloader.running)
    assert not list((tmp_path / "Nintendo - Game Boy").rglob("*.png"))
    assert downloader.status["cancelled"]


def test_timeout_finishes_with_retryable_failures_and_no_partial_files(application, tmp_path, server):
    from udeck.apps.emulator.thumbnails import ThumbnailDownloader

    base, _, _, release = server
    downloader = ThumbnailDownloader(base_url=base, timeout=100)
    item = {"path": "/roms/Slow.gb", "title": "Slow", "dbName": "Nintendo - Game Boy"}
    downloader.start([item], tmp_path)
    wait_for(lambda: not downloader.running)
    assert downloader.status["failed"] == 3 and downloader.status["done"] == 3
    assert not list((tmp_path / "Nintendo - Game Boy").rglob("*.png"))
    release.set()
    downloader.start([item], tmp_path)
    wait_for(lambda: not downloader.running)
    assert downloader.status["missing"] == 2 and downloader.status["failed"] == 1
