"""Read battery-side measurements without changing the charger configuration."""

from pathlib import Path

from .i18n import tr


def _text(path):
    try:
        return path.read_text().strip()
    except OSError:
        return ""


def _integer(path):
    try:
        return int(_text(path))
    except ValueError:
        return None


def read_battery(root):
    for supply in sorted(Path(root).glob("*")):
        if _text(supply / "type") != "Battery" or _text(supply / "present") == "0":
            continue
        capacity = _integer(supply / "capacity")
        if capacity is None or not 0 <= capacity <= 100:
            continue
        status = _text(supply / "status") or "Unknown"
        voltage = _integer(supply / "voltage_now")
        current = _integer(supply / "current_now")
        voltage = voltage / 1_000_000 if voltage is not None and voltage > 0 else None
        # Drivers differ on discharge sign; status carries the direction.
        current = abs(current) / 1_000_000 if current is not None else None
        # uConsole can report power_now=0 alongside nonzero voltage/current.
        # Never substitute the configured charge-current limit for a reading.
        power = voltage * current if voltage is not None and current is not None else None
        return {"available": True, "capacity": capacity, "charging": status == "Charging",
                "status": status, "voltage": voltage, "current": current, "power": power}
    return {"available": False, "capacity": 0, "charging": False, "status": "Unknown",
            "voltage": None, "current": None, "power": None}


def battery_summary(battery):
    if not battery.get("available"):
        return tr('未检测到电池')
    status = battery.get("status", "Charging" if battery.get("charging") else "Discharging")
    label = {"Charging": tr('正在充电'), "Discharging": tr('电池供电'),
             "Full": tr("Fully charged"), "Not charging": tr("Not charging")}.get(status, tr("Battery status unknown"))
    return tr('{value0}% · {value1}', value0=battery["capacity"], value1=label)


def battery_details(battery):
    status = battery.get("status")
    power_label = tr("Charging power (estimate)") if status == "Charging" else (
        tr("Discharging power (estimate)") if status == "Discharging" else tr("Battery power (estimate)"))

    def measurement(field, spec, unit):
        value = battery.get(field) if battery.get("available") else None
        return f"{value:{spec}} {unit}" if value is not None else tr("Not available")

    return {"body": battery_summary(battery) + "\n" + tr("Battery-side estimate. Charger input power is unavailable."),
            "metrics": [
                {"label": power_label, "value": measurement("power", ".2f", "W")},
                {"label": tr("Battery voltage"), "value": measurement("voltage", ".3f", "V")},
                {"label": tr("Battery current"), "value": measurement("current", ".3f", "A")},
            ]}
