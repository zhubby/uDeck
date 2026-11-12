"""Authenticated system D-Bus control for uDeck's dedicated Samba service."""
# D-Bus annotations are wire signatures.
# ruff: noqa: F821

import asyncio
import contextlib
import json
import os
import pwd
import signal
from pathlib import Path

from dbus_next import BusType, Message, MessageType, RequestNameReply, Variant
from dbus_next.aio import MessageBus
from dbus_next.service import ServiceInterface, method

from ..network_files.networks import discover
from . import OBJECT_PATH, SERVICE
from .lifecycle import Actor, SmbManager


async def call(bus, destination, path, interface, member, signature="", body=None):
    reply = await asyncio.wait_for(bus.call(Message(destination=destination, path=path, interface=interface,
                                                    member=member, signature=signature, body=body or [])), 60)
    if reply.error_name:
        raise PermissionError(reply.body[0] if reply.body else reply.error_name)
    return reply.body


def process_start(pid):
    # The comm field can contain spaces and closing parentheses.
    return Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[19]


async def credentials(bus, sender):
    values = (await call(bus, "org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus",
                         "GetConnectionCredentials", "s", [sender]))[0]
    uid, pid = values["UnixUserID"].value, values["ProcessID"].value
    user = pwd.getpwuid(uid)
    session = ""
    with contextlib.suppress(PermissionError):
        session = (await call(bus, "org.freedesktop.login1", "/org/freedesktop/login1", "org.freedesktop.login1.Manager",
                              "GetSessionByPID", "u", [pid]))[0]
    return Actor(uid=uid, gid=user.pw_gid, name=user.pw_name, pid=pid, session=session, start_time=process_start(pid))


async def authorize(bus, sender):
    result = await call(bus, "org.freedesktop.PolicyKit1", "/org/freedesktop/PolicyKit1/Authority",
                        "org.freedesktop.PolicyKit1.Authority", "CheckAuthorization", "(sa{sv})sa{ss}us",
                        [["system-bus-name", {"name": Variant("s", sender)}], SERVICE + ".manage", {}, 1, ""])
    if not result[0][0]:
        raise PermissionError("Not authorized to manage SMB file sharing")


async def owner_alive(bus, actor):
    if actor is None:
        return False
    try:
        if process_start(actor.pid) != actor.start_time:
            return False
        if actor.session:
            result = await call(bus, "org.freedesktop.login1", actor.session, "org.freedesktop.DBus.Properties",
                                "Get", "ss", ["org.freedesktop.login1.Session", "State"])
            return result[0].value != "closing"
        return True
    except (OSError, PermissionError, IndexError):
        return False


class Metadata(ServiceInterface):
    """Introspection only. The raw dispatcher below authenticates each sender."""

    def __init__(self):
        super().__init__(SERVICE)

    @method()
    def Status(self) -> 's':
        raise PermissionError("Authenticated dispatcher required")

    @method()
    def Configure(self, payload: 's') -> 's':
        raise PermissionError("Authenticated dispatcher required")

    @method()
    def Stop(self) -> 's':
        raise PermissionError("Authenticated dispatcher required")


class Dispatcher:
    def __init__(self, bus, manager):
        self.bus, self.manager = bus, manager
        self.tasks = set()

    def handle(self, message):
        if message.message_type != MessageType.METHOD_CALL or message.path != OBJECT_PATH or message.interface != SERVICE:
            return None
        task = asyncio.create_task(self.dispatch(message))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        return True

    async def dispatch(self, message):
        try:
            signature = {"Status": "", "Configure": "s", "Stop": ""}.get(message.member)
            if signature is None or signature != message.signature:
                raise ValueError("Unsupported SMB method or signature")
            actor = await credentials(self.bus, message.sender)
            if message.member == "Status":
                result = self.manager.status()
            else:
                await authorize(self.bus, message.sender)
                if message.member == "Configure":
                    payload = message.body[0]
                    if len(payload.encode()) > 65536:
                        raise ValueError("Configuration is too large")
                    result = await self.manager.configure(json.loads(payload), actor=actor, candidates=await discover(self.bus))
                else:
                    result = await self.manager.stop(actor=actor)
            reply = Message.new_method_return(message, "s", [json.dumps(result)])
        except Exception as error:
            reply = Message.new_method_return(message, "s", [json.dumps({"error": str(error)})])
        await self.bus.send(reply)


async def serve():
    if os.geteuid() != 0:
        raise PermissionError("The SMB manager must be started by the system service")
    manager = SmbManager()
    bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
    dispatcher = Dispatcher(bus, manager)
    bus.add_message_handler(dispatcher.handle)
    bus.export(OBJECT_PATH, Metadata())
    if await bus.request_name(SERVICE) != RequestNameReply.PRIMARY_OWNER:
        bus.disconnect()
        return
    done = asyncio.Event()
    for event in (signal.SIGINT, signal.SIGTERM):
        asyncio.get_running_loop().add_signal_handler(event, done.set)
    try:
        # A manager restart must not adopt a stale daemon or its existing connections.
        await manager.runtime.stop()
        while not done.is_set():
            try:
                await manager.tick(candidates=await discover(bus), owner_alive=await owner_alive(bus, manager.owner) if manager.deadline is not None else True)
            except Exception as error:
                manager.errors = [str(error)]
                # Revocation failures must remain visible and retry termination.
                await manager.runtime.stop()
                manager.addresses = set()
            try:
                await asyncio.wait_for(done.wait(), 1)
            except TimeoutError:
                pass
    finally:
        for task in list(dispatcher.tasks):
            task.cancel()
        await asyncio.gather(*dispatcher.tasks, return_exceptions=True)
        await manager.close()
        bus.disconnect()


def main():
    asyncio.run(serve())


if __name__ == "__main__":
    main()
