"""Run the actual headless service on a private session bus and local remote."""

import asyncio
import json
import os
import sys
from pathlib import Path

from dbus_next.aio import MessageBus
from dbus_next.errors import DBusError

from udeck.emulator_saves import OBJECT_PATH, SERVICE
from udeck.emulator_saves.native import SaveManager


async def run(root):
    root.mkdir(parents=True)
    config = root / "rclone.conf"
    config.write_text("[isolated]\ntype = local\n")
    directory = root / "data"
    cloud = root / "cloud"
    context = {"gameId": "test", "title": "Original", "basename": "Original", "platform": "gb",
               "contentHash": "b" * 64, "coreId": "gambatte", "coreHash": "a" * 64}
    saves = SaveManager(directory)
    source = root / "Original.state"
    source.write_bytes(b"native bytes recorded by a frontend that has closed")
    entry = saves.import_native(context, source, confirmed=True)
    environment = {**os.environ, "RCLONE_CONFIG": str(config)}

    async def start():
        process = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "udeck.emulator_saves.daemon", "--directory", str(directory),
            env=environment, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        bus = await MessageBus().connect()
        try:
            async with asyncio.timeout(10):
                while True:
                    try:
                        introspection = await bus.introspect(SERVICE, OBJECT_PATH)
                        break
                    except DBusError:
                        if process.returncode is not None:
                            raise AssertionError((await process.stderr.read()).decode()) from None
                        await asyncio.sleep(0.05)
            interface = bus.get_proxy_object(SERVICE, OBJECT_PATH, introspection).get_interface(SERVICE)
            return process, bus, interface
        except BaseException:
            bus.disconnect()
            process.kill()
            await process.wait()
            raise

    async def stop(process, bus):
        bus.disconnect()
        process.terminate()
        output, error = await asyncio.wait_for(process.communicate(), 10)
        assert process.returncode == 0, (output.decode(), error.decode())

    process, bus, interface = await start()
    try:
        assert json.loads(await interface.call_status())["phase"] == "disabled"
        assert json.loads(await interface.call_remotes())["remotes"] == ["isolated"]
        invalid = json.loads(await interface.call_configure("[]"))
        assert invalid["phase"] == "error"
        states = []
        interface.on_changed(lambda payload: states.append(json.loads(payload)))
        settings = {"enabled": True, "remote": "isolated", "directory": str(cloud)}
        assert json.loads(await interface.call_configure(json.dumps(settings)))["enabled"]
        job = json.loads(await interface.call_sync_now())["jobId"]
        assert json.loads(await interface.call_sync_now())["jobId"] == job
        # Drop the frontend's D-Bus connection; transfer belongs to the daemon.
        bus.disconnect()
        async with asyncio.timeout(15):
            while not list(cloud.glob("**/manifest.json")):
                await asyncio.sleep(0.1)
        bus = await MessageBus().connect()
        introspection = await bus.introspect(SERVICE, OBJECT_PATH)
        interface = bus.get_proxy_object(SERVICE, OBJECT_PATH, introspection).get_interface(SERVICE)
        interface.on_changed(lambda payload: states.append(json.loads(payload)))
        async with asyncio.timeout(15):
            while True:
                status = json.loads(await interface.call_status())
                if status["completedJob"] >= job and status["phase"] != "syncing":
                    assert status["phase"] == "idle", status
                    break
                await asyncio.sleep(0.1)
        assert any(s["enabled"] for s in states)
        assert (cloud / "uDeck/Emulator/v1" / entry["deviceId"] / entry["id"] / "Original.state1").read_bytes() == source.read_bytes()
    finally:
        await stop(process, bus)
    process, bus, interface = await start()
    try:
        async with asyncio.timeout(15):
            while True:
                status = json.loads(await interface.call_status())
                if status["completedJob"]:
                    assert status["enabled"] and status["phase"] == "idle", status
                    break
                await asyncio.sleep(0.1)
    finally:
        await stop(process, bus)
    print(json.dumps({"service": "passed", "restart": "passed", "notifications": len(states)}))


if __name__ == "__main__":
    asyncio.run(run(Path(sys.argv[1])))
