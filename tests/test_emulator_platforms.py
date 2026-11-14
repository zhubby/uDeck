"""Standard platform playlists retain navigation when core availability changes."""

import json

import pytest
from libretro_fixtures import configure_library
from test_emulator_playlist_browser import wait_for
from test_emulator_playlists import write_playlist
from test_games_catalog import installed

from udeck.apps.emulator.controller import EmulatorController


@pytest.fixture
def platform_browser(qt_application, tmp_path):
    catalog = installed(tmp_path, {
        "gambatte": {"supported_extensions": "gb|gbc"},
        "mgba": {"supported_extensions": "gba|gb|gbc"},
        "vba_next": {"supported_extensions": "gba"},
        "nestopia": {"supported_extensions": "nes"},
        "ppsspp": {"supported_extensions": "iso|cso"},
    }, {"coreEnabled": {"ppsspp": False}})
    controller = EmulatorController(tmp_path / "state", tmp_path / "settings.json")
    controller.store.data["preferences"].update(catalog.preferences)
    catalog.preferences = controller.store.data["preferences"]
    controller.catalog = controller.library.catalog = catalog
    root = tmp_path / "Games"
    for directory, title in [("gb", "Stripes.gb"), ("gba", "Orbit.gba"),
                             ("fc", "Alpha.nes"), ("nes", "Beta.nes")]:
        folder = root / directory
        folder.mkdir(parents=True, exist_ok=True)
        (folder / title).write_bytes(b"Original navigation fixture")
    write_playlist(tmp_path / "playlists/Sony - PlayStation Portable.lpl", [])
    configure_library(controller, root)
    wait_for(lambda: not controller.library.pending)
    controller.setTab(1)
    yield controller
    controller.close()


def platform_rows(controller):
    rows = controller.snapshot()["cards"]
    assert all(row["kind"] == "playlist" for row in rows)
    return {controller.catalog.platform_for_database(row["title"]).id: row for row in rows}


def enter_platform(controller, platform):
    row = platform_rows(controller)[platform]
    controller.select(row["id"])
    controller.dispatch("accept")


def test_platform_playlists_include_empty_even_when_core_is_disabled(platform_browser):
    controller = platform_browser
    assert {p: r["gameCount"] for p, r in platform_rows(controller).items()} == {
        "gb": 1, "gba": 1, "nes": 2, "psp": 0}
    controller.catalog.preferences["coreEnabled"]["ppsspp"] = True
    controller.publish()
    assert platform_rows(controller)["psp"]["gameCount"] == 0


def test_multi_platform_core_switches_do_not_remove_lists(platform_browser):
    controller = platform_browser
    controller.catalog.preferences["coreEnabled"]["gambatte"] = False
    controller.publish()
    assert set(platform_rows(controller)) == {"gb", "gba", "nes", "psp"}
    controller.catalog.preferences["coreEnabled"]["mgba"] = True
    controller.publish()
    assert platform_rows(controller)["gb"]["gameCount"] == 1


def test_last_core_disabled_keeps_playlist_focus_and_core_settings(platform_browser):
    controller = platform_browser
    key = platform_rows(controller)["nes"]["id"]
    controller.select(key)
    controller.core_details("nestopia", "nes")
    controller.toggle_core("nestopia", False, "nes")
    assert "nes" in platform_rows(controller) and controller.selected == key
    assert controller.menus[-1]["coreId"] == "nestopia"


def test_playlist_enter_and_back_restore_selection_and_search(platform_browser):
    controller = platform_browser
    controller.search("Entertainment")
    assert set(platform_rows(controller)) == {"nes"}
    key = platform_rows(controller)["nes"]["id"]
    enter_platform(controller, "nes")
    assert controller.platform == key and not controller.filter
    assert {r["title"] for r in controller.rows()} == {"Alpha", "Beta"}
    controller.search("Beta")
    controller.select(controller.rows()[0]["id"])
    controller.dispatch("accept")
    assert controller.page == "game-details" and controller.current["title"] == "Beta"
    controller.dispatch("back")
    assert controller.page == "library" and controller.platform == key
    controller.dispatch("back")
    assert controller.platform == "All" and controller.filter == "Entertainment"
    assert controller.selected == key
    enter_platform(controller, "nes")
    assert controller.filter == "Beta" and controller.selected == controller.rows()[0]["id"]


def test_recent_and_favorites_do_not_inherit_collection_or_search(platform_browser):
    controller = platform_browser
    game = next(r for r in controller.library.items if r["platform"] == "gba")
    controller.store.data["recent"] = [game["id"]]
    controller.store.data["favorites"] = [game["id"]]
    key = platform_rows(controller)["nes"]["id"]
    enter_platform(controller, "nes")
    controller.search("Alpha")
    for tab in (0, 2):
        controller.setTab(tab)
        assert controller.platform == "All" and not controller.filter
        assert [r["gameId"] for r in controller.rows()] == [game["id"]]
        controller.dispatch("accept")
        assert controller.page == "game-details" and controller.current["id"] == game["id"]
    controller.setTab(1)
    assert controller.platform == "All" and controller.selected == key


def test_empty_list_hint_is_independent_of_enabled_cores(platform_browser):
    controller = platform_browser
    enter_platform(controller, "psp")
    state = json.loads(controller.snapshotJson)
    assert state["count"] == 0 and state["playlistTitle"] == "Sony - PlayStation Portable"
    assert "playlist" in state["emptyHint"].lower()
    controller.dispatch("back")
    controller.catalog.preferences["coreEnabled"] = {key: False for key in controller.catalog.cores}
    controller.publish()
    assert len(json.loads(controller.snapshotJson)["cards"]) == 4


def test_playlist_card_cannot_be_favorited(platform_browser):
    controller = platform_browser
    controller.toggle_favorite()
    assert controller.store.data["favorites"] == []
    controller.context()
    labels = [str(row["title"]) for row in controller.menus[-1]["options"]]
    assert "Toggle favorite" not in labels


def test_disabling_core_keeps_active_collection_and_reports_unavailable_game(platform_browser):
    controller = platform_browser
    enter_platform(controller, "nes")
    key = controller.platform
    controller.core_details("nestopia", "nes")
    controller.toggle_core("nestopia", False, "nes")
    controller.clear_menus()
    controller.publish()
    assert controller.page == "library" and controller.platform == key
    controller.dispatch("accept")
    assert not controller.checks["ready"]


def test_snapshot_stays_in_collection_when_core_probe_fails(platform_browser):
    controller = platform_browser
    enter_platform(controller, "nes")
    key = controller.platform
    controller.catalog.apply_probe("nestopia", {"status": "incompatible", "reason": "Fixture failure"})
    state = json.loads(controller.snapshotJson)
    assert state["platform"] == key and not state["platformsView"]
    assert state["count"] == 2


def test_returning_from_details_preserves_collection_after_core_disable(platform_browser):
    controller = platform_browser
    enter_platform(controller, "nes")
    key = controller.platform
    controller.dispatch("accept")
    controller.core_details("nestopia", "nes")
    controller.toggle_core("nestopia", False, "nes")
    controller.clear_menus()
    controller.dispatch("back")
    state = json.loads(controller.snapshotJson)
    assert not state["platformsView"] and state["platform"] == key
