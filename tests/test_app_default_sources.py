"""
[INPUT]: 依赖真实媒体库、模拟器列表库和默认用户目录夹具。
[OUTPUT]: 验证默认源发现、条目身份恢复、自定义源保留和视频封面缓存。
[POS]: 默认源回归；通过 Qt 事件泵和 GIL 让步等待扫描。
[PROTOCOL]: Update this header on change, then check AGENTS.md
"""

import shutil
import subprocess
import time
from pathlib import Path

import pytest
from PySide6.QtCore import QCoreApplication, QThreadPool
from PySide6.QtGui import QImage
from test_games_catalog import installed

from udeck.apps.common.library import Library, Source
from udeck.apps.common.state import AppState
from udeck.apps.emulator.library import EmulatorLibrary
from udeck.apps.emulator.playlists import generate_playlists


@pytest.fixture
def application():
    return QCoreApplication.instance() or QCoreApplication([])


@pytest.fixture
def home(tmp_path, monkeypatch):
    path = tmp_path / "home"
    path.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: path))
    return path


@pytest.fixture(params=[
    ("music", "Music", "albums/original.wav"),
    ("video", "Video", "clips/original.mp4"),
    ("reader", "Books", "books/original.txt"),
    ("emulator", "Games/roms", "Nintendo - Game Boy Advance/original.gba"),
])
def content(request):
    return request.param


def library_for(app, directory, catalog):
    state = AppState(app, directory)
    return EmulatorLibrary(state, catalog) if app == "emulator" else Library(app, state)


def refresh(library):
    library.refresh()
    deadline = time.monotonic() + 3
    while library.pending and time.monotonic() < deadline:
        QCoreApplication.processEvents()
        # 显式让出 GIL，使 Python 扫描线程继续执行。
        if library.pending:
            time.sleep(0.01)
    QCoreApplication.processEvents()
    assert not library.pending, {"pending": library.pending, "errors": library.errors}
    assert not any(library.errors.values())


@pytest.mark.parametrize("embedded", [True, False])
def test_video_library_fills_missing_cover_and_reuses_it(home, tmp_path, monkeypatch, embedded):
    if not shutil.which("ffmpeg"):
        pytest.skip("FFmpeg is required for the video cover fixture")
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    source = home / "Video"
    source.mkdir()
    command = ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=blue:s=96x64:r=10:d=1"]
    if embedded:
        command += ["-f", "lavfi", "-i", "color=red:s=96x64:r=1:d=1", "-map", "0:v", "-map", "1:v",
                    "-c:v:1", "mjpeg", "-disposition:v:1", "attached_pic", "-frames:v:1", "1"]
    subprocess.run([*command, "-c:v:0", "mpeg4", str(source / "sample.mp4")],
                   capture_output=True, check=True, timeout=10)
    library = Library("video", AppState("video", tmp_path / "state"))
    try:
        refresh(library)
        deadline = time.monotonic() + 5
        while not library.items[0]["cover"] and time.monotonic() < deadline:
            QCoreApplication.processEvents()
            time.sleep(0.01)
        cover_url = library.items[0]["cover"]
        assert cover_url
        covers = list((tmp_path / "cache").rglob("*.jpg"))
        assert len(covers) == 1 and covers[0].as_uri() == cover_url
        image = QImage(str(covers[0]))
        assert not image.isNull()
        pixel = image.pixelColor(image.width() // 2, image.height() // 2)
        assert (pixel.red() > pixel.blue()) if embedded else (pixel.blue() > pixel.red())
        stamp = covers[0].stat().st_mtime_ns
        refresh(library)
        assert library.items[0]["cover"] == cover_url
        assert covers[0].stat().st_mtime_ns == stamp

        sidecar = source / "sample.png"
        assert image.save(str(sidecar))
        refresh(library)
        assert library.items[0]["cover"] == sidecar.as_uri()
    finally:
        library.close()
        QThreadPool.globalInstance().waitForDone(5000)


def test_default_folder_indexes_nested_content_and_restores_identity(application, tmp_path, home, content):
    app, folder, relative = content
    path = home / folder / relative
    path.parent.mkdir(parents=True)
    path.write_bytes(b"original library fixture")
    (path.parent / "ignored.exe").write_bytes(b"unsupported")
    catalog = installed(tmp_path, {"mgba": {"supported_extensions": "gba"}})
    if app == "emulator":
        generate_playlists(home / folder, home / "Games/playlists", catalog).commit()
    directory = tmp_path / "state"
    library = library_for(app, directory, catalog)
    try:
        refresh(library)
        assert [item["path"] for item in library.items] == [str(path)]
        assert [source.path for source in library.sources] == [str(home / folder)]
        identifier = library.items[0]["id"]
        refresh(library)
        assert [item["id"] for item in library.items] == [identifier]
        restored = library_for(app, directory, catalog)
        try:
            refresh(restored)
            assert [item["id"] for item in restored.items] == [identifier]
            assert len(restored.sources) == 1
        finally:
            restored.close()
    finally:
        library.close()
        QThreadPool.globalInstance().waitForDone(3000)


def test_default_folder_created_after_startup_is_found_on_refresh(application, tmp_path, home, content):
    app, folder, relative = content
    catalog = installed(tmp_path, {"mgba": {"supported_extensions": "gba"}})
    library = library_for(app, tmp_path / "state", catalog)
    try:
        library.refresh()
        assert not library.items and not library.sources
        path = home / folder / relative
        path.parent.mkdir(parents=True)
        path.write_bytes(b"original library fixture")
        if app == "emulator":
            generate_playlists(home / folder, home / "Games/playlists", catalog).commit()
        refresh(library)
        assert [item["path"] for item in library.items] == [str(path)]
    finally:
        library.close()
        QThreadPool.globalInstance().waitForDone(3000)


def test_saved_custom_folder_is_preserved_when_default_exists(application, tmp_path, home, content):
    app, folder, relative = content
    default = home / folder / relative
    default.parent.mkdir(parents=True)
    default.write_bytes(b"default fixture")
    path = tmp_path / "custom" / relative
    path.parent.mkdir(parents=True)
    path.write_bytes(b"custom fixture")
    catalog = installed(tmp_path, {"mgba": {"supported_extensions": "gba"}})
    directory = tmp_path / "state"
    state = AppState(app, directory)
    state.data["sources"] = [Source.create(tmp_path / "custom").to_dict()]
    if app == "emulator":
        state.data["preferences"]["romRoot"] = str(tmp_path / "custom")
        state.data["preferences"]["playlistDirectory"] = str(tmp_path / "playlists")
        generate_playlists(tmp_path / "custom", tmp_path / "playlists", catalog).commit()
    state.save()
    library = library_for(app, directory, catalog)
    try:
        refresh(library)
    finally:
        library.close()
        QThreadPool.globalInstance().waitForDone(3000)
    restored = library_for(app, directory, catalog)
    try:
        refresh(restored)
        assert [source.path for source in restored.sources] == [str(tmp_path / "custom")]
        assert [item["path"] for item in restored.items] == [str(path)]
    finally:
        restored.close()
        QThreadPool.globalInstance().waitForDone(3000)
