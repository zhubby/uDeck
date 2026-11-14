"""The runtime library is driven exclusively by playlists, including missing games."""

import time

import pytest
from PySide6.QtCore import QCoreApplication
from PySide6.QtTest import QTest
from test_emulator_playlists import entry, write_playlist
from test_games_catalog import installed

from udeck.apps.common.state import AppState
from udeck.apps.emulator.library import EmulatorLibrary


@pytest.fixture
def application():
    return QCoreApplication.instance() or QCoreApplication([])


def refresh(library):
    library.refresh()
    deadline = time.monotonic() + 5
    while library.pending and time.monotonic() < deadline:
        QTest.qWait(10)
    assert not library.pending


def test_refresh_never_scans_unlisted_roms_and_keeps_missing_list_entries(application, tmp_path):
    root = tmp_path / "roms/Nintendo - Game Boy"
    root.mkdir(parents=True)
    (root / "Unlisted.gb").write_bytes(b"original")
    lists = tmp_path / "playlists"
    write_playlist(lists / "Favorites.lpl", [entry(root / "Missing.gb")])
    state = AppState("emulator", tmp_path / "state")
    state.data["preferences"].update(romRoot=str(root.parent), playlistDirectory=str(lists), emulatorSchema=3)
    library = EmulatorLibrary(state, installed(tmp_path, {}))
    try:
        refresh(library)
        assert len(library.items) == 1 and library.items[0]["path"].endswith("Missing.gb")
        assert library.items[0]["contentError"]
        assert library.playlists[0]["title"] == "Favorites"
    finally:
        library.close()
        state.close()


def test_refresh_keeps_last_good_collection_when_its_json_becomes_invalid(application, tmp_path):
    game = tmp_path / "roms/Original.gb"
    game.parent.mkdir()
    game.write_bytes(b"original")
    path = write_playlist(tmp_path / "playlists/Custom.lpl", [entry(game)])
    state = AppState("emulator", tmp_path / "state")
    state.data["preferences"].update(romRoot=str(game.parent), playlistDirectory=str(path.parent), emulatorSchema=3)
    library = EmulatorLibrary(state, installed(tmp_path, {}))
    try:
        refresh(library)
        identity = library.items[0]["id"]
        path.write_text("broken")
        refresh(library)
        assert library.items[0]["id"] == identity
        assert library.playlists[0]["error"]
    finally:
        library.close()
        state.close()


def test_corrupt_identity_registry_blocks_refresh_and_preserves_the_file(application, tmp_path):
    state = AppState("emulator", tmp_path / "state")
    state.path.parent.mkdir(parents=True)
    registry = state.path.parent / "emulator-identities.json"
    registry.write_text("{broken registry")
    library = EmulatorLibrary(state, installed(tmp_path, {}))
    try:
        refresh(library)
        assert library.errors and "emulator-identities.json" in str(library.errors)
        assert registry.read_text() == "{broken registry"
    finally:
        library.close()
        state.close()
