from pathlib import Path

from .i18n import tr


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
            "name": {"usb": tr('USB 无线网卡'), "builtin": tr('内置无线网卡')}.get(kind, tr('无线网卡'))}


def wifi_label(device):
    return device.get("name", tr('无线网卡')) + (" · " + device["interface"] if device.get("interface") else "")


def wifi_status(device, enabled=True):
    if not enabled:
        return tr('全部 Wi-Fi 已关闭')
    if not device.get("managed", True):
        return tr('未由系统管理')
    if device.get("error"):
        return device["error"]
    if device.get("connected"):
        return tr('已连接 · ') + device["connected"]
    state = device.get("deviceState", 0)
    if state == 100:
        return tr('已连接')
    if 40 <= state < 100:
        return tr('正在连接') + (" · " + device["connecting"] if device.get("connecting") else "")
    if state == 20:
        return tr('暂不可用')
    return tr('未连接')


def wifi_summary(information):
    devices = information.get("devices", [])
    if not devices:
        return information.get("error") or tr('未检测到无线网卡')
    if not information.get("enabled"):
        return tr('Wi-Fi 已关闭') if len(devices) == 1 else tr('{value0} 张网卡 · Wi-Fi 已关闭', value0=len(devices))
    if len(devices) == 1:
        return wifi_status(devices[0])
    connected = sum(bool(device.get("connected")) or device.get("deviceState") == 100 for device in devices)
    return tr('{value0} 张网卡 · {value1} 已连接', value0=len(devices), value1=connected)


def wifi_indicators(information):
    """One status per adapter; scan results never stand in for active signal."""
    indicators = []
    devices = sorted(information.get("devices", []), key=lambda device: (
        {"builtin": 0, "usb": 1}.get(device.get("kind"), 2), device.get("interface", ""), device["id"]))
    enabled = information.get("enabled", False)
    for device in devices:
        state = device.get("deviceState", 0)
        if not enabled:
            status = "off"
        elif not device.get("managed", True):
            status = "unmanaged"
        elif not device.get("available", False) or device.get("error") or state in (0, 10, 20, 120):
            status = "unavailable"
        elif state == 100:
            status = "connected"
        elif 40 <= state < 100:
            status = "connecting"
        else:
            status = "disconnected"
        strength = device.get("strength") if status == "connected" else None
        if strength is not None:
            strength = max(0, min(100, int(strength)))
        label = wifi_label(device) + "\n" + wifi_status(device, enabled)
        if status == "connected":
            label += "\n" + (tr('信号强度：{strength}%', strength=strength) if strength is not None else tr('信号强度暂不可用'))
        indicators.append({"id": device["id"], "status": status, "strength": strength,
                           "level": (strength + 24) // 25 if strength is not None else 0, "label": label})
    return indicators


def wifi_security(information):
    flags = information.get("WpaFlags", 0) | information.get("RsnFlags", 0)
    enterprise = bool(flags & 0x200) and not bool(flags & 0x500)
    security = tr('企业网络') if enterprise else "WPA3" if flags & 0x400 else "WPA2" if flags & 0x100 else tr('不支持的加密') if information.get("Flags", 0) & 1 else tr('开放网络')
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
        return tr("Wi-Fi credentials are required or were rejected")
    if reason in (8, 9, 10, 11):
        return tr("Wi-Fi authentication or negotiation failed")
    if reason in (5, 6, 15, 16, 17):
        return tr("Could not obtain a network address")
    if reason == 53:
        return tr("The network is no longer in range")
    return tr("Wi-Fi connection failed (system reason {reason})", reason=reason)


def wifi_phase(state):
    return tr("Preparing to join") if state == 40 else tr("Configuring Wi-Fi") if state == 50 else (
        tr("Waiting for credentials") if state == 60 else tr("Obtaining a network address") if state == 70 else
        tr("Checking the connection") if state in (80, 90) else tr("Joining network"))
