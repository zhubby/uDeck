"""Public hotspot descriptions and input validation; credentials never live here."""

from .i18n import tr

HOTSPOT_BUSY = {"starting", "stopping", "restoring"}
HOTSPOT_OWNER = "io.github.zhubby.uDeck.hotspot"


def validate_hotspot_name(value):
    if not isinstance(value, str) or not value.strip() or "\x00" in value or not 1 <= len(value.encode("utf-8")) <= 32:
        raise ValueError(tr("Hotspot name must contain 1–32 UTF-8 bytes and no null characters"))
    return value


def default_hotspot_name(interface):
    return ("uDeck-" + interface).encode()[:32].decode("utf-8", errors="ignore")


def hotspot_status(hotspot):
    labels = {"off": tr("Hotspot off"), "starting": tr("Starting hotspot…"),
              "active": tr("Hotspot on"), "stopping": tr("Stopping hotspot…"),
              "restoring": tr("Restoring Wi-Fi…"), "failed": tr("Hotspot failed")}
    return labels.get(hotspot.get("status"), labels["off"])


def hotspot_summary(wifi):
    if not wifi.get("available"):
        return wifi.get("error") or tr("No wireless adapter detected")
    count = sum(device.get("mode") == "ap" and device.get("deviceState") == 100
                for device in wifi.get("devices", []))
    return tr("{count} hotspots on", count=count) if count else tr("Hotspots off")
