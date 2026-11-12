"""Start and stop a real AP on an explicitly selected, idle NetworkManager adapter.

Run through SSH as a user allowed to manage NetworkManager, for example:
    sudo --preserve-env=SSH_CONNECTION python3 tests/hotspot_device_probe.py \
        --interface wlan0 --output /tmp/udeck-hotspot-report.json

Refuses the SSH adapter and existing hotspot configurations. Creates a unique
temporary profile, removes only that profile, and verifies existing connections
and settings. AP activation does not prove that a wireless client can join.
"""

import argparse
import asyncio
import json
import os
import secrets
import subprocess
import time
import uuid
from pathlib import Path

from dbus_next import BusType
from dbus_next.aio import MessageBus

from udeck.backend import NM, NM_ROOT, SystemBackend, unwrap


async def probe(backend, interface, report):
    backend.bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
    backend.network_agent_registered = True  # No second SecretAgent is registered.
    client = os.environ.get("SSH_CONNECTION", "").split()
    assert client, "Run through SSH to protect its management route"

    def route():
        return json.loads(subprocess.check_output(
            ["ip", "-j", "route", "get", client[0]], text=True))[0]

    before_route = route()
    assert interface != before_route.get("dev"), "Refusing the adapter carrying SSH"
    await backend.refresh_wifi()
    device = next(d for d in backend.state["wifi"]["devices"] if d["interface"] == interface)
    assert device["managed"] and device["deviceState"] == 30 and not device["connected"], "Adapter must be idle"
    assert device["apSupported"], "Adapter must support WPA2/CCMP AP mode"
    assert not device["hotspot"]["configured"], "Refusing an existing hotspot configuration"
    identifier = device["id"]

    async def profiles():
        paths = (await backend.call(NM, NM_ROOT + "/Settings", NM + ".Settings", "ListConnections"))[0]
        return {path: unwrap((await backend.call(
            NM, path, NM + ".Settings.Connection", "GetSettings"))[0]) for path in paths}

    before_profiles = await profiles()
    before_active = await backend.get(NM, NM_ROOT, NM, "ActiveConnections")
    name = "udeck-audit-" + uuid.uuid4().hex[:12]
    password = secrets.token_urlsafe(18)
    report.update(interface=interface, checks=[], clientConnectivityTested=False)
    checks = report["checks"]

    async def current():
        assert route() == before_route, "SSH route changed"
        await backend.refresh_wifi()
        return next(d for d in backend.state["wifi"]["devices"] if d["id"] == identifier)

    async def settle():
        task = backend.hotspot_tasks[identifier]
        await asyncio.wait_for(asyncio.shield(task), 100)
        return await current()

    async def owned_profiles():
        # Match the unique test SSID as well as paths absent from the baseline.
        return {path: value for path, value in (await profiles()).items()
                if path not in before_profiles
                and value.get("802-11-wireless", {}).get("mode") == "ap"
                and bytes(value["802-11-wireless"].get("ssid", [])).decode() == name}

    try:
        await backend._execute("wifi_hotspot_configure", {
            "deviceId": identifier, "ssid": name, "password": password,
            "revision": device["hotspot"]["revision"],
        })
        item = await current()
        created = await owned_profiles()
        assert len(created) == 1 and item["hotspot"]["configured"]
        settings = next(iter(created.values()))
        assert settings["connection"]["autoconnect"] is False
        assert settings["ipv4"]["method"] == "shared" and settings["ipv4"]["never-default"]
        assert settings["ipv6"]["method"] == "disabled"
        checks.append("temporary-device-bound-wpa2-profile-saved-without-activation")
        await backend._execute("wifi_hotspot_start", {
            "deviceId": identifier, "revision": item["hotspot"]["revision"],
            "expectedActive": item.get("activeConnection", "/"),
        })
        item = await settle()
        assert item["hotspot"]["status"] == "active", item["hotspot"]
        assert item["hotspot"]["owned"] and item["deviceState"] == 100
        raw_device = await backend._require_wifi_device(identifier)
        assert (await backend.properties(NM, identifier, NM + ".Device.Wireless"))["Mode"] == 3
        addresses = await backend._wifi_addresses(raw_device)
        assert addresses["ip"], "Active AP must have an actual address"
        assert password not in json.dumps(backend.state)
        report["addressCount"] = len(addresses["ip"])
        checks.append("real-ap-activation-confirmed-by-nm-device-mode-state-and-address")
        await backend._execute("wifi_hotspot_stop", {
            "deviceId": identifier, "operationId": item["hotspot"]["operationId"],
            "activePath": item["hotspot"]["activePath"],
        })
        item = await settle()
        assert item["hotspot"]["status"] == "off", item["hotspot"]
        assert (await backend._require_wifi_device(identifier))["ActiveConnection"] == "/"
        checks.append("real-ap-stop-leaves-selected-adapter-disconnected")
    finally:
        for task in list(backend.hotspot_tasks.values()):
            if not task.done():
                task.cancel()
        await asyncio.gather(*backend.hotspot_tasks.values(), return_exceptions=True)
        created = await owned_profiles()
        raw = await backend._require_wifi_device(identifier)
        active_path = raw.get("ActiveConnection", "/")
        if active_path != "/":
            active = await backend.properties(NM, active_path, NM + ".Connection.Active")
            if active.get("Connection") in created and active.get("Devices") == [identifier]:
                await backend.call(NM, NM_ROOT, NM, "DeactivateConnection", "o", [active_path])
        deadline = time.monotonic() + 10
        while (await backend._require_wifi_device(identifier)).get("ActiveConnection", "/") != "/":
            assert time.monotonic() < deadline, "Adapter did not become idle; keep profile for diagnosis"
            await asyncio.sleep(0.2)
        for path in created:
            await backend.call(NM, path, NM + ".Settings.Connection", "Delete")
        assert await profiles() == before_profiles, "Existing profiles changed"
        assert await backend.get(NM, NM_ROOT, NM, "ActiveConnections") == before_active
        assert route() == before_route
        report["preserved"] = True
        checks.append("temporary-profile-removed-existing-profiles-active-connections-and-ssh-preserved")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--interface", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = {"passed": False, "mock": False}
    backend = SystemBackend()

    async def run():
        try:
            await probe(backend, args.interface, report)
            report["passed"] = True
        finally:
            backend.closing = True
            if backend.wifi_monitor:
                backend.wifi_monitor.cancel()
                await asyncio.gather(backend.wifi_monitor, return_exceptions=True)
            if backend.bus:
                backend.bus.disconnect()

    try:
        asyncio.run(run())
    except Exception as error:
        report["error"] = repr(error)
        raise
    finally:
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2))
        backend.loop.close()
    print(json.dumps(report, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
