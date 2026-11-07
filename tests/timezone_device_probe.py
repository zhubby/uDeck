"""Read the device's real time zone and validate its unchanged-zone no-op path.

Does not set a different time zone or change the system clock, NTP or RTC.
Run with the installed uDeck package and the device's normal desktop user.
"""

import asyncio
import json
import subprocess

from dbus_next import BusType
from dbus_next.aio import MessageBus

from udeck.backend import SystemBackend


async def run():
    backend = SystemBackend()
    mutations = []
    original = backend.call

    async def observe(destination, path, interface, member, *args, **kwargs):
        if member.startswith("Set"):
            mutations.append(member)
            raise AssertionError("This probe must not modify system settings")
        return await original(destination, path, interface, member, *args, **kwargs)

    backend.call = observe
    try:
        backend.bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
        assert await backend.refresh_timezone(), backend.state["timezone"]
        state = backend.state["timezone"]
        current = state["current"]
        assert current and current in state["zones"], state
        await backend._execute("timezone_set", {"timezone": current})
        independent = subprocess.check_output(["timedatectl", "show", "--value", "-p", "Timezone"], text=True).strip()
        assert backend.state["timezone"]["current"] == independent == current
        assert not mutations
        print(json.dumps({"current": current, "zoneCount": len(state["zones"]),
                          "systemReadbackMatches": True, "unchangedZoneIsNoOp": True,
                          "mutations": mutations, "interactiveAuthorizationTested": False}))
    finally:
        if backend.bus:
            backend.bus.disconnect()
        backend.loop.close()


if __name__ == "__main__":
    asyncio.run(run())
