"""Worker-thread D-Bus client; no network operation blocks the Qt UI."""

import asyncio
import getpass
import json
import os
import subprocess
import sys
from pathlib import Path

from . import OBJECT_PATH, SERVICE

UNIT = "udeck-network-files.service"


class ServiceUnavailable(RuntimeError):
    pass


def systemd_installed():
    return sys.platform == "linux" and any((Path(root) / UNIT).is_file() for root in (
        "/usr/lib/systemd/user", "/lib/systemd/user", str(Path.home() / ".config/systemd/user")))


def command(arguments):
    result = subprocess.run(arguments, capture_output=True, text=True, timeout=20)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "Could not manage the file service")


def unit_enabled():
    result = subprocess.run(["systemctl", "--user", "is-enabled", UNIT], capture_output=True, text=True, timeout=10)
    return result.stdout.strip() in ("enabled", "enabled-runtime", "linked", "linked-runtime")


async def remote(member, value=None):
    from dbus_next import Message
    from dbus_next.aio import MessageBus
    bus = await MessageBus().connect()
    try:
        result = await asyncio.wait_for(bus.call(Message(destination=SERVICE, path=OBJECT_PATH,
            interface=SERVICE, member=member, signature="s" if value is not None else "",
            body=[json.dumps(value)] if value is not None else [])), 25)
        if result.error_name:
            if result.error_name in ("org.freedesktop.DBus.Error.ServiceUnknown", "org.freedesktop.DBus.Error.NameHasNoOwner"):
                raise ServiceUnavailable("Network access is off")
            raise RuntimeError(result.body[0] if result.body else result.error_name)
        result = json.loads(result.body[0])
        if isinstance(result, dict) and result.get("error"):
            raise RuntimeError(result["error"])
        return result
    finally:
        bus.disconnect()


def status():
    try:
        return asyncio.run(remote("Status"))
    except (ServiceUnavailable, OSError):
        from .lifecycle import ShareSettings
        from .networks import discover
        async def candidates():
            from dbus_next import BusType
            from dbus_next.aio import MessageBus
            bus = None
            try:
                if sys.platform == "linux":
                    try:
                        bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
                    except OSError:
                        return []
                return await discover(bus)
            finally:
                if bus:
                    bus.disconnect()
        state = ShareSettings().load()
        state.update(enabled=False, state="stopped", urls=[], errors=[], candidates=asyncio.run(candidates()))
        return state


def start(value):
    if value["duration"] == 0 and not systemd_installed():
        raise RuntimeError("Install the uDeck systemd user service to keep network access on after restart")
    installed = systemd_installed()
    previously_enabled = unit_enabled() if installed else False
    if installed:
        command(["systemctl", "--user", "start", UNIT])
    else:
        try:
            asyncio.run(remote("Status"))
        except Exception:
            log = Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local/state"))) / "udeck/network-files.log"
            log.parent.mkdir(parents=True, exist_ok=True)
            with log.open("ab") as stream:
                subprocess.Popen([sys.executable, "-m", "udeck.network_files.daemon"], stdin=subprocess.DEVNULL,
                                 stdout=stream, stderr=stream, start_new_session=True)
    async def configure():
        async with asyncio.timeout(10):
            while True:
                try:
                    await remote("Status")
                    break
                except ServiceUnavailable:
                    await asyncio.sleep(.1)
        # Configure persistence before replacing a working share. Failure must not
        # call Stop on the old configuration or expose an unsaved replacement.
        if installed:
            if value["duration"] == 0:
                command(["loginctl", "enable-linger", getpass.getuser()])
                command(["systemctl", "--user", "enable", UNIT])
            else:
                command(["systemctl", "--user", "disable", UNIT])
        return await remote("Configure", value)
    try:
        return asyncio.run(configure())
    except Exception:
        if installed:
            command(["systemctl", "--user", "enable" if previously_enabled else "disable", UNIT])
        raise


def stop():
    try:
        try:
            result = asyncio.run(remote("Stop"))
        except (ServiceUnavailable, OSError):
            from .lifecycle import ShareSettings
            settings = ShareSettings()
            value = settings.load()
            value["enabled"] = False
            settings.save(value)
            result = status()
        return result
    finally:
        if systemd_installed():
            try:
                command(["systemctl", "--user", "disable", UNIT])
            finally:
                command(["systemctl", "--user", "stop", UNIT])
