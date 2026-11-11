import json
import os
from copy import deepcopy

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QCoreApplication

from udeck.controller import ShellController
from udeck.core import ConfigStore
from udeck.i18n import render
from udeck.mock import MockBackend


@pytest.fixture
def controller(tmp_path):
    application = QCoreApplication.instance() or QCoreApplication([])
    control = ShellController(MockBackend(), config=ConfigStore(tmp_path / "config.json"), mock=True)
    control._test_application = application
    yield control
    control.close()


def choose(control, action):
    index = next(index for index, option in enumerate(control.modal["options"]) if option["action"] == action)
    control.chooseModal(index)


def open_usb(control):
    control.activateSetting("wifi")
    options = control.modal["options"]
    index = next(index for index, option in enumerate(options) if option.get("deviceId") == "usb")
    control.chooseModal(index)


def test_adapter_menu_lists_both_devices_and_connected_summary(controller):
    controller.activateSetting("wifi")
    adapters = [option for option in controller.modal["options"] if option["action"] == "wifi-device"]
    assert len(adapters) == 2
    assert {option["deviceId"] for option in adapters} == {"builtin", "usb"}
    assert "2 adapters" in json.loads(controller.snapshotJson)["wifiSummary"]
    assert "1 connected" in json.loads(controller.snapshotJson)["wifiSummary"]


def test_back_restores_usb_selection_and_parent_settings_page(controller):
    controller.setPage("settings")
    controller.select(3)
    open_usb(controller)
    assert controller.modal["deviceId"] == "usb"
    choose(controller, "wifi-saved")
    assert controller.modal["source"] == "wifi-saved"
    controller.dispatch("back")
    assert controller.modal["source"] == "wifi-device"
    controller.dispatch("back")
    assert controller.modal["source"] == "wifi"
    assert controller.modal["options"][controller.modal["index"]]["deviceId"] == "usb"
    controller.dispatch("back")
    assert not controller.modal
    assert controller.navigation.page == "settings"
    assert controller.navigation.index == 3


def test_scan_keeps_device_menu_open_and_uses_usb_payload(controller, monkeypatch):
    requests = []
    request = controller.backend.request

    def record(action, payload=None):
        requests.append((action, payload))
        request(action, payload)

    monkeypatch.setattr(controller.backend, "request", record)
    open_usb(controller)
    choose(controller, "system")
    assert requests == [("wifi_scan", {"deviceId": "usb", "wifiEpoch": controller.data["wifi"]["epoch"]})]
    assert controller.modal["source"] == "wifi-device"
    assert controller.modal["deviceId"] == "usb"


def test_connect_confirmation_keeps_target_and_network_menu(controller, monkeypatch):
    requests = []
    monkeypatch.setattr(controller.backend, "request", lambda action, payload: requests.append((action, payload)))
    open_usb(controller)
    choose(controller, "wifi-connect")
    choose(controller, "wifi-join")
    assert controller.modal["kind"] == "confirm"
    assert controller.modal["deviceId"] == "usb"
    assert "USB" in controller.modal["body"]
    controller.dispatch("right")
    controller.dispatch("accept")
    assert requests[0][0] == "wifi_connect"
    assert requests[0][1]["deviceId"] == "usb"
    assert controller.modal["source"] == "wifi-network"


def test_global_off_requires_confirmation_and_leaves_devices_visible(controller):
    controller.activateSetting("wifi")
    choose(controller, "wifi-power")
    assert controller.modal["kind"] == "confirm"
    assert "所有" in render(controller.modal["body"], "zh_CN")
    assert "wifi_power" not in controller.backend.actions
    controller.dispatch("right")
    controller.dispatch("accept")
    assert controller.data["wifi"]["enabled"] is False
    assert len([option for option in controller.modal["options"] if option["action"] == "wifi-device"]) == 2


@pytest.mark.parametrize("overlay", ["none", "confirm", "password"])
def test_unplug_returns_to_adapters_and_dismisses_only_target_overlays(controller, monkeypatch, overlay):
    replies = []
    monkeypatch.setattr(controller.backend, "reply", lambda token, value: replies.append((token, value)))
    open_usb(controller)
    if overlay == "confirm":
        choose(controller, "wifi-connect")
    elif overlay == "password":
        controller._agent_prompt({"kind": "text", "title": "密码", "token": "usb-password", "deviceId": "usb"})
    wifi = deepcopy(controller.data["wifi"])
    wifi["devices"] = [device for device in wifi["devices"] if device["id"] != "usb"]
    controller.backend.updated.emit({"wifi": wifi})
    assert controller.modal["source"] == "wifi"
    assert len(controller._modals) == len(controller.navigation.modal_owners) == 1
    assert "移除" in render(controller.toast, "zh_CN")
    if overlay == "password":
        assert replies == [("usb-password", None)]
    controller.dispatch("back")
    assert not controller.modal


def test_refresh_updates_parent_menu_under_network_confirmation(controller):
    open_usb(controller)
    choose(controller, "wifi-connect")
    choose(controller, "wifi-join")
    wifi = deepcopy(controller.data["wifi"])
    usb = next(device for device in wifi["devices"] if device["id"] == "usb")
    usb["connected"] = usb["networks"][0]["name"]
    usb["deviceState"] = 100
    usb["networks"][0]["connected"] = True
    controller.backend.updated.emit({"wifi": wifi})
    assert controller.modal["kind"] == "confirm"
    controller.dispatch("back")
    assert controller.modal["source"] == "wifi-network"
    assert "已连接" in render(controller.modal["body"], "zh_CN")


def test_network_refresh_preserves_focus_when_access_point_changes(controller):
    open_usb(controller)
    index = next(index for index, option in enumerate(controller.modal["options"]) if option["action"] == "wifi-connect")
    controller.modal["index"] = index
    wifi = deepcopy(controller.data["wifi"])
    usb = next(device for device in wifi["devices"] if device["id"] == "usb")
    name = usb["networks"][0]["name"]
    usb["networks"][0]["id"] = "new-ap-for-same-ssid"
    usb["networks"].reverse()
    controller.backend.updated.emit({"wifi": wifi})
    selected = controller.modal["options"][controller.modal["index"]]
    assert selected["network"]["name"] == name


def test_usb_insertion_preserves_the_open_builtin_menu_and_adapter_focus(controller):
    dual_wifi = deepcopy(controller.data["wifi"])
    single_wifi = deepcopy(dual_wifi)
    single_wifi["devices"] = single_wifi["devices"][:1]
    controller.backend.updated.emit({"wifi": single_wifi})
    controller.activateSetting("wifi")
    controller.chooseModal(1)
    assert controller.modal["deviceId"] == "builtin"
    controller.backend.updated.emit({"wifi": dual_wifi})
    assert controller.modal["source"] == "wifi-device"
    assert controller.modal["deviceId"] == "builtin"
    controller.dispatch("back")
    adapters = [option for option in controller.modal["options"] if option["action"] == "wifi-device"]
    assert {option["deviceId"] for option in adapters} == {"builtin", "usb"}
    assert controller.modal["options"][controller.modal["index"]]["deviceId"] == "builtin"


def test_mock_connection_on_usb_preserves_builtin_connection(controller):
    open_usb(controller)
    choose(controller, "wifi-connect")
    choose(controller, "wifi-join")
    controller.dispatch("right")
    controller.dispatch("accept")
    devices = {device["id"]: device for device in controller.data["wifi"]["devices"]}
    assert devices["builtin"]["connected"] == "Workshop"
    assert devices["usb"]["connected"]
    assert "2 connected" in json.loads(controller.snapshotJson)["wifiSummary"]


def test_connected_adapter_without_visible_ssid_can_still_be_disconnected(controller):
    controller.data["wifi"]["devices"][0].update({"connected": "", "networks": []})
    controller.activateSetting("wifi")
    index = next(index for index, option in enumerate(controller.modal["options"]) if option.get("deviceId") == "builtin")
    controller.chooseModal(index)
    assert "已连接" in render(controller.modal["body"], "zh_CN")
    assert any(option["action"] == "wifi-disconnect" for option in controller.modal["options"])
    assert "1 connected" in json.loads(controller.snapshotJson)["wifiSummary"]


def test_mock_releases_saved_profile_when_its_adapter_disconnects(controller):
    controller.backend.request("wifi_disconnect", {"deviceId": "builtin"})
    usb = next(device for device in controller.data["wifi"]["devices"] if device["id"] == "usb")
    assert not usb["saved"][0].get("blocked")
