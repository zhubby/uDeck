"""Independently validate emitted AP settings with Debian's real libnm.

Requires python3-gi, gir1.2-nm-1.0 and the normal test dependencies.
Uses synthetic devices and credentials. Optionally verifies password retention
against an explicitly supplied disposable NetworkManager D-Bus instance.
"""

import argparse
import asyncio
import json

import gi
from dbus_next import Variant
from dbus_next.aio import MessageBus
from test_hotspot import HotspotManager, configure

from udeck.backend import SystemBackend


async def run(isolated_bus_address=None):
    gi.require_version("NM", "1.0")
    from gi.repository import NM, GLib

    backend, manager = SystemBackend(), HotspotManager()
    real_call = backend.call
    captured = []

    async def call(*args, **kwargs):
        if args[3] == "AddConnection":
            captured.append(args[5][0])
        return await manager.call(*args, **kwargs)

    backend.call, backend.get, backend.properties = call, manager.get, manager.properties
    try:
        await configure(backend)
        raw = captured[0]
        settings = {group: {key: GLib.Variant(value.signature, value.value) for key, value in values.items()}
                    for group, values in raw.items()}
        connection = NM.SimpleConnection.new_from_dbus(GLib.Variant("a{sa{sv}}", settings))
        assert connection.verify()
        report = {"libnm": NM.utils_version(), "profileValid": True, "hardwareChanged": False}
        if isolated_bus_address:
            backend.bus = await MessageBus(bus_address=isolated_bus_address).connect()
            destination, root = "org.freedesktop.NetworkManager", "/org/freedesktop/NetworkManager/Settings"
            target = (await real_call(destination, root, destination + ".Settings", "AddConnection", "a{sa{sv}}", [raw]))[0]
            try:
                interface = destination + ".Settings.Connection"
                updated = (await real_call(destination, target, interface, "GetSettings"))[0]
                assert "psk" not in updated["802-11-wireless-security"]
                updated["802-11-wireless"]["ssid"] = Variant("ay", b"Renamed hotspot")
                await real_call(destination, target, interface, "Update2", "a{sa{sv}}ua{sv}", [updated, 1, {}])
                secrets = (await real_call(destination, target, interface, "GetSecrets", "s", ["802-11-wireless-security"]))[0]
                assert secrets["802-11-wireless-security"]["psk"].value == raw["802-11-wireless-security"]["psk"].value
                report["nameUpdateRetainsPassword"] = True
            finally:
                await real_call(destination, target, interface, "Delete")
                backend.bus.disconnect()
        print(json.dumps(report))
    finally:
        backend.loop.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--isolated-bus-address", help="A disposable test NetworkManager bus; never use the host system bus")
    asyncio.run(run(parser.parse_args().isolated_bus_address))
