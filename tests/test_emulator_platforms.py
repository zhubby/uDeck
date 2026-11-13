"""Platform navigation follows enabled cores, independently of ROM counts."""

import json
from pathlib import Path

import pytest
from test_games_catalog import installed

from udeck.apps.common.library import Source
from udeck.apps.emulator.controller import EmulatorController
from udeck.apps.emulator.library import scan_games


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
    source = Source.create(root)
    controller.library.sources = [source]
    controller.library.root_id, controller.library.root_path = source.id, str(root)
    controller.library.items = scan_games(source, catalog).items
    controller.setTab(1)
    yield controller
    controller.close()


def platform_rows(controller):
    rows = controller.snapshot()["cards"]
    assert all(row["kind"] == "platform" for row in rows)
    return {row["platformId"]: row for row in rows}


def enter_platform(controller, platform):
    row = platform_rows(controller)[platform]
    controller.select(row["id"])
    controller.dispatch("accept")


def test_platforms_include_enabled_empty_and_exclude_disabled_installed(platform_browser):
    controller = platform_browser
    assert {p: r["gameCount"] for p, r in platform_rows(controller).items()} == {
        "gb": 1, "gba": 1, "nes": 2}
    controller.catalog.preferences["coreEnabled"]["ppsspp"] = True
    controller.publish()
    rows = platform_rows(controller)
    assert rows["psp"]["gameCount"] == 0
    assert rows["psp"]["subtitle"] == "0 games"
    assert rows["nes"]["id"] == "platform:nes"


def test_multi_platform_core_uses_same_defaults_as_settings(platform_browser):
    controller = platform_browser
    controller.catalog.preferences["coreEnabled"]["gambatte"] = False
    controller.publish()
    assert set(platform_rows(controller)) == {"gba", "nes"}
    controller.catalog.preferences["coreEnabled"]["mgba"] = True
    controller.catalog.preferences["coreEnabled"]["vba_next"] = True
    controller.publish()
    assert set(platform_rows(controller)) == {"gb", "gba", "nes"}


def test_last_core_disabled_hides_platform_with_games_and_reconciles_focus(platform_browser):
    controller = platform_browser
    controller.select(platform_rows(controller)["nes"]["id"])
    controller.core_details("nestopia", "nes")
    controller.toggle_core("nestopia", False, "nes")
    rows = platform_rows(controller)
    assert set(rows) == {"gb", "gba"}
    assert controller.selected == "platform:gba"
    assert controller.menus[-1]["coreId"] == "nestopia"


def test_platform_enter_and_back_restore_selection_and_search(platform_browser):
    controller = platform_browser
    controller.search("fc")
    assert set(platform_rows(controller)) == {"nes"}
    enter_platform(controller, "nes")
    assert controller.platform == "nes" and not controller.filter
    assert {r["title"] for r in controller.rows()} == {"Alpha", "Beta"}
    controller.search("Beta")
    controller.select(controller.rows()[0]["id"])
    controller.dispatch("accept")
    assert controller.page == "game-details" and controller.current["title"] == "Beta"
    controller.dispatch("back")
    assert controller.page == "library" and controller.platform == "nes"
    controller.dispatch("back")
    assert controller.platform == "All" and controller.filter == "fc"
    assert controller.selected == "platform:nes"
    enter_platform(controller, "nes")
    assert controller.filter == "Beta" and controller.selected == controller.rows()[0]["id"]


def test_recent_and_favorites_do_not_inherit_platform_or_search(platform_browser):
    controller = platform_browser
    game = next(r for r in controller.library.items if r["platform"] == "gba")
    controller.store.data["recent"] = [game["id"]]
    controller.store.data["favorites"] = [game["id"]]
    enter_platform(controller, "nes")
    controller.search("Alpha")
    for tab in (0, 2):
        controller.setTab(tab)
        assert controller.platform == "All" and not controller.filter
        assert [r["id"] for r in controller.rows()] == [game["id"]]
        controller.dispatch("accept")
        assert controller.page == "game-details" and controller.current["id"] == game["id"]
    controller.setTab(1)
    assert controller.platform == "All" and controller.selected == "platform:nes"


def test_empty_platform_and_no_enabled_platform_have_specific_hints(platform_browser):
    controller = platform_browser
    controller.catalog.preferences["coreEnabled"]["ppsspp"] = True
    enter_platform(controller, "psp")
    state = json.loads(controller.snapshotJson)
    assert state["count"] == 0 and state["platformTitle"] == "PlayStation Portable"
    assert str(Path(controller.library.root_path) / "psp") in state["emptyHint"]
    controller.dispatch("back")
    controller.catalog.preferences["coreEnabled"] = {key: False for key in controller.catalog.cores}
    controller.publish()
    state = json.loads(controller.snapshotJson)
    assert state["cards"] == [] and "enable" in state["emptyHint"].lower()


def test_platform_card_cannot_be_favorited_and_has_no_old_platform_filter(platform_browser):
    controller = platform_browser
    controller.toggle_favorite()
    assert controller.store.data["favorites"] == []
    controller.context()
    labels = [str(row["title"]) for row in controller.menus[-1]["options"]]
    assert "Platform filter" not in labels and "Toggle favorite" not in labels


def test_disabling_active_platform_returns_to_platform_list(platform_browser):
    controller = platform_browser
    enter_platform(controller, "nes")
    controller.core_details("nestopia", "nes")
    controller.toggle_core("nestopia", False, "nes")
    controller.clear_menus()
    controller.publish()
    assert controller.page == "library" and controller.platform == "All"
    assert set(platform_rows(controller)) == {"gb", "gba"}
    assert controller.selected == "platform:gba"


def test_snapshot_is_consistent_when_core_probe_removes_the_current_platform(platform_browser):
    controller = platform_browser
    enter_platform(controller, "nes")
    controller.catalog.apply_probe("nestopia", {"status": "incompatible", "reason": "Fixture failure"})
    state = json.loads(controller.snapshotJson)
    assert state["platform"] == "All" and state["platformsView"]
    assert {row["kind"] for row in state["cards"]} == {"platform"}
    assert state["count"] == 2
    assert state["selected"] == "platform:gba"
