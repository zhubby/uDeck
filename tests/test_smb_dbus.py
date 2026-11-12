import asyncio
import json
from types import SimpleNamespace

from dbus_next import Message, Variant

from udeck.smb_files import OBJECT_PATH, SERVICE, daemon
from udeck.smb_files.lifecycle import Actor


def test_dbus_rejects_configuration_without_polkit_and_uses_bus_sender(monkeypatch):
    async def scenario():
        calls, replies = [], []

        async def credentials(bus, sender):
            calls.append(("credentials", sender))
            return Actor(uid=1000, gid=1000, name="localuser", pid=123)

        async def denied(bus, sender):
            calls.append(("polkit", sender))
            raise PermissionError("not authorized")

        async def send(message):
            replies.append(json.loads(message.body[0]))

        monkeypatch.setattr(daemon, "credentials", credentials)
        monkeypatch.setattr(daemon, "authorize", denied)
        dispatcher = daemon.Dispatcher(SimpleNamespace(send=send), SimpleNamespace())
        message = Message(path=OBJECT_PATH, interface=SERVICE, member="Configure", sender=":1.123", serial=1,
                          signature="s", body=[json.dumps({"uid": 0, "username": "root", "sender": ":1.1"})])
        await dispatcher.dispatch(message)
        assert calls == [("credentials", ":1.123"), ("polkit", ":1.123")]
        assert replies == [{"error": "not authorized"}]
    asyncio.run(scenario())


def test_polkit_authorizes_the_unique_bus_name(monkeypatch):
    async def scenario():
        calls = []

        async def call(*args):
            # Exercise dbus-next's actual wire marshaller, including struct types.
            Message(path="/test", interface="org.test.Authorization", member="Check", signature=args[-2], body=args[-1])._marshall()
            calls.append(args)
            return [(True, False, {})]

        monkeypatch.setattr(daemon, "call", call)
        await daemon.authorize(object(), ":1.45")
        subject = calls[0][-1][0]
        assert subject[0] == "system-bus-name"
        assert subject[1] == {"name": Variant("s", ":1.45")}
        assert calls[0][-1][1] == SERVICE + ".manage"
    asyncio.run(scenario())


def test_timed_owner_rejects_pid_reuse_and_session_logout(monkeypatch):
    async def scenario():
        actor = Actor(uid=1000, gid=1000, name="localuser", pid=123, start_time="old", session="/session/one")
        monkeypatch.setattr(daemon, "process_start", lambda pid: "new")
        assert not await daemon.owner_alive(None, actor)
        monkeypatch.setattr(daemon, "process_start", lambda pid: "old")

        async def closing(*args):
            return [Variant("s", "closing")]

        monkeypatch.setattr(daemon, "call", closing)
        assert not await daemon.owner_alive(None, actor)
    asyncio.run(scenario())
