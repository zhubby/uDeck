"""Public hotspot descriptions and input validation; credentials never live here."""

from .i18n import Msg, tr

HOTSPOT_BUSY = {"starting", "stopping", "restoring"}
HOTSPOT_OWNER = "io.github.zhubby.uDeck.hotspot"


def validate_hotspot_name(value):
    if not isinstance(value, str) or not value.strip() or "\x00" in value or not 1 <= len(value.encode("utf-8")) <= 32:
        raise ValueError(tr(Msg.HOTSPOT_NAME_MUST_CONTAIN_1_32_UTF_8_BYTES_AND_NO_NULL_CHARACTERS))
    return value


def default_hotspot_name(interface):
    return ("uDeck-" + interface).encode()[:32].decode("utf-8", errors="ignore")


def hotspot_status(hotspot):
    labels = {"off": tr(Msg.HOTSPOT_OFF), "starting": tr(Msg.STARTING_HOTSPOT),
              "active": tr(Msg.HOTSPOT_ON), "stopping": tr(Msg.STOPPING_HOTSPOT),
              "restoring": tr(Msg.RESTORING_WI_FI), "failed": tr(Msg.HOTSPOT_FAILED)}
    return labels.get(hotspot.get("status"), labels["off"])


def hotspot_summary(wifi):
    if not wifi.get("available"):
        return wifi.get("error") or tr(Msg.NO_WIRELESS_ADAPTER_DETECTED)
    count = sum(device.get("mode") == "ap" and device.get("deviceState") == 100
                for device in wifi.get("devices", []))
    return tr(Msg.COUNT_HOTSPOTS_ON, count=count) if count else tr(Msg.HOTSPOTS_OFF)
