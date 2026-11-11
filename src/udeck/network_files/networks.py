"""Connected interfaces with stable connection identities and usable addresses."""

import asyncio
import ipaddress
import sys

from PySide6.QtNetwork import QNetworkInterface


def interfaces():
    rows = []
    for interface in QNetworkInterface.allInterfaces():
        flags = interface.flags()
        if not flags & QNetworkInterface.InterfaceFlag.IsUp or flags & QNetworkInterface.InterfaceFlag.IsLoopBack:
            continue
        addresses = []
        for entry in interface.addressEntries():
            raw = entry.ip().toString().split("%")[0]
            try:
                address = ipaddress.ip_address(raw)
            except ValueError:
                continue
            if not (address.is_loopback or address.is_link_local or address.is_multicast or address.is_unspecified):
                addresses.append(str(address))
        if not addresses:
            continue
        mac = interface.hardwareAddress().lower()
        identity = "mac:" + mac if mac and mac != "00:00:00:00:00:00" else "if:" + interface.name()
        kind = "wifi" if interface.type() == QNetworkInterface.InterfaceType.Ieee80211 else "network"
        rows.append({"id": identity, "interface": interface.name(), "name": interface.humanReadableName(),
                     "connection": "", "addresses": addresses, "key": identity, "kind": kind})
    return rows


async def discover(bus=None):
    rows = interfaces()
    if bus is None:
        # Linux connection profiles are the authorization boundary, including after reboot.
        return [] if sys.platform == "linux" else [row for row in rows if row["kind"] != "wifi"]
    from dbus_next import Message
    async def call(path, interface, member, signature="", body=None):
        result = await asyncio.wait_for(bus.call(Message(destination="org.freedesktop.NetworkManager", path=path,
                                        interface=interface, member=member, signature=signature, body=body or [])), 2)
        if result.error_name:
            raise RuntimeError(result.error_name)
        return result.body
    async def properties(path, interface):
        data = (await call(path, "org.freedesktop.DBus.Properties", "GetAll", "s", [interface]))[0]
        return {key: value.value for key, value in data.items()}
    try:
        devices = (await call("/org/freedesktop/NetworkManager", "org.freedesktop.NetworkManager", "GetDevices"))[0]
        for path in devices:
            device = await properties(path, "org.freedesktop.NetworkManager.Device")
            connection = device.get("ActiveConnection", "/")
            if connection == "/":
                continue
            active = await properties(connection, "org.freedesktop.NetworkManager.Connection.Active")
            if active.get("State") != 2 or not active.get("Uuid"):
                continue
            permanent = device.get("PermHwAddress", "")
            if device.get("DeviceType") == 2:
                wireless = await properties(path, "org.freedesktop.NetworkManager.Device.Wireless")
                permanent = wireless.get("PermHwAddress") or permanent
            for row in rows:
                if row["interface"] == device.get("Interface"):
                    if permanent and permanent != "00:00:00:00:00:00":
                        row["id"] = "mac:" + permanent.lower()
                    row.update(connection=active["Uuid"], name=active.get("Id", row["name"]),
                               kind="vpn" if active.get("Vpn") or active.get("Type") in ("vpn", "wireguard") else
                               "wifi" if device.get("DeviceType") == 2 else "ethernet" if device.get("DeviceType") == 1 else "network")
                    row["key"] = row["id"] + "@" + row["connection"]
    except (RuntimeError, OSError, TimeoutError):
        # Metadata loss must revoke access rather than broaden a saved network selection.
        return []
    return [row for row in rows if row["connection"]]
