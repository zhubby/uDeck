"""User-session D-Bus service; no window or graphical Qt dependency."""
# D-Bus signatures are protocol types, as in the existing file service.
# ruff: noqa: F821

import argparse
import asyncio
import json
import signal
import time

from . import OBJECT_PATH, SERVICE
from .sync import SyncManager


async def serve(directory=None):
    from dbus_next import RequestNameReply
    from dbus_next.aio import MessageBus
    from dbus_next.service import ServiceInterface, method
    from dbus_next.service import signal as dbus_signal

    # D-Bus protocol annotations are intentionally evaluated by dbus-next.
    class Control(ServiceInterface):
        def __init__(self, manager):
            super().__init__(SERVICE)
            self.manager = manager

        @method()
        def Status(self) -> 's':
            return json.dumps(self.manager.status())

        @method()
        async def Configure(self, payload: 's') -> 's':
            try:
                if len(payload) > 65536:
                    raise ValueError("Configuration is too large")
                result = await self.manager.configure(json.loads(payload))
                self.Changed(json.dumps(result))
                return json.dumps(result)
            except (OSError, ValueError, TypeError) as error:
                return json.dumps({"error": str(error), "phase": "error"})

        @method()
        def SyncNow(self) -> 's':
            return json.dumps(self.manager.schedule())

        @method()
        async def Remotes(self) -> 's':
            try:
                return json.dumps({"remotes": await self.manager.remotes()})
            except OSError as error:
                return json.dumps({"error": str(error)})

        @method()
        async def TestConnection(self, payload: 's') -> 's':
            try:
                value = json.loads(payload)
                return json.dumps(await self.manager.test_connection(value["remote"], value["directory"]))
            except (OSError, ValueError, KeyError, TypeError) as error:
                return json.dumps({"error": str(error)})

        @dbus_signal()
        def Changed(self, payload: 's') -> 's':
            return payload

    manager = SyncManager(directory)
    bus = await MessageBus().connect()
    control = Control(manager)
    bus.export(OBJECT_PATH, control)
    if await bus.request_name(SERVICE) != RequestNameReply.PRIMARY_OWNER:
        bus.disconnect()
        return
    done = asyncio.Event()
    loop = asyncio.get_running_loop()
    for event in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(event, done.set)
    previous = ""
    try:
        while not done.is_set():
            if (manager.config["enabled"] and time.monotonic() >= manager.next_run
                    and (not manager.task or manager.task.done())):
                manager.schedule()
            state = json.dumps(manager.status())
            if state != previous:
                control.Changed(state)
                previous = state
            try:
                await asyncio.wait_for(done.wait(), 1)
            except TimeoutError:
                pass
    finally:
        await manager.close()
        bus.disconnect()


def main():
    parser = argparse.ArgumentParser(description="uDeck emulator native save sync service")
    parser.add_argument("--directory")
    parser.add_argument("--once", action="store_true")
    options = parser.parse_args()
    if options.once:
        async def once():
            manager = SyncManager(options.directory)
            try:
                print(json.dumps(await manager.sync()))
            finally:
                await manager.close()
        asyncio.run(once())
    else:
        asyncio.run(serve(options.directory))


if __name__ == "__main__":
    main()
