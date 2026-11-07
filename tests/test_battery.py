import json
import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication

from udeck.backend import SystemBackend
from udeck.controller import ShellController
from udeck.core import ConfigStore
from udeck.mock import MockBackend


@pytest.fixture
def hardware(tmp_path, monkeypatch):
    supplies = tmp_path / "power_supply"
    supplies.mkdir()
    backlights = tmp_path / "backlight"
    backlights.mkdir()
    paths = {"/sys/class/power_supply": supplies, "/sys/class/backlight": backlights}
    monkeypatch.setattr("udeck.backend.Path", lambda value: paths.get(value, Path(value)))
    backend = SystemBackend()
    yield backend, supplies
    backend.loop.close()


def supply(root, **values):
    directory = root / "axp20x-battery"
    directory.mkdir(exist_ok=True)
    fields = {"type": "Battery", "present": "1", "capacity": "100", "status": "Charging",
              "voltage_now": "4206000", "current_now": "17000", "power_now": "0",
              "constant_charge_current": "1950000", **values}
    for field, value in fields.items():
        if value is not None:
            (directory / field).write_text(str(value))
    return directory


def test_battery_power_uses_actual_microvolt_and_microamp_readings(hardware):
    backend, root = hardware
    supply(root)
    backend.refresh_hardware()
    battery = backend.state["battery"]
    assert battery["available"] is True
    assert battery["voltage"] == pytest.approx(4.206)
    assert battery["current"] == pytest.approx(0.017)
    assert battery["power"] == pytest.approx(0.071502)
    assert battery["status"] == "Charging"


def test_signed_discharge_current_is_a_magnitude_not_charging(hardware):
    backend, root = hardware
    supply(root, status="Discharging", capacity="83", voltage_now="3900000", current_now="-800000")
    backend.refresh_hardware()
    battery = backend.state["battery"]
    assert battery["charging"] is False
    assert battery["current"] == pytest.approx(0.8)
    assert battery["power"] == pytest.approx(3.12)
    assert battery["status"] == "Discharging"


@pytest.mark.parametrize("reading", [None, "", "nan", "broken"])
def test_missing_or_invalid_current_does_not_become_a_zero_watt_reading(hardware, reading):
    backend, root = hardware
    supply(root, current_now=reading)
    backend.refresh_hardware()
    battery = backend.state["battery"]
    assert battery["available"] is True
    assert battery["capacity"] == 100
    assert battery["voltage"] == pytest.approx(4.206)
    assert battery["current"] is None
    assert battery["power"] is None


@pytest.mark.parametrize("reading", [None, "broken", "0", "-1000000"])
def test_unusable_voltage_does_not_hide_a_valid_current(hardware, reading):
    backend, root = hardware
    supply(root, voltage_now=reading)
    backend.refresh_hardware()
    battery = backend.state["battery"]
    assert battery["available"] is True
    assert battery["voltage"] is None
    assert battery["current"] == pytest.approx(0.017)
    assert battery["power"] is None


def test_zero_current_is_a_valid_measurement(hardware):
    backend, root = hardware
    supply(root, current_now="0", status="Full")
    backend.refresh_hardware()
    battery = backend.state["battery"]
    assert battery["charging"] is False
    assert battery["current"] == 0
    assert battery["power"] == 0


def test_metric_permission_error_preserves_other_battery_information(hardware, monkeypatch):
    backend, root = hardware
    directory = supply(root)
    original = Path.read_text

    def read(path, *args, **kwargs):
        if path == directory / "current_now":
            raise PermissionError("sensor not readable")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", read)
    backend.refresh_hardware()
    assert backend.state["battery"]["available"] is True
    assert backend.state["battery"]["power"] is None
    assert backend.state["battery"]["voltage"] == pytest.approx(4.206)


@pytest.mark.parametrize("removed", [True, False])
def test_battery_removal_or_present_zero_clears_previous_measurements(hardware, removed):
    backend, root = hardware
    directory = supply(root)
    backend.refresh_hardware()
    if removed:
        for field in directory.iterdir():
            field.unlink()
        directory.rmdir()
    else:
        (directory / "present").write_text("0")
    backend.refresh_hardware()
    battery = backend.state["battery"]
    assert battery["available"] is False
    assert battery.get("voltage") is None
    assert battery.get("current") is None
    assert battery.get("power") is None


@pytest.fixture
def controller(tmp_path):
    application = QCoreApplication.instance() or QCoreApplication([])
    instance = ShellController(MockBackend(), config=ConfigStore(tmp_path / "settings.json"), mock=True)
    instance._test_application = application
    yield instance
    instance.close()


def charging_state(**values):
    return {"available": True, "capacity": 83, "status": "Charging", "charging": True,
            "voltage": 3.9, "current": 1.2, "power": 4.68, **values}


@pytest.mark.parametrize(("language", "power_label", "status"), [
    ("en", "Charging power (estimate)", "Charging"),
    ("zh_CN", "充电功率（估算）", "正在充电"),
])
def test_battery_details_display_localized_units_and_battery_side_scope(controller, language, power_label, status):
    controller.setLanguage(language)
    controller.backend.updated.emit({"battery": charging_state()})
    controller.activateSetting("battery")
    modal = json.loads(controller.snapshotJson)["modal"]
    assert status in modal["body"]
    assert modal["metrics"][0] == {"label": power_label, "value": "4.68 W"}
    assert modal["metrics"][1]["value"] == "3.900 V"
    assert modal["metrics"][2]["value"] == "1.200 A"
    assert ("Battery-side" if language == "en" else "电池侧") in modal["body"]


def test_open_battery_details_refresh_without_replacing_dialog_or_focus(controller):
    controller.backend.updated.emit({"battery": charging_state()})
    controller.setPage("settings")
    position = next(i for i, item in enumerate(controller._items()) if item["id"] == "battery")
    controller.select(position)
    controller.dispatch("accept")
    key = controller.modal["key"]
    controller.backend.updated.emit({"battery": charging_state(current=0.5, power=1.95)})
    modal = json.loads(controller.snapshotJson)["modal"]
    assert modal["key"] == key
    assert modal["metrics"][0]["value"] == "1.95 W"
    assert modal["metrics"][2]["value"] == "0.500 A"
    controller.dispatch("back")
    assert controller.navigation.page == "settings"
    assert controller.navigation.index == position
    assert not controller.modal


def test_battery_refresh_clears_old_metrics_and_preserves_a_nested_prompt(controller):
    controller.backend.updated.emit({"battery": charging_state()})
    controller.activateSetting("battery")
    owner = controller.modal["key"]
    controller.backend.prompt.emit({"kind": "text", "title": "Password", "body": "Enter password",
                                    "token": "nested-battery", "secret": True})
    controller.editText("keep this input")
    controller.backend.updated.emit({"battery": {"available": False, "capacity": 0, "charging": False}})
    assert controller.modal["text"] == "keep this input"
    controller.dispatch("back")
    modal = json.loads(controller.snapshotJson)["modal"]
    assert modal["key"] == owner
    assert "No battery detected" in modal["body"]
    assert all(metric["value"] == "Not available" for metric in modal["metrics"])


@pytest.mark.parametrize(("status", "summary", "label"), [
    ("Discharging", "On battery", "Discharging power (estimate)"),
    ("Full", "Fully charged", "Battery power (estimate)"),
    ("Not charging", "Not charging", "Battery power (estimate)"),
    ("Unknown", "Battery status unknown", "Battery power (estimate)"),
])
def test_battery_status_does_not_mislabel_discharge_or_full_as_charging(controller, status, summary, label):
    controller.backend.updated.emit({"battery": charging_state(status=status, charging=False)})
    controller.setPage("settings")
    state = json.loads(controller.snapshotJson)
    battery = next(item for item in state["items"] if item["id"] == "battery")
    assert summary in battery["subtitle"]
    controller.activateSetting("battery")
    modal = json.loads(controller.snapshotJson)["modal"]
    assert summary in modal["body"]
    assert modal["metrics"][0]["label"] == label


def test_missing_metrics_can_be_distinguished_from_a_measured_zero(controller):
    controller.backend.updated.emit({"battery": charging_state(current=0, power=0, voltage=None)})
    controller.activateSetting("battery")
    metrics = json.loads(controller.snapshotJson)["modal"]["metrics"]
    assert [metric["value"] for metric in metrics] == ["0.00 W", "Not available", "0.000 A"]


def test_quick_settings_battery_returns_to_its_previous_selection(controller):
    controller.setPage("apps")
    controller.select(3)
    controller.dispatch("quick-settings")
    controller.chooseModal(next(i for i, item in enumerate(controller.modal["options"]) if item.get("id") == "battery"))
    assert "metrics" in json.loads(controller.snapshotJson)["modal"]
    controller.dispatch("back")
    assert not controller.modal
    assert controller.navigation.page == "apps"
    assert controller.navigation.index == 3
    assert controller.backend.actions == []
