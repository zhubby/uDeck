import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from udeck.controller import ShellController
from udeck.core import ConfigStore
from udeck.mock import MockBackend


@pytest.fixture
def shell(tmp_path):
    controller = ShellController(MockBackend(), config=ConfigStore(tmp_path / "settings.json"), mock=True)
    yield controller
    controller.close()


def test_system_information_is_reachable_and_returns_to_the_same_setting(shell):
    shell.setPage("settings")
    rows = json.loads(shell.snapshotJson)["items"]
    position = next(index for index, row in enumerate(rows) if row["id"] == "system-info")
    assert rows[position]["name"] == "System information"
    assert rows[position]["icon"].startswith("udeck-setting:")
    shell.select(position)
    shell.dispatch("accept")
    owner = shell.modal["key"]
    assert shell.modal["source"] == "system-info"
    assert all(row["singleLine"] and row["icon"] for row in shell.modal["options"])
    shell.chooseModal(next(index for index, row in enumerate(shell.modal["options"]) if row["id"] == "model"))
    assert shell.modal["kind"] == "information"
    assert "Compute Module 4" in shell.modal["body"]
    shell.dispatch("back")
    assert shell.modal["key"] == owner
    shell.dispatch("back")
    assert not shell.modal and shell.navigation.index == position
    assert shell.backend.actions == []


@pytest.fixture
def hardware(tmp_path, monkeypatch):
    from udeck import system_info

    def write(name, value):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value)

    write("sys/firmware/devicetree/base/model", "Raspberry Pi Compute Module 4 Rev 1.0\0")
    write("sys/firmware/devicetree/base/serial-number", "10000000abcdef01\0")
    write("sys/firmware/devicetree/base/cpus/cpu@0/compatible", "arm,cortex-a72\0")
    write("proc/cpuinfo", "".join(f"processor : {index}\n\n" for index in range(4))
          + "Hardware : BCM2711\nRevision : c03140\nSerial : fallback-serial\n")
    write("proc/meminfo", "MemTotal: 4194304 kB\nMemAvailable: 1572864 kB\n")
    write("sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_max_freq", "1500000\n")
    write("sys/class/thermal/thermal_zone0/type", "cpu-thermal\n")
    write("sys/class/thermal/thermal_zone0/temp", "42500\n")
    write("etc/os-release", 'NAME="Debian GNU/Linux"\nPRETTY_NAME="Debian GNU/Linux 13 (trixie)"\n')
    write("proc/sys/kernel/osrelease", "6.12.47+rpt-rpi-v8\n")
    monkeypatch.setattr(system_info.platform, "machine", lambda: "aarch64")
    monkeypatch.setattr(system_info.os, "cpu_count", lambda: 8)
    monkeypatch.setattr(system_info.shutil, "disk_usage", lambda path: SimpleNamespace(
        total=64 * 1024**3, free=20 * 1024**3))
    return tmp_path, write


def test_linux_hardware_uses_device_readings_and_converts_kernel_units(hardware):
    from udeck.system_info import read_system_info

    root, _ = hardware
    info = read_system_info(root)
    assert info["model"] == "Raspberry Pi Compute Module 4 Rev 1.0"
    assert info["serial"] == "10000000abcdef01"
    assert info["processor"] == "ARM Cortex-A72"
    assert info["cores"] == 4
    assert info["architecture"] == "aarch64"
    assert info["memoryTotal"] == 4 * 1024**3
    assert info["memoryAvailable"] == 1.5 * 1024**3
    assert info["storageTotal"] == 64 * 1024**3
    assert info["storageFree"] == 20 * 1024**3
    assert info["cpuMaxFrequency"] == 1500
    assert info["temperature"] == 42.5
    assert info["os"] == "Debian GNU/Linux 13 (trixie)"
    assert info["kernel"] == "6.12.47+rpt-rpi-v8"


def test_dmi_and_x86_cpu_names_work_without_a_raspberry_pi_device_tree(hardware):
    from udeck.system_info import read_system_info

    root, write = hardware
    for path in (root / "sys/firmware/devicetree/base").rglob("*"):
        if path.is_file():
            path.unlink()
    write("sys/class/dmi/id/product_name", "Example Computer\n")
    write("sys/class/dmi/id/product_serial", "DEVICE-SERIAL\n")
    write("proc/cpuinfo", "processor : 0\nmodel name : Example x86 CPU @ 2.40GHz\n")
    info = read_system_info(root)
    assert info["model"] == "Example Computer"
    assert info["serial"] == "DEVICE-SERIAL"
    assert info["processor"] == "Example x86 CPU @ 2.40GHz"
    assert info["cores"] == 1


def test_proc_device_tree_and_cpuinfo_are_used_on_older_linux_images(hardware):
    from udeck.system_info import read_system_info

    root, write = hardware
    for path in (root / "sys/firmware/devicetree/base").rglob("*"):
        if path.is_file():
            path.unlink()
    write("proc/device-tree/model", "Older compute module\0")
    info = read_system_info(root)
    assert info["model"] == "Older compute module"
    assert info["processor"] == "BCM2711"
    assert info["serial"] == "fallback-serial"


@pytest.mark.parametrize("memory", ["MemTotal: 4194304 kB\n", "MemTotal: 4194304 kB\nMemAvailable: 8388608 kB\n"])
def test_missing_or_inconsistent_available_memory_is_not_guessed(hardware, memory):
    from udeck.system_info import read_system_info

    root, write = hardware
    write("proc/meminfo", memory)
    info = read_system_info(root)
    assert info["memoryTotal"] == 4 * 1024**3
    assert info["memoryAvailable"] is None


def test_gpu_temperature_is_not_reported_as_cpu_temperature(hardware):
    from udeck.system_info import read_system_info

    root, write = hardware
    write("sys/class/thermal/thermal_zone0/type", "gpu-thermal\n")
    assert read_system_info(root)["temperature"] is None
    write("sys/class/thermal/thermal_zone1/type", "cpu-thermal\n")
    write("sys/class/thermal/thermal_zone1/temp", "51000\n")
    assert read_system_info(root)["temperature"] == 51


@pytest.mark.parametrize("reading", ["", "invalid", "nan", "-1", "999999999"])
def test_invalid_sensors_and_memory_are_unavailable_without_hiding_other_fields(hardware, reading):
    from udeck.system_info import read_system_info

    root, write = hardware
    write("sys/class/thermal/thermal_zone0/temp", reading)
    write("sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_max_freq", "invalid")
    write("proc/meminfo", "MemTotal: invalid kB\nMemAvailable: -1 kB\n")
    info = read_system_info(root)
    assert info["temperature"] is None
    assert info["cpuMaxFrequency"] is None
    assert info["memoryTotal"] is None
    assert info["memoryAvailable"] is None
    assert info["processor"] == "ARM Cortex-A72"


def test_permission_errors_and_missing_sources_do_not_invent_hardware(tmp_path, monkeypatch):
    from udeck import system_info

    def denied(*args, **kwargs):
        raise PermissionError("Not readable")

    monkeypatch.setattr(Path, "read_text", denied)
    monkeypatch.setattr(system_info.shutil, "disk_usage", denied)
    monkeypatch.setattr(system_info.os, "cpu_count", lambda: None)
    info = system_info.read_system_info(tmp_path)
    for field in ("model", "serial", "processor", "cores", "memoryTotal", "memoryAvailable",
                  "storageTotal", "storageFree", "temperature", "cpuMaxFrequency"):
        assert info[field] is None, field


def test_mock_information_never_reads_host_hardware_and_translates_live(shell, monkeypatch):
    def unexpected_read(*args, **kwargs):
        raise AssertionError("Mock preview read host hardware")

    monkeypatch.setattr("udeck.controller.read_system_info", unexpected_read)
    shell.activateSetting("system-info")
    owner = shell.modal["key"]
    shell.setLanguage("zh_CN")
    modal = json.loads(shell.snapshotJson)["modal"]
    assert modal["title"] == "系统信息"
    assert next(row for row in modal["options"] if row["id"] == "memoryTotal")["label"] == "内存总量"
    shell.chooseModal(next(index for index, row in enumerate(shell.modal["options"]) if row["id"] == "refresh"))
    assert shell.modal["key"] == owner
    assert shell.backend.actions == []


def test_refresh_reads_current_values_and_preserves_focus(shell, monkeypatch):
    from udeck.mock import mock_system_info

    info = mock_system_info()
    monkeypatch.setattr("udeck.controller.read_system_info", lambda: dict(info))
    shell.mock = False
    shell.activateSetting("system-info")
    owner = shell.modal["key"]
    info["temperature"] = 51.25
    info["memoryAvailable"] = None
    refresh = next(index for index, row in enumerate(shell.modal["options"]) if row["id"] == "refresh")
    shell.chooseModal(refresh)
    modal = json.loads(shell.snapshotJson)["modal"]
    assert modal["key"] == owner and modal["index"] == refresh
    assert next(row for row in modal["options"] if row["id"] == "temperature")["subtitle"] == "51.2 °C"
    assert next(row for row in modal["options"] if row["id"] == "memoryAvailable")["subtitle"] == "Not available"
    assert shell.backend.actions == []


def test_long_hardware_values_can_be_read_in_full_and_back_preserves_selection(shell, monkeypatch):
    from udeck.mock import mock_system_info

    info = mock_system_info()
    info["model"] = "Example computer " * 12
    monkeypatch.setattr("udeck.controller.mock_system_info", lambda: dict(info))
    shell.activateSetting("system-info")
    position = next(index for index, row in enumerate(shell.modal["options"]) if row["id"] == "model")
    shell.chooseModal(position)
    assert shell.modal["body"] == info["model"]
    shell.dispatch("back")
    assert shell.modal["source"] == "system-info" and shell.modal["index"] == position
