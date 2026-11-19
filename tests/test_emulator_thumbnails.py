"""
[INPUT]: 依赖本地图像、可控 HTTP 响应与真实 Qt 网络事件。
[OUTPUT]: 验证批量封面查找、临时目录索引与完整图像发布。
[POS]: 封面查找和下载回归；索引仅在单次批处理内复用。
[PROTOCOL]: Update this header on change, then check AGENTS.md
"""

import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QCoreApplication, QEventLoop, QTimer
from PySide6.QtGui import QImage


def image_file(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    image = QImage(4, 6, QImage.Format.Format_RGB32)
    image.fill(0xFF115599)
    assert image.save(str(path), "PNG")
    return path.read_bytes()


def wait_for(predicate, seconds=5):
    deadline = time.monotonic() + seconds
    while not predicate() and time.monotonic() < deadline:
        loop = QEventLoop()
        QTimer.singleShot(10, loop.quit)
        loop.exec()
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


def test_variant_filename_keeps_its_suffix_locally_and_matches_official_art(application, tmp_path, server):
    from udeck.apps.emulator.thumbnails import ThumbnailDownloader, find_thumbnails

    base, requests, png, _ = server
    item = {"path": "/roms/Original [53E0BEF4-1234].zip", "title": "中文汉化版",
            "dbName": "Nintendo - Game Boy"}
    downloader = ThumbnailDownloader(base_url=base)
    downloader.start([item], tmp_path)
    wait_for(lambda: not downloader.running)
    target = tmp_path / "Nintendo - Game Boy/Named_Boxarts/Original [53E0BEF4-1234].png"
    assert target.read_bytes() == png
    assert find_thumbnails(item, tmp_path)["Named_Boxarts"] == target.as_uri()
    assert "/Nintendo%20-%20Game%20Boy/Named_Boxarts/Original.png" in requests
    count = len(requests)
    downloader.start([item], tmp_path)
    wait_for(lambda: not downloader.running)
    assert not any("Named_Boxarts" in path for path in requests[count:])


@pytest.mark.parametrize("language,expected", [("en", "name"), ("zh_CN", "名称")])
def test_unmatched_download_explains_names_instead_of_claiming_success(language, expected):
    from udeck.apps.emulator.library_management import EmulatorLibraryManagement
    from udeck.i18n import render

    owner = SimpleNamespace(thumbnail_downloader=SimpleNamespace(
        running=False, status={"total": 3, "done": 3, "missing": 3}))
    status = render(EmulatorLibraryManagement.thumbnail_status(owner), language)
    assert expected in status
    assert ("Download complete" if language == "en" else "下载完成") not in status


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
            if "Partial.png" in self.path and requests.count(self.path) == 1:
                self.send_response(200)
                self.end_headers()
                self.wfile.write(png[:8])
                self.wfile.flush()
                release.wait(0.4)
            elif "Flaky.png" in self.path and requests.count(self.path) == 1:
                self.send_error(503)
            elif "AlwaysFail.png" in self.path:
                self.send_error(503)
            elif "Named_Boxarts/Original.png" in self.path or "Flaky.png" in self.path or "Partial.png" in self.path:
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


def test_transient_server_failure_retries_and_success_is_preserved(application, tmp_path, server):
    from udeck.apps.emulator.thumbnails import ThumbnailDownloader

    base, requests, png, _ = server
    downloader = ThumbnailDownloader(base_url=base)
    item = {"path": "/roms/Flaky.gb", "title": "Flaky", "dbName": "Nintendo - Game Boy"}
    downloader.start([item], tmp_path)
    wait_for(lambda: not downloader.running)
    assert downloader.status["saved"] == 3 and downloader.status["failed"] == 0
    assert downloader.status["retried"] == 3
    assert len(requests) == 6
    assert all(path.read_bytes() == png for path in tmp_path.glob("Nintendo - Game Boy/*/Flaky.png"))


def test_permanent_server_failure_has_a_bounded_retry_budget(application, tmp_path, server):
    from udeck.apps.emulator.thumbnails import ThumbnailDownloader

    base, requests, _, _ = server
    downloader = ThumbnailDownloader(base_url=base)
    item = {"path": "/roms/AlwaysFail.gb", "title": "AlwaysFail", "dbName": "Nintendo - Game Boy"}
    downloader.start([item], tmp_path)
    wait_for(lambda: not downloader.running)
    assert downloader.status["failed"] == 3 and downloader.status["done"] == 3
    assert len(requests) == 6
    assert not list(tmp_path.glob("Nintendo - Game Boy/*/*.png"))


def test_timeout_after_http_headers_retries_and_discards_partial_body(application, tmp_path, server):
    from udeck.apps.emulator.thumbnails import ThumbnailDownloader

    base, requests, png, _ = server
    downloader = ThumbnailDownloader(base_url=base, timeout=100)
    item = {"path": "/roms/Partial.gb", "title": "Partial", "dbName": "Nintendo - Game Boy"}
    downloader.start([item], tmp_path)
    wait_for(lambda: not downloader.running)
    assert downloader.status["saved"] == 3 and downloader.status["failed"] == 0
    assert downloader.status["retried"] == 3
    assert len(requests) >= 6  # Qt 还会重试断开的复用连接。
    files = list(tmp_path.glob("Nintendo - Game Boy/*/Partial.png"))
    assert len(files) == 3 and all(path.read_bytes() == png for path in files)


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


def test_reload_thumbnails_bounds_filesystem_probes_by_directory(application, tmp_path, monkeypatch):
    from test_emulator_playlist_library import thumbnail_library

    library, state, _, _, boxart = thumbnail_library(tmp_path)
    root = tmp_path / 'thumbnails'
    library.items = [{'path': '/roms/Original.gb', 'title': 'Original', 'dbName': 'Nintendo - Game Boy'}
                     for _ in range(100)]
    original_stat = os.stat
    probes = []

    def stat(path, *args, **kwargs):
        if isinstance(path, (str, bytes, os.PathLike)) and Path(path).is_relative_to(root):
            probes.append(str(path))
        return original_stat(path, *args, **kwargs)

    monkeypatch.setattr(os, 'stat', stat)
    try:
        library.reload_thumbnails()
        assert all(item['cover'] == boxart.as_uri() for item in library.items)
        assert len(probes) < 12
    finally:
        library.close()
        state.close()


def test_reload_discovers_added_replaced_and_preferred_images(application, tmp_path):
    from test_emulator_playlist_library import thumbnail_library

    library, state, _, _, boxart = thumbnail_library(tmp_path)
    library.items = [{'path': '/roms/Original.gb', 'title': 'Original', 'dbName': 'Nintendo - Game Boy'}]
    try:
        boxart.unlink()
        library.reload_thumbnails()
        assert library.items[0]['cover'] == ''
        jpg = boxart.with_suffix('.jpg')
        jpg.write_bytes(b'jpg')
        library.reload_thumbnails()
        assert library.items[0]['cover'] == jpg.as_uri()
        boxart.write_bytes(b'png')
        library.reload_thumbnails()
        assert library.items[0]['cover'] == boxart.as_uri()
        snap = boxart.parent.parent / 'Named_Snaps/Original.png'
        snap.parent.mkdir()
        snap.write_bytes(b'snap')
        state.data['preferences']['thumbnailType'] = 'Named_Snaps'
        library.reload_thumbnails()
        assert library.items[0]['cover'] == snap.as_uri()
        boxart.unlink()
        boxart.symlink_to(jpg)
        state.data['preferences']['thumbnailType'] = 'Named_Boxarts'
        library.reload_thumbnails()
        assert library.items[0]['cover'] == jpg.as_uri()
    finally:
        library.close()
        state.close()


def test_downloader_preparation_bounds_filesystem_probes_by_directory(application, tmp_path, monkeypatch):
    from udeck.apps.emulator.thumbnails import ThumbnailDownloader

    root = tmp_path / 'thumbnails'
    items = [{'path': f'/roms/Game{index}.gb', 'title': f'Game{index}', 'dbName': 'Nintendo - Game Boy'}
             for index in range(100)]
    original_stat = os.stat
    probes = []

    def stat(path, *args, **kwargs):
        if isinstance(path, (str, bytes, os.PathLike)) and Path(path).is_relative_to(root):
            probes.append(str(path))
        return original_stat(path, *args, **kwargs)

    monkeypatch.setattr(os, 'stat', stat)
    downloader = ThumbnailDownloader()
    try:
        downloader.start(items, root)
        assert downloader.status['total'] == 300
        assert len(probes) < 12
    finally:
        downloader.cancel()


@pytest.mark.parametrize('boundary', ['root', 'database', 'kind'])
def test_bulk_lookup_rejects_symbolic_link_directories(application, tmp_path, boundary):
    from test_emulator_playlist_library import thumbnail_library

    library, state, _, _, _ = thumbnail_library(tmp_path)
    root = tmp_path / 'linked-thumbnails'
    actual = tmp_path / 'actual'
    database, kind = 'Nintendo - Game Boy', 'Named_Boxarts'
    image_file(actual / database / kind / 'Original.png')
    if boundary == 'root':
        root.symlink_to(actual, target_is_directory=True)
    elif boundary == 'database':
        root.mkdir()
        (root / database).symlink_to(actual / database, target_is_directory=True)
    else:
        (root / database).mkdir(parents=True)
        (root / database / kind).symlink_to(actual / database / kind, target_is_directory=True)
    library.thumbnail_path = str(root)
    library.items = [{'path': '/roms/Original.gb', 'title': 'Original', 'dbName': database}]
    try:
        library.reload_thumbnails()
        assert library.items[0]['thumbnails'] == {} and library.items[0]['cover'] == ''
    finally:
        library.close()
        state.close()
