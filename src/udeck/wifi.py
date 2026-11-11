from pathlib import Path

from .hotspot import HOTSPOT_BUSY, hotspot_status
from .i18n import Msg, tr


def wifi_identity(interface, sysfs_root=Path("/sys/class/net")):
    kind = "unknown"
    device = Path(sysfs_root) / interface / "device"
    if interface and device.exists():
        resolved = device.resolve()
        buses = {(parent / "subsystem").resolve().name for parent in (resolved, *resolved.parents)
                 if (parent / "subsystem").exists()}
        if "usb" in buses:
            kind = "usb"
        elif buses & {"mmc", "sdio", "platform"}:
            kind = "builtin"
    return {"interface": interface, "kind": kind,
            "name": {"usb": tr(Msg.USB_WI_FI_ADAPTER), "builtin": tr(Msg.BUILT_IN_WI_FI_ADAPTER)}.get(kind, tr(Msg.WI_FI_ADAPTER))}


def wifi_label(device):
    return device.get("name", tr(Msg.WI_FI_ADAPTER)) + (" · " + device["interface"] if device.get("interface") else "")


def wifi_status(device, enabled=True):
    if not enabled:
        return tr(Msg.ALL_WI_FI_OFF)
    if not device.get("managed", True):
        return tr(Msg.UNMANAGED_BY_SYSTEM)
    if device.get("error"):
        return device["error"]
    if device.get("mode") == "ap" or device.get("hotspot", {}).get("status") in HOTSPOT_BUSY:
        hotspot = device.get("hotspot", {})
        return hotspot_status(hotspot) + " · " + (hotspot.get("activeSsid") or hotspot.get("ssid", ""))
    if device.get("connected"):
        return tr(Msg.CONNECTED_PREFIX) + device["connected"]
    state = device.get("deviceState", 0)
    if state == 100:
        return tr(Msg.CONNECTED)
    if 40 <= state < 100:
        return tr(Msg.CONNECTING) + (" · " + device["connecting"] if device.get("connecting") else "")
    if state == 20:
        return tr(Msg.UNAVAILABLE)
    return tr(Msg.NOT_CONNECTED)


def wifi_summary(information):
    devices = information.get("devices", [])
    if not devices:
        return information.get("error") or tr(Msg.NO_WI_FI_ADAPTERS_FOUND)
    if not information.get("enabled"):
        return tr(Msg.WI_FI_OFF) if len(devices) == 1 else tr(Msg.VALUE0_ADAPTERS_WI_FI_OFF, value0=len(devices))
    if len(devices) == 1:
        return wifi_status(devices[0])
    connected = sum(device.get("mode") != "ap" and (bool(device.get("connected")) or device.get("deviceState") == 100) for device in devices)
    return tr(Msg.VALUE0_ADAPTERS_VALUE1_CONNECTED, value0=len(devices), value1=connected)


def wifi_indicators(information):
    """One status per adapter; scan results never stand in for active signal."""
    indicators = []
    devices = sorted(information.get("devices", []), key=lambda device: (
        {"builtin": 0, "usb": 1}.get(device.get("kind"), 2), device.get("interface", ""), device["id"]))
    enabled = information.get("enabled", False)
    for device in devices:
        state = device.get("deviceState", 0)
        hotspot = device.get("hotspot", {})
        kind = "hotspot" if (device.get("mode") == "ap" or hotspot.get("status") in HOTSPOT_BUSY
                             or hotspot.get("status") == "failed" and state != 100) else "wifi"
        if not enabled:
            status = "off"
        elif not device.get("managed", True):
            status = "unmanaged"
        elif kind == "hotspot" and hotspot.get("status") == "failed":
            status = "failed"
        elif not device.get("available", False) or device.get("error") or state in (0, 10, 20, 120):
            status = "unavailable"
        elif kind == "hotspot":
            status = hotspot.get("status", "active" if state == 100 else "starting")
        elif state == 100:
            status = "connected"
        elif 40 <= state < 100:
            status = "connecting"
        else:
            status = "disconnected"
        strength = device.get("strength") if status == "connected" and kind == "wifi" else None
        if strength is not None:
            strength = max(0, min(100, int(strength)))
        description = (hotspot_status(hotspot) + " · " + (hotspot.get("activeSsid") or hotspot.get("ssid", ""))
                       if kind == "hotspot" else wifi_status(device, enabled))
        label = wifi_label(device) + "\n" + description
        if status == "connected":
            label += "\n" + (tr(Msg.SIGNAL_STRENGTH, strength=strength) if strength is not None else tr(Msg.SIGNAL_STRENGTH_UNAVAILABLE))
        if kind == "hotspot" and hotspot.get("message"):
            label += "\n" + hotspot["message"]
        indicators.append({"id": device["id"], "kind": kind, "status": status, "strength": strength,
                           "level": (strength + 24) // 25 if strength is not None else 0, "label": label})
    return indicators


def wifi_security(information):
    flags = information.get("WpaFlags", 0) | information.get("RsnFlags", 0)
    enterprise = bool(flags & 0x200) and not bool(flags & 0x500)
    security = tr(Msg.ENTERPRISE_NETWORK) if enterprise else "WPA3" if flags & 0x400 else "WPA2" if flags & 0x100 else tr(Msg.UNSUPPORTED_ENCRYPTION) if information.get("Flags", 0) & 1 else tr(Msg.OPEN_NETWORK)
    keys = (["wpa-psk"] if flags & 0x100 else []) + (["sae"] if flags & 0x400 else [])
    return security, keys


def security_code(information):
    flags = information.get("WpaFlags", 0) | information.get("RsnFlags", 0)
    if flags & 0x200 and not flags & 0x500:
        return "enterprise"
    if flags & 0x400:
        return "wpa3"
    if flags & 0x100:
        return "wpa2"
    return "unsupported" if information.get("Flags", 0) & 1 else "open"


def network_key(ssid, security):
    return bytes(ssid).hex() + ":" + security


def wifi_failure(reason):
    if reason == 7:
        return tr(Msg.WI_FI_CREDENTIALS_ARE_REQUIRED_OR_WERE_REJECTED)
    if reason in (8, 9, 10, 11):
        return tr(Msg.WI_FI_AUTHENTICATION_OR_NEGOTIATION_FAILED)
    if reason in (5, 6, 15, 16, 17):
        return tr(Msg.COULD_NOT_OBTAIN_A_NETWORK_ADDRESS)
    if reason == 53:
        return tr(Msg.THE_NETWORK_IS_NO_LONGER_IN_RANGE)
    return tr(Msg.WI_FI_CONNECTION_FAILED_SYSTEM_REASON_REASON, reason=reason)


def wifi_phase(state):
    return tr(Msg.PREPARING_TO_JOIN) if state == 40 else tr(Msg.CONFIGURING_WI_FI) if state == 50 else (
        tr(Msg.WAITING_FOR_CREDENTIALS) if state == 60 else tr(Msg.OBTAINING_A_NETWORK_ADDRESS) if state == 70 else
        tr(Msg.CHECKING_THE_CONNECTION) if state in (80, 90) else tr(Msg.JOINING_NETWORK))
