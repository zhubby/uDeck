from pathlib import Path


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
            "name": {"usb": "USB 无线网卡", "builtin": "内置无线网卡"}.get(kind, "无线网卡")}


def wifi_label(device):
    return device.get("name", "无线网卡") + (" · " + device["interface"] if device.get("interface") else "")


def wifi_status(device, enabled=True):
    if not enabled:
        return "全部 Wi-Fi 已关闭"
    if not device.get("managed", True):
        return "未由系统管理"
    if device.get("error"):
        return device["error"]
    if device.get("connected"):
        return "已连接 · " + device["connected"]
    state = device.get("deviceState", 0)
    if state == 100:
        return "已连接"
    if 40 <= state < 100:
        return "正在连接" + (" · " + device["connecting"] if device.get("connecting") else "")
    if state == 20:
        return "暂不可用"
    return "未连接"


def wifi_summary(information):
    devices = information.get("devices", [])
    if not devices:
        return information.get("error") or "未检测到无线网卡"
    if not information.get("enabled"):
        return "Wi-Fi 已关闭" if len(devices) == 1 else f"{len(devices)} 张网卡 · Wi-Fi 已关闭"
    if len(devices) == 1:
        return wifi_status(devices[0])
    connected = sum(bool(device.get("connected")) or device.get("deviceState") == 100 for device in devices)
    return f"{len(devices)} 张网卡 · {connected} 已连接"


def wifi_security(information):
    flags = information.get("WpaFlags", 0) | information.get("RsnFlags", 0)
    enterprise = bool(flags & 0x200) and not bool(flags & 0x500)
    security = "企业网络" if enterprise else "WPA3" if flags & 0x400 else "WPA2" if flags & 0x100 else "不支持的加密" if information.get("Flags", 0) & 1 else "开放网络"
    keys = (["wpa-psk"] if flags & 0x100 else []) + (["sae"] if flags & 0x400 else [])
    return security, keys
