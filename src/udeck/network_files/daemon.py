"""Headless file service, managed by the user's systemd instance on Linux."""
# D-Bus signatures in annotations are protocol types, not Python forward references.
# ruff: noqa: F821

import argparse
import asyncio
import contextlib
import json
import signal

from dbus_next import BusType, Message, RequestNameReply
from dbus_next.aio import MessageBus
from dbus_next.service import ServiceInterface, method
from dbus_next.service import signal as dbus_signal

from . import OBJECT_PATH, SERVICE
from .lifecycle import ShareManager
from .networks import discover


class Control(ServiceInterface):
    def __init__(self, manager, system_bus):
        super().__init__(SERVICE)
        self.manager, self.system_bus = manager, system_bus

    @method()
    def Status(self) -> 's':
        return json.dumps(self.manager.status())

    @method()
    async def Networks(self) -> 's':
        return json.dumps(await discover(self.system_bus))

    @method()
    async def Configure(self, payload: 's') -> 's':
        try:
            if len(payload) > 65536:
                raise ValueError("Configuration is too large")
            value = json.loads(payload)
            result = await self.manager.configure(value, candidates=await discover(self.system_bus))
            self.Changed(json.dumps(result))
            return json.dumps(result)
        except (ValueError, OSError, KeyError, TypeError) as error:
            return json.dumps({"error": str(error)})

    @method()
    async def Stop(self) -> 's':
        result = await self.manager.stop()
        self.Changed(json.dumps(result))
        return json.dumps(result)

    @dbus_signal()
    def Changed(self, payload: 's') -> 's':
        return payload


async def serve(config=None):
    manager = ShareManager(config)
    bus = await MessageBus().connect()
    system_bus = None
    with contextlib.suppress(Exception):
        system_bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
    control = Control(manager, system_bus)
    bus.export(OBJECT_PATH, control)
    # Acquiring the name marks a Type=dbus service ready; export its API first.
    if await bus.request_name(SERVICE) != RequestNameReply.PRIMARY_OWNER:
        bus.disconnect()
        if system_bus:
            system_bus.disconnect()
        return
    done = asyncio.Event()
    for event in (signal.SIGINT, signal.SIGTERM):
        asyncio.get_running_loop().add_signal_handler(event, done.set)
    previous = ""
    try:
        while not done.is_set():
            candidates = await discover(system_bus)
            owner_alive = True
            if manager.deadline is not None:
                reply = await bus.call(Message(destination="org.freedesktop.DBus", path="/org/freedesktop/DBus",
                                                interface="org.freedesktop.DBus", member="NameHasOwner",
                                                signature="s", body=[manager.owner]))
                owner_alive = not reply.error_name and bool(reply.body[0])
            await manager.tick(candidates=candidates, owner_alive=owner_alive)
            state = json.dumps(manager.status())
            if state != previous:
                control.Changed(state)
                previous = state
            try:
                await asyncio.wait_for(done.wait(), 2)
            except TimeoutError:
                pass
    finally:
        await manager.close()
        bus.disconnect()
        if system_bus:
            system_bus.disconnect()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config")
    parser.add_argument("--standalone-root", help="Run an isolated local preview without session D-Bus")
    parser.add_argument("--bind", default="127.0.0.1")
    parser.add_argument("--port", default=8787, type=int)
    args = parser.parse_args()
    if args.standalone_root:
        from aiohttp import web

        from .server import create_app
        web.run_app(create_app(args.standalone_root), host=args.bind, port=args.port)
    else:
        asyncio.run(serve(args.config))


if __name__ == "__main__":
    main()
