import json
from copy import deepcopy

import pytest
from test_wifi_ui import choose
from test_wifi_ui import controller as controller_fixture

controller = controller_fixture


def open_hotspot(control, identifier="usb"):
    control.activateSetting("hotspot")
    choose_device(control, identifier)


def choose_device(control, identifier):
    control.chooseModal(next(i for i, item in enumerate(control.modal["options"]) if item.get("deviceId") == identifier))


def configure_hotspot(control):
    choose(control, "hotspot-name")
    assert control.modal["text"].startswith("uDeck-")
    control.editText("My hotspot")
    control.dispatch("accept")
    assert control.modal["purpose"] == "hotspot-password"
    control.editText("test-only-password")
    assert "test-only-password" not in control.snapshotJson
    control.dispatch("accept")


def test_hotspot_is_reachable_from_settings_and_quick_settings(controller):
    assert any(item["id"] == "hotspot" for item in controller._settings())
    controller.dispatch("quick-settings")
    controller.chooseModal(next(i for i, item in enumerate(controller.modal["options"]) if item["id"] == "hotspot"))
    assert controller.modal["source"] == "hotspot"
    choose_device(controller, "usb")
    assert controller.modal["source"] == "hotspot-device"
    controller.dispatch("back")
    assert controller.modal["source"] == "hotspot"
    controller.dispatch("back")
    assert controller.modal["source"] == "quick-settings"


def test_configuration_start_stop_and_client_restoration_keep_the_menu(controller):
    open_hotspot(controller, "builtin")
    configure_hotspot(controller)
    assert controller.modal["source"] == "hotspot-device"
    assert "wifi_hotspot_configure" in controller.backend.actions
    choose(controller, "hotspot-start")
    assert controller.modal["kind"] == "confirm"
    assert controller.modal["index"] == 0
    assert "wifi_hotspot_start" not in controller.backend.actions
    controller.dispatch("right")
    controller.dispatch("accept")
    assert controller.modal["source"] == "hotspot-device"
    device = controller.data["wifi"]["devices"][0]
    assert device["hotspot"]["status"] == "active"
    assert device["mode"] == "ap"
    assert all(item.get("disabled") for item in controller.modal["options"] if item["action"] in ("hotspot-name", "hotspot-password"))
    state = json.loads(controller.snapshotJson)
    assert state["wifiIndicators"][0]["kind"] == "hotspot"
    choose(controller, "hotspot-stop")
    device = controller.data["wifi"]["devices"][0]
    assert device["hotspot"]["status"] == "off"
    assert device["connected"] == "Workshop"
    assert controller.modal["source"] == "hotspot-device"


def test_settings_keep_running_hotspot_count_when_stopping_fails(controller):
    controller.setPage("settings")
    open_hotspot(controller)
    configure_hotspot(controller)
    choose(controller, "hotspot-start")
    controller.backend.state["wifi"]["devices"][1]["hotspot"].update(status="failed", message="Stopping denied")
    controller.backend.updated.emit({"wifi": deepcopy(controller.backend.state["wifi"])})
    state = json.loads(controller.snapshotJson)
    hotspot = next(item for item in state["items"] if item["id"] == "hotspot")
    assert hotspot["subtitle"] == "1 hotspots on"
    assert state["wifiIndicators"][1]["status"] == "failed"
    choose(controller, "hotspot-stop")
    hotspot = next(item for item in json.loads(controller.snapshotJson)["items"] if item["id"] == "hotspot")
    assert hotspot["subtitle"] == "Hotspots off"


def test_invalid_ssid_and_password_preserve_input_without_saving(controller):
    open_hotspot(controller)
    choose(controller, "hotspot-name")
    controller.editText("网" * 11)
    controller.dispatch("accept")
    assert controller.modal["error"]
    assert controller.modal["text"] == "网" * 11
    controller.editText("Pocket")
    controller.dispatch("accept")
    controller.editText("short")
    controller.dispatch("accept")
    assert controller.modal["error"]
    assert "wifi_hotspot_configure" not in controller.backend.actions
    assert "short" not in controller.snapshotJson
    controller.dispatch("context")
    assert controller.modal["reveal"]
    controller.dispatch("back")
    assert "short" not in controller.viewSnapshotJson


@pytest.mark.parametrize("change", ["unplug", "restart"])
def test_hotspot_password_entry_is_dismissed_on_device_or_service_change(controller, change):
    open_hotspot(controller)
    choose(controller, "hotspot-password")
    controller.editText("private-input")
    wifi = deepcopy(controller.data["wifi"])
    if change == "unplug":
        wifi["devices"] = [item for item in wifi["devices"] if item["id"] != "usb"]
    else:
        wifi["epoch"] = "replacement"
    controller.backend.updated.emit({"wifi": wifi})
    assert controller.modal["source"] == "hotspot"
    assert "private-input" not in controller.viewSnapshotJson
    assert "wifi_hotspot_configure" not in controller.backend.actions


def test_normal_wifi_actions_are_disabled_until_hotspot_is_stopped(controller):
    open_hotspot(controller)
    configure_hotspot(controller)
    choose(controller, "hotspot-start")
    controller._cancel_modals()
    controller.activateSetting("wifi")
    choose_device(controller, "usb")
    actions = {item["action"] for item in controller.modal["options"] if not item.get("disabled")}
    assert "wifi-disconnect" not in actions
    assert "wifi-connect" not in actions
    assert "hotspot-device" in actions
