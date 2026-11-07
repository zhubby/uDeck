"""Status indicators stay bound to their adapter and active connection."""

import json
from copy import deepcopy

import pytest
from PySide6.QtCore import QCoreApplication

from udeck.controller import ShellController
from udeck.core import ConfigStore
from udeck.mock import MockBackend


@pytest.fixture
def controller(tmp_path):
    application = QCoreApplication.instance() or QCoreApplication([])
    instance = ShellController(MockBackend(), config=ConfigStore(tmp_path / "settings.json"), mock=True)
    instance._test_application = application
    yield instance
    instance.close()


def indicators(controller):
    return json.loads(controller.snapshotJson).get("wifiIndicators", [])


def test_one_indicator_per_adapter_in_stable_hardware_order(controller):
    controller.data["wifi"]["devices"].reverse()
    entries = indicators(controller)
    assert [entry["id"] for entry in entries] == ["builtin", "usb"]
    assert [entry["status"] for entry in entries] == ["connected", "disconnected"]
    assert "wlan0" in entries[0]["label"]
    assert "Workshop" in entries[0]["label"]
    assert "wlx001122334455" in entries[1]["label"]
    assert entries[1]["strength"] is None
    assert entries[1]["level"] == 0


@pytest.mark.parametrize(("strength", "expected"), [(0, 0), (1, 1), (25, 1), (26, 2), (50, 2), (51, 3), (75, 3), (76, 4), (100, 4), (None, 0)])
def test_four_signal_levels_follow_the_connected_ap(controller, strength, expected):
    device = controller.data["wifi"]["devices"][0]
    device["strength"] = strength
    entries = indicators(controller)
    assert len(entries) == 2
    assert entries[0]["level"] == expected
    assert entries[0]["strength"] == strength
    assert entries[0]["status"] == "connected"


@pytest.mark.parametrize(("update", "enabled", "status"), [
    ({}, False, "off"),
    ({"managed": False}, True, "unmanaged"),
    ({"available": False, "error": "Read failed"}, True, "unavailable"),
    ({"connected": "", "deviceState": 60, "connecting": "Guest"}, True, "connecting"),
    ({"connected": "", "deviceState": 30}, True, "disconnected"),
])
def test_stale_signal_is_not_shown_for_nonconnected_states(controller, update, enabled, status):
    controller.data["wifi"]["enabled"] = enabled
    controller.data["wifi"]["devices"][0].update(update)
    entries = indicators(controller)
    assert len(entries) == 2
    assert entries[0]["status"] == status
    assert entries[0]["strength"] is None
    assert entries[0]["level"] == 0


def test_live_signal_hotplug_and_bluetooth_preserve_page_focus_and_text(controller):
    controller.setPage("apps")
    controller.select(3)
    controller.dispatch("search")
    controller.editText("keep my input")
    modal_key = controller.modal["key"]
    original = deepcopy(controller.data["wifi"])
    single = deepcopy(original)
    single["devices"] = single["devices"][:1]
    controller.backend.updated.emit({"wifi": single, "bluetooth": {"available": True, "powered": False}})
    assert [entry["id"] for entry in indicators(controller)] == ["builtin"]
    controller.backend.updated.emit({"wifi": original, "bluetooth": {"available": True, "powered": True}})
    assert len(indicators(controller)) == 2
    assert controller.modal["key"] == modal_key
    assert controller.modal["text"] == "keep my input"
    assert controller.navigation.page == "apps"
    controller.dispatch("back")
    assert controller.navigation.index == 3
    assert controller.backend.actions == []


def test_no_adapters_has_no_invented_signal(controller):
    controller.data["wifi"].update({"available": False, "devices": []})
    assert indicators(controller) == []


@pytest.mark.parametrize(("language", "text"), [("en", "Signal: 92%"), ("zh_CN", "信号强度：92%")])
def test_signal_tooltips_follow_the_interface_language(controller, language, text):
    controller.setLanguage(language)
    entries = indicators(controller)
    assert len(entries) == 2
    assert text in entries[0]["label"]


def test_mock_connect_and_disconnect_update_only_the_target_signal(controller):
    controller.backend.request("wifi_connect", {"deviceId": "usb", "id": "usb-studio"})
    entries = indicators(controller)
    assert len(entries) == 2
    assert [entry["strength"] for entry in entries] == [92, 86]
    controller.backend.request("wifi_disconnect", {"deviceId": "usb"})
    entries = indicators(controller)
    assert entries[0]["strength"] == 92
    assert entries[1]["strength"] is None
