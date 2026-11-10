"""Default user folders are scanned and saved without replacing custom sources."""

import time
from pathlib import Path

import pytest
from PySide6.QtCore import QCoreApplication, QThreadPool
from PySide6.QtTest import QTest
from test_games_catalog import installed

from udeck.apps.common.library import Library, Source
from udeck.apps.common.state import AppState
from udeck.apps.emulator.library import EmulatorLibrary


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
    ("emulator", "Games", "gba/original.gba"),
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
        QTest.qWait(20)
    assert not library.pending
    assert not any(library.errors.values())


def test_default_folder_indexes_nested_content_and_restores_identity(application, tmp_path, home, content):
    app, folder, relative = content
    path = home / folder / relative
    path.parent.mkdir(parents=True)
    path.write_bytes(b"original library fixture")
    (path.parent / "ignored.exe").write_bytes(b"unsupported")
    catalog = installed(tmp_path, {"mgba": {"supported_extensions": "gba"}})
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
