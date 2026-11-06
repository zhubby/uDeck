"""Read real adapters; --scan additionally requests a scan on each adapter."""

import argparse
import asyncio
import json
import os
import subprocess
import time

from dbus_next import BusType
from dbus_next.aio import MessageBus

from udeck.backend import NM, SystemBackend
from udeck.wifi import wifi_summary


async def probe(scan):
    backend = SystemBackend()
    backend.loop.close()
    backend.loop = asyncio.get_running_loop()
    # Enumeration needs no second SecretAgent alongside the running desktop.
    backend.network_agent_registered = True
    backend.bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
    try:
        await backend.refresh_wifi()
        initial = backend.state["wifi"]
        scans = []
        if scan:
            for device in initial["devices"]:
                result = {"deviceId": device["id"], "interface": device["interface"]}
                try:
                    result["before"] = await backend.get(NM, device["id"], NM + ".Device.Wireless", "LastScan")
                    await backend._execute("wifi_scan", {"deviceId": device["id"]})
                    result["requested"] = True
                except Exception as error:
                    result["error"] = str(error)
                scans.append(result)
            deadline = time.monotonic() + 12
            while time.monotonic() < deadline:
                for result in scans:
                    if result.get("requested") and not result.get("completed"):
                        result["after"] = await backend.get(NM, result["deviceId"], NM + ".Device.Wireless", "LastScan")
                        result["completed"] = result["after"] > result["before"]
                if all(result.get("completed") or result.get("error") for result in scans):
                    break
                await asyncio.sleep(0.5)
            await backend.refresh_wifi()
        wifi = backend.state["wifi"]
        devices = [{**device, "networks": [{key: network[key] for key in ("id", "name", "security", "strength", "connected", "saved")} for network in device["networks"]]}
                   for device in wifi["devices"]]
        report = {"summary": wifi_summary(wifi), "available": wifi["available"], "enabled": wifi["enabled"], "devices": devices, "scans": scans}
        connection = os.environ.get("SSH_CONNECTION", "").split()
        if connection:
            report["sshRoute"] = json.loads(subprocess.check_output(["ip", "-j", "route", "get", connection[0]], text=True))
        print(json.dumps(report, ensure_ascii=False))
    finally:
        backend.bus.disconnect()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--scan", action="store_true")
    asyncio.run(probe(parser.parse_args().scan))
