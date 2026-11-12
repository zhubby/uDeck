"""Nonblocking GUI worker client of the restricted system D-Bus service."""

import asyncio
import json

from . import OBJECT_PATH, SERVICE


async def remote(member, value=None):
    from dbus_next import BusType, Message
    from dbus_next.aio import MessageBus
    bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
    try:
        reply = await asyncio.wait_for(bus.call(Message(destination=SERVICE, path=OBJECT_PATH,
            interface=SERVICE, member=member, signature="s" if value is not None else "",
            body=[json.dumps(value)] if value is not None else [])), 100)
        if reply.error_name:
            raise RuntimeError(reply.body[0] if reply.body else reply.error_name)
        value = json.loads(reply.body[0])
        if value.get("error"):
            raise RuntimeError(value["error"])
        return value
    finally:
        bus.disconnect()


def status():
    return asyncio.run(remote("Status"))


def start(value):
    return asyncio.run(remote("Configure", {key: value[key] for key in ("root", "networks", "duration")}))


def stop():
    return asyncio.run(remote("Stop"))
