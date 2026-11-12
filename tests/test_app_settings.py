"""Settings reached through shortcuts must expose the same state as Settings."""

import json

import pytest
from PySide6.QtCore import QCoreApplication
from test_games_catalog import installed

from udeck.apps.browser.controller import BrowserController
from udeck.apps.common.controller import AppController
from udeck.apps.emulator.controller import EmulatorController
from udeck.apps.reader.controller import ReaderController


@pytest.fixture
def application():
    return QCoreApplication.instance() or QCoreApplication([])


@pytest.mark.parametrize("entry", ["settings", "shortcut", "detail"])
def test_core_toggle_is_visible_and_updates_from_every_entry(application, tmp_path, entry):
    controller = EmulatorController(tmp_path / "state", tmp_path / "settings.json")
    catalog = installed(tmp_path, {"gambatte": {"supported_extensions": "gb"}})
    controller.store.data["preferences"] = catalog.preferences
    controller.catalog = controller.library.catalog = catalog
    try:
        if entry == "settings":
            controller.settings()
            controller.choose(2)
        elif entry == "shortcut":
            controller.command("core-management")
        if entry != "detail":
            controller.platform_cores_menu("gb")
            controller.choose(0)
        else:
            controller.core_details("gambatte", "gb")
        menu = json.loads(controller.snapshotJson)["menu"]
        assert menu["settings"]  # The QML delegate only renders switches in this layout.
        assert menu["options"][0]["checked"] is True
        controller.choose(0)
        menu = json.loads(controller.snapshotJson)["menu"]
        assert menu["settings"] and menu["options"][0]["checked"] is False
        assert not catalog.enabled(catalog.cores["gambatte"], "gb")
        controller.choose(0)
        assert json.loads(controller.snapshotJson)["menu"]["options"][0]["checked"] is True
        assert catalog.enabled(catalog.cores["gambatte"], "gb")
    finally:
        controller.close()


def test_browser_context_mode_exposes_current_choice(application, tmp_path):
    controller = BrowserController(tmp_path, tmp_path / "settings.json")
    try:
        controller.web_mode = "pointer"
        controller.context()
        parent = controller.menus[-1]
        controller.choose(5)
        menu = json.loads(controller.snapshotJson)["menu"]
        assert menu["settings"]
        assert [row["current"] for row in menu["options"]] == [False, False, True, False]
        controller.dispatch("back")
        assert controller.menus == [parent] and not parent["settings"]
        assert parent["index"] == 5
    finally:
        controller.close()


def test_reader_context_layout_updates_values_without_restylizing_actions(application, tmp_path):
    controller = ReaderController(tmp_path, tmp_path / "settings.json")
    controller.current = {"format": "TXT"}
    controller.page = "document"
    try:
        controller.context()
        parent = controller.menus[-1]
        controller.choose(1)
        layout = controller.menus[-1]
        assert layout["settings"]
        controller.choose(0)
        controller.choose(3)
        assert controller.line_height == 1.8
        assert controller.menus[-1] is layout and layout["options"][0]["subtitle"] == "1.8×"
        controller.dispatch("back")
        assert controller.menus == [parent] and not parent["settings"]
        assert parent["index"] == 1
    finally:
        controller.current = None
        controller.close()


def test_dynamic_settings_rebind_actions_and_remove_stale_callbacks(application, tmp_path):
    controller = AppController("browser", tmp_path, tmp_path / "settings.json")
    values, calls = ["first", "second"], []
    try:
        controller.menu("Settings", lambda: [(value, lambda value=value: calls.append(value))
                                             for value in values], settings=True)
        controller.menus[-1]["index"] = 1
        values[:] = ["replacement"]
        controller.publish()
        controller.dispatch("accept")
        assert calls == ["replacement"]
        values.clear()
        controller.publish()
        controller.dispatch("accept")  # Empty menus retain an operable Back action.
        assert not controller.menus and not controller._callbacks
    finally:
        controller.close()
