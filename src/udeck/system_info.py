"""Read hardware and operating-system details without additional services or privileges."""

import os
import platform
import shlex
import shutil
from pathlib import Path

from . import __version__
from .i18n import Msg, tr


def _text(path):
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip("\0 \t\r\n")
    except OSError:
        return ""


def _integer(value, minimum=1):
    try:
        number = int(value)
        return number if number >= minimum else None
    except ValueError:
        return None


def _temperature(root):
    try:
        zones = sorted((root / "sys/class/thermal").glob("thermal_zone*"))
    except OSError:
        return None
    for zone in zones:
        kind = _text(zone / "type").lower()
        if kind not in {"cpu-thermal", "cpu_thermal", "soc-thermal", "soc_thermal", "x86_pkg_temp"}:
            continue
        value = _integer(_text(zone / "temp"), minimum=0)
        if value is not None and value <= 150_000:
            return value / 1000
    return None


def read_system_info(root=Path("/")):
    root = Path(root)
    cpu_text = _text(root / "proc/cpuinfo")
    cpu = {}
    processors = []
    for line in cpu_text.splitlines():
        key, separator, value = line.partition(":")
        if separator:
            cpu.setdefault(key.strip(), value.strip())
            if key.strip() == "processor" and value.strip().isdigit():
                processors.append(value.strip())

    def device_tree(name):
        return (_text(root / "sys/firmware/devicetree/base" / name)
                or _text(root / "proc/device-tree" / name))

    compatible = device_tree("cpus/cpu@0/compatible").split("\0")[0]
    processor = cpu.get("model name")
    if not processor and compatible.startswith("arm,cortex-"):
        processor = "ARM Cortex-" + compatible.removeprefix("arm,cortex-").upper()
    processor = processor or cpu.get("Hardware") or cpu.get("Processor")

    memory = {}
    for line in _text(root / "proc/meminfo").splitlines():
        key, separator, value = line.partition(":")
        fields = value.split()
        if separator and len(fields) == 2 and fields[1] == "kB":
            amount = _integer(fields[0], minimum=0)
            if amount is not None:
                memory[key] = amount * 1024
    total = memory.get("MemTotal") or None
    available = memory.get("MemAvailable")
    if total is None or available is not None and available > total:
        available = None

    storage_total = storage_free = None
    try:
        usage = shutil.disk_usage(root)
        storage_total, storage_free = usage.total, usage.free
    except OSError:
        pass

    os_release = {}
    for line in _text(root / "etc/os-release").splitlines():
        key, separator, value = line.partition("=")
        if separator and key in {"PRETTY_NAME", "NAME"}:
            try:
                os_release[key] = " ".join(shlex.split(value))
            except ValueError:
                continue
    frequency = _integer(_text(root / "sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_max_freq"))
    return {
        "model": device_tree("model") or _text(root / "sys/class/dmi/id/product_name") or None,
        "serial": device_tree("serial-number") or _text(root / "sys/class/dmi/id/product_serial") or cpu.get("Serial") or None,
        "processor": processor or None,
        "cores": len(set(processors)) or os.cpu_count(),
        "architecture": platform.machine() or None,
        "cpuMaxFrequency": frequency / 1000 if frequency is not None else None,
        "memoryTotal": total,
        "memoryAvailable": available,
        "storageTotal": storage_total,
        "storageFree": storage_free,
        "temperature": _temperature(root),
        "os": os_release.get("PRETTY_NAME") or os_release.get("NAME") or platform.system() or None,
        "kernel": _text(root / "proc/sys/kernel/osrelease") or platform.release() or None,
    }


def system_info_options(info):
    def value(field, unit=""):
        reading = info.get(field)
        if reading is None or reading == "":
            return tr(Msg.NOT_AVAILABLE)
        if unit == "bytes":
            return f"{reading / 1024**3:.2f} GiB"
        if unit == "MHz":
            return f"{reading:.0f} MHz"
        if unit == "°C":
            return f"{reading:.1f} °C"
        return str(reading)

    fields = [
        ("model", Msg.DEVICE_MODEL, ""),
        ("processor", Msg.PROCESSOR, ""),
        ("cores", Msg.LOGICAL_CPUS, ""),
        ("architecture", Msg.ARCHITECTURE, ""),
        ("cpuMaxFrequency", Msg.CPU_MAX_FREQUENCY, "MHz"),
        ("memoryTotal", Msg.MEMORY_TOTAL, "bytes"),
        ("memoryAvailable", Msg.MEMORY_AVAILABLE, "bytes"),
        ("storageTotal", Msg.SYSTEM_STORAGE_TOTAL, "bytes"),
        ("storageFree", Msg.SYSTEM_STORAGE_FREE, "bytes"),
        ("temperature", Msg.CPU_TEMPERATURE, "°C"),
        ("serial", Msg.HARDWARE_SERIAL_NUMBER, ""),
        ("os", Msg.OPERATING_SYSTEM, ""),
        ("kernel", Msg.KERNEL_VERSION, ""),
    ]
    rows = [{"id": field, "label": tr(label), "subtitle": value(field, unit),
             "action": "system-info-detail"} for field, label, unit in fields]
    rows.append({"id": "udeck", "label": tr(Msg.UDECK_VERSION), "subtitle": __version__,
                 "action": "system-info-detail"})
    rows.append({"id": "refresh", "label": tr(Msg.REFRESH), "action": "system-info-refresh",
                 "icon": "view-refresh"})
    return rows
