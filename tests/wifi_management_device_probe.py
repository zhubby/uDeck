"""Safe real-NM checks: explicit idle adapter, temporary profile, no activation.

Run on the handheld with --interface <idle interface>. The SSH route and all
existing profile settings are checked before and after. Secrets are read only
from the temporary profile created here; neither passwords nor settings print.
"""

import argparse
import asyncio
import getpass
import json
import os
import secrets
import subprocess
import time
import uuid

from dbus_next import BusType, Variant
from dbus_next.aio import MessageBus

from udeck.backend import NM, NM_ROOT, SystemBackend, unwrap


async def probe(backend, interface):
    backend.bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
    backend.network_agent_registered = True  # No agent registration/activation needed.
    await backend.refresh_wifi()
    device = next(entry for entry in backend.state["wifi"]["devices"] if entry["interface"] == interface)
    ssh_client = os.environ.get("SSH_CONNECTION", "").split()
    assert ssh_client, "Run through SSH so the current management route can be protected"

    def ssh_route():
        return json.loads(subprocess.check_output(["ip", "-j", "route", "get", ssh_client[0]], text=True))[0]

    before_route = ssh_route()
    assert device["interface"] != before_route.get("dev"), "Refusing to test the adapter carrying SSH"
    assert device["managed"] and device["deviceState"] == 30 and not device["connected"], "Adapter must be managed and idle"
    identifier = device["id"]
    before = {p["uuid"]: p["revision"] for p in await backend._saved_wifi()}
    before_active = await backend.get(NM, NM_ROOT, NM, "ActiveConnections")
    temporary_uuid = str(uuid.uuid4())
    password, new_password = secrets.token_hex(16), secrets.token_hex(16)
    settings = {
        "connection": {"id": Variant("s", "uDeck 0.1.16 temporary acceptance"),
                       "uuid": Variant("s", temporary_uuid), "type": Variant("s", "802-11-wireless"),
                       "interface-name": Variant("s", interface), "autoconnect": Variant("b", False),
                       "permissions": Variant("as", [f"user:{getpass.getuser()}:"])},
        "802-11-wireless": {"ssid": Variant("ay", ("udeck-test-" + temporary_uuid[:12]).encode()),
                            "mode": Variant("s", "infrastructure")},
        "802-11-wireless-security": {"key-mgmt": Variant("s", "wpa-psk"), "psk": Variant("s", password)},
        "ipv4": {"method": Variant("s", "auto"), "route-metric": Variant("x", 1234)},
        "ipv6": {"method": Variant("s", "auto")},
        "proxy": {"method": Variant("i", 0)},
    }
    path = None
    checks = []
    try:
        path = (await backend.call(NM, NM_ROOT + "/Settings", NM + ".Settings", "AddConnection", "a{sa{sv}}", [settings]))[0]

        async def target():
            await backend.refresh_wifi()
            entry = next(p for d in backend.state["wifi"]["devices"] if d["id"] == identifier
                         for p in d["saved"] if p["uuid"] == temporary_uuid)
            return {"deviceId": identifier, "profileUuid": temporary_uuid, "revision": entry["revision"]}

        async def temporary_secrets():
            return unwrap((await backend.call(NM, path, NM + ".Settings.Connection", "GetSecrets", "s", ["802-11-wireless-security"]))[0])

        async def temporary_settings():
            return unwrap((await backend.call(NM, path, NM + ".Settings.Connection", "GetSettings"))[0])

        original = await temporary_settings()
        await backend._execute("wifi_set_autoconnect", {**await target(), "enabled": True})
        value = await temporary_settings()
        assert value["connection"].get("autoconnect", True) is True
        assert (await temporary_secrets())["802-11-wireless-security"]["psk"] == password
        checks.append("autoconnect_persisted_and_existing_secret_preserved")
        await backend._execute("wifi_set_autoconnect", {**await target(), "enabled": False})
        assert (await temporary_settings())["connection"]["autoconnect"] is False
        checks.append("autoconnect_disabled_without_activation")
        await backend._execute("wifi_update_password", {**await target(), "password": new_password})
        assert (await temporary_secrets())["802-11-wireless-security"]["psk"] == new_password
        current = await temporary_settings()
        assert {k: v for k, v in current.items() if k != "802-11-wireless-security"} == {
            k: v for k, v in original.items() if k != "802-11-wireless-security"}
        assert new_password not in str(backend.state)
        assert (await backend._require_wifi_device(identifier))["ActiveConnection"] == "/"
        checks.append("password_persisted_without_reconnect_or_unrelated_changes")
        stale = await target()
        raw = (await backend.call(NM, path, NM + ".Settings.Connection", "GetSettings"))[0]
        raw["connection"]["id"] = Variant("s", "uDeck temporary external update")
        await backend.call(NM, path, NM + ".Settings.Connection", "Update2", "a{sa{sv}}ua{sv}", [raw, 1, {}])
        try:
            await backend._execute("wifi_update_password", {**stale, "password": password})
        except RuntimeError:
            pass
        else:
            raise AssertionError("Stale configuration update was accepted")
        assert (await temporary_secrets())["802-11-wireless-security"]["psk"] == new_password
        checks.append("external_update_rejected_without_overwriting_secret")
        await backend._execute("wifi_forget", await target())
        path = None
        after = {p["uuid"]: p["revision"] for p in await backend._saved_wifi()}
        assert before == after
        checks.append("exact_temporary_profile_forgotten_and_existing_profiles_preserved")
        await backend._execute("wifi_scan", {"deviceId": identifier})
        deadline = time.monotonic() + 22
        while time.monotonic() < deadline:
            await backend.refresh_wifi()
            result = next(d for d in backend.state["wifi"]["devices"] if d["id"] == identifier)
            if result["scan"].get("status") != "scanning":
                break
            await asyncio.sleep(0.5)
        assert result["scan"]["status"] == "complete", result["scan"]
        checks.append("idle_adapter_scan_confirmed_by_last_scan")
        assert before_active == await backend.get(NM, NM_ROOT, NM, "ActiveConnections")
        assert before_route == ssh_route()
        assert (await backend._require_wifi_device(identifier))["ActiveConnection"] == "/"
        checks.append("ssh_connection_routes_and_idle_adapter_preserved")
        return {"interface": interface, "checks": checks, "temporaryProfileRemoved": True,
                "adapterCount": len(backend.state["wifi"]["devices"]), "scanNetworkCount": len(result["networks"])}
    finally:
        if path:
            current = await backend._require_wifi_device(identifier, inactive=True)
            if current["ActiveConnection"] == "/":
                await backend.call(NM, path, NM + ".Settings.Connection", "Delete")
        backend.closing = True
        if backend.wifi_monitor:
            backend.wifi_monitor.cancel()
            await asyncio.gather(backend.wifi_monitor, return_exceptions=True)
        backend.bus.disconnect()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--interface", required=True)
    args = parser.parse_args()
    backend = SystemBackend()
    try:
        print(json.dumps(asyncio.run(probe(backend, args.interface)), indent=2))
    finally:
        backend.loop.close()


if __name__ == "__main__":
    main()
