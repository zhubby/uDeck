"""Collection navigation, labels, shared saves and explicit generation."""

import json
import time
import zipfile
from pathlib import Path

import pytest
from PySide6.QtCore import QCoreApplication
from PySide6.QtTest import QTest
from test_emulator_playlists import entry, write_playlist
from test_games_catalog import installed

from udeck.apps.emulator.controller import EmulatorController, content_hash


def wait_for(predicate):
    deadline = time.monotonic() + 5
    while not predicate() and time.monotonic() < deadline:
        QTest.qWait(10)
    assert predicate()


@pytest.fixture
def browser(tmp_path):
    application = QCoreApplication.instance() or QCoreApplication([])
    controller = EmulatorController(tmp_path / "state", tmp_path / "settings.json")
    root = tmp_path / "roms/Nintendo - Game Boy"
    root.mkdir(parents=True)
    game = root / "Original.gb"
    game.write_bytes(b"original")
    catalog = installed(tmp_path, {"gambatte": {"supported_extensions": "gb|gbc"},
                                   "sameboy": {"supported_extensions": "gb|gbc"}},
                        {"romRoot": str(root.parent), "playlistDirectory": str(tmp_path / "playlists"),
                         "coreEnabled": {"sameboy": True}, "emulatorSchema": 3})
    controller.store.data["preferences"] = catalog.preferences
    controller.catalog = controller.library.catalog = catalog
    controller.library.root_path = str(root.parent)
    controller.library.playlist_path = str(tmp_path / "playlists")
    write_playlist(tmp_path / "playlists/A custom.lpl", [entry(game, "Custom name")])
    write_playlist(tmp_path / "playlists/B other.lpl", [entry(game, "Another name")])
    write_playlist(tmp_path / "playlists/C empty.lpl", [])
    controller.library.refresh()
    wait_for(lambda: not controller.library.pending)
    controller.setTab(1)
    yield controller, game, application
    controller.close()


def test_cards_follow_playlists_including_empty_lists_and_disabled_cores(browser):
    controller, _, _ = browser
    assert [r["title"] for r in controller.rows()] == ["A custom", "B other", "C empty"]
    assert controller.rows()[2]["gameCount"] == 0
    controller.catalog.preferences["coreEnabled"] = {"gambatte": False, "sameboy": False}
    controller.library.refresh()
    wait_for(lambda: not controller.library.pending)
    assert len(controller.rows()) == 3


def test_collection_search_back_focus_and_tabs_are_independent(browser):
    controller, _, _ = browser
    controller.search("custom")
    card = controller.rows()[0]
    controller.select(card["id"])
    controller.activate(card)
    assert controller.rows()[0]["title"] == "Custom name"
    controller.search("name")
    controller.back()
    assert controller.selected == card["id"] and controller.filter == "custom"
    controller.setTab(2)
    assert controller.filter == ""
    controller.setTab(1)
    assert controller.filter == "custom"


def test_duplicate_memberships_share_favorites_saves_but_keep_their_labels(browser):
    controller, _, _ = browser
    cards = controller.rows()
    controller.activate(cards[0])
    row = controller.rows()[0]
    controller.select(row["id"])
    controller.toggle_favorite()
    controller.open_item(row["id"])
    game_id, save_root = controller.current["id"], controller.game_root()
    controller.back()
    controller.back()
    controller.activate(cards[1])
    controller.open_item(controller.rows()[0]["id"])
    assert controller.current["title"] == "Another name"
    assert controller.current["id"] == game_id and controller.game_root() == save_root
    controller.setTab(2)
    assert len(controller.rows()) == 1
    assert controller.store.data["favorites"] == [game_id]


def test_core_selection_edits_only_the_selected_playlist_entry(browser):
    controller, _, _ = browser
    controller.activate(controller.rows()[0])
    controller.open_item(controller.rows()[0]["id"])
    controller.set_game_core("sameboy")
    value = json.loads(Path(controller.current["playlistPath"]).read_text())
    assert value["items"][0]["core_path"].endswith("sameboy_libretro.so")
    assert controller.catalog.resolve(controller.current).id == "sameboy"
    other = Path(controller.library.playlist_path) / "B other.lpl"
    assert json.loads(other.read_text())["items"][0]["core_path"] == "DETECT"


def test_archive_members_have_distinct_content_hashes_and_save_basenames(tmp_path):
    archive = tmp_path / "games.zip"
    with zipfile.ZipFile(archive, "w") as stream:
        stream.writestr("folder/One.gb", b"one")
        stream.writestr("Two.gb", b"two")
    first = {"path": str(archive), "archiveMember": "folder/One.gb", "basename": "One"}
    second = {"path": str(archive), "archiveMember": "Two.gb", "basename": "Two"}
    assert content_hash(first) != content_hash(second)


def test_scan_preview_writes_nothing_until_user_accepts(browser):
    controller, game, _ = browser
    path = Path(controller.library.playlist_path) / "Nintendo - Game Boy.lpl"
    controller.preview_scan()
    wait_for(lambda: controller.library_task is None)
    assert not path.exists()
    assert controller.menus[-1]["options"][0]["disabled"] is False
    controller.dispatch("accept")
    wait_for(lambda: controller.library_task is None and not controller.library.pending)
    assert json.loads(path.read_text())["items"][0]["path"] == str(game)
    assert len(controller.library.playlists) == 4


def test_playlist_default_core_edit_refuses_external_changes(browser):
    controller, _, _ = browser
    controller.activate(controller.rows()[0])
    path = Path(controller.library.playlist_path) / "A custom.lpl"
    external = json.loads(path.read_text())
    external["default_core_name"] = "Other application"
    path.write_text(json.dumps(external))
    with pytest.raises(ValueError, match="changed|modified"):
        controller.set_playlist_core("sameboy")
    assert json.loads(path.read_text()) == external


def test_corrupt_migration_journal_opens_recovery_without_scanning_or_overwriting(tmp_path):
    application = QCoreApplication.instance() or QCoreApplication([])
    state = tmp_path / "state"
    state.mkdir()
    journal = state / "emulator-migration.json"
    journal.write_text("{broken journal")
    controller = EmulatorController(state, tmp_path / "settings.json")
    try:
        assert application and controller.migration_pending and controller.library.suspended
        controller.library.refresh()
        assert not controller.library.pending
        assert journal.read_text() == "{broken journal"
        assert "emulator-migration.json" in str(controller.library.errors)
        with pytest.raises(RuntimeError):
            controller.preview_scan()
    finally:
        controller.close()


def test_opening_unlisted_files_previews_only_those_entries_before_publishing(browser):
    controller, game, _ = browser
    first, second, unrelated = (game.with_name(n + ".gb") for n in ("First", "Second", "Unrelated"))
    for path in (first, second, unrelated):
        path.write_bytes(b"original")
    controller.accept_file_paths([first, second])
    wait_for(lambda: controller.library_task is None)
    playlist = Path(controller.library.playlist_path) / "Nintendo - Game Boy.lpl"
    assert not playlist.exists()
    assert "First.gb" in str(controller.menus[-1]["body"])
    assert "Second.gb" in str(controller.menus[-1]["body"])
    assert "Unrelated.gb" not in str(controller.menus[-1]["body"])
    controller.dispatch("accept")
    wait_for(lambda: controller.library_task is None and not controller.library.pending)
    assert {i["path"] for i in json.loads(playlist.read_text())["items"]} == {str(first), str(second)}
