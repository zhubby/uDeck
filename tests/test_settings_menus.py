"""Settings stay application-scoped while using the shared desktop icon path."""

import json
from copy import deepcopy

import pytest
from PySide6.QtWidgets import QApplication

from udeck.apps.runtime import make_controller
from udeck.controller import ShellController
from udeck.core import ConfigStore
from udeck.mock import MockBackend


@pytest.fixture(scope="module")
def application():
    return QApplication.instance() or QApplication([])


@pytest.mark.parametrize("app", ["music", "video", "browser", "reader", "emulator"])
def test_application_settings_do_not_offer_global_language(application, tmp_path, app, monkeypatch):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    config_path = tmp_path / "settings.json"
    config = ConfigStore(config_path)
    config.data["preferences"]["language"] = "en"
    config.save()
    controller = make_controller(app, tmp_path / app, config_path)
    try:
        controller.command("settings")
        menu = json.loads(controller.snapshotJson)["menu"]
        assert menu["title"] == "Settings"
        assert "Language" not in [row["title"] for row in menu["options"]]
        assert all(row.get("icon") for row in menu["options"])
        controller.dispatch("back")
        assert not controller.menus
        assert ConfigStore(config_path).data["preferences"]["language"] == "en"
    finally:
        controller.close()
        application.processEvents()


def test_global_language_stays_in_system_settings(application, tmp_path):
    controller = ShellController(MockBackend(), config=ConfigStore(tmp_path / "settings.json"), mock=True)
    try:
        controller.setPage("settings")
        controller.select(next(i for i, row in enumerate(controller._items()) if row["id"] == "language"))
        controller.dispatch("accept")
        options = json.loads(controller.snapshotJson)["modal"]["options"]
        assert all(row.get("icon") for row in options)
        controller.chooseModal(next(i for i, row in enumerate(options) if row["id"] == "zh_CN"))
        assert controller.language == "zh_CN"
        assert all(row.get("singleLine") and row.get("icon") for row in controller.modal["options"])
    finally:
        controller.close()


@pytest.fixture
def shell(application, tmp_path):
    controller = ShellController(MockBackend(), config=ConfigStore(tmp_path / "settings.json"), mock=True)
    yield controller
    controller.close()


@pytest.mark.parametrize("setting", ["wifi", "hotspot", "bluetooth", "volume", "output", "microphone",
                                     "language", "theme", "timezone", "shortcuts"])
def test_settings_children_use_inline_rows_while_main_keeps_descriptions(shell, setting):
    assert all(row.get("subtitle") and not row.get("singleLine") for row in shell._settings())
    shell.activateSetting(setting)
    assert all(row.get("singleLine") and row.get("icon") for row in shell.modal["options"])
    # A network adapter remains navigation, rather than a switch that could disconnect it.
    for row in shell.modal["options"]:
        if row.get("action") in ("wifi-device", "hotspot-device", "device"):
            assert row["navigate"] and "checked" not in row


def test_wifi_switch_preserves_confirmation_and_waits_for_actual_device_state(shell, monkeypatch):
    shell.activateSetting("wifi")
    owner = shell.modal["key"]
    assert shell.modal["options"][0]["checked"] is True
    shell.chooseModal(0)
    assert shell.modal["kind"] == "confirm" and shell.modal["index"] == 0
    shell.dispatch("back")
    assert shell.modal["key"] == owner and shell.modal["options"][0]["checked"] is True
    assert "wifi_power" not in shell.backend.actions

    requests = []
    monkeypatch.setattr(shell.backend, "request", lambda action, payload: requests.append((action, payload)))
    shell.chooseModal(0)
    shell.dispatch("right")
    shell.dispatch("accept")
    assert requests[0][0] == "wifi_power" and requests[0][1]["enabled"] is False
    assert "wifi_power" in shell.pending_system
    assert shell.modal["key"] == owner and shell.modal["options"][0]["checked"] is True
    shell.backend.operationFailed.emit("wifi_power", "Power change denied")
    assert "wifi_power" not in shell.pending_system
    assert shell.modal["options"][0]["checked"] is True
    wifi = deepcopy(shell.data["wifi"])
    wifi["enabled"] = False
    shell.backend.updated.emit({"wifi": wifi})
    assert shell.modal["options"][0]["checked"] is False
    assert shell.modal["key"] == owner and shell.modal["index"] == 0


@pytest.mark.parametrize(("setting", "action"), [("volume", "mute"), ("microphone", "audio_input_mute"),
                                                  ("bluetooth", "bluetooth_power")])
def test_switch_updates_from_backend_without_closing_its_menu(shell, setting, action):
    shell.activateSetting(setting)
    owner = shell.modal["key"]
    index = next(i for i, row in enumerate(shell.modal["options"]) if row.get("systemAction") == action)
    before = shell.modal["options"][index]["checked"]
    shell.chooseModal(index)
    assert action in shell.backend.actions
    assert shell.modal["options"][index]["checked"] is not before
    assert shell.modal["key"] == owner and shell.modal["index"] == index


def test_hotspot_switch_uses_actual_ap_mode_during_progress_and_failed_stop(shell):
    shell.activateSetting("hotspot")
    shell.chooseModal(next(i for i, row in enumerate(shell.modal["options"]) if row.get("deviceId") == "usb"))
    owner = shell.modal["key"]
    assert shell.modal["options"][0]["checked"] is False
    wifi = deepcopy(shell.data["wifi"])
    device = next(device for device in wifi["devices"] if device["id"] == "usb")
    device["hotspot"].update(status="starting", owned=True)
    shell.backend.updated.emit({"wifi": wifi})
    assert shell.modal["options"][0]["checked"] is False
    assert shell.modal["options"][0]["disabled"] is True
    device["mode"] = "ap"
    device["hotspot"].update(status="failed", message="Stopping denied")
    shell.backend.updated.emit({"wifi": deepcopy(wifi)})
    assert shell.modal["options"][0]["checked"] is True
    assert shell.modal["options"][0]["action"] == "hotspot-stop"
    assert any(row["label"] == "Stopping denied" for row in shell.modal["options"])
    assert shell.modal["key"] == owner
    device["hotspot"].update(status="external", owned=False)
    shell.backend.updated.emit({"wifi": deepcopy(wifi)})
    assert shell.modal["options"][0]["checked"] is True
    assert shell.modal["options"][0]["disabled"] is True


def test_shortcut_refresh_keeps_inline_presentation_and_selection(shell):
    shell.activateSetting("shortcuts")
    shell.chooseModal(0)
    shell.chooseModal(0)
    shell.chooseModal(next(i for i, row in enumerate(shell.modal["options"]) if row["id"] == "clear"))
    assert shell.modal["source"] == "shortcut-action"
    assert shell.modal["options"][shell.modal["index"]]["id"] == "clear"
    assert all(row.get("singleLine") and row.get("icon") for row in shell.modal["options"])
