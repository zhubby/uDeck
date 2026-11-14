"""Exercise the actual rclone binary against isolated local cloud remotes."""

import asyncio
import shutil
import socket
import subprocess
from pathlib import Path

import pytest
from test_emulator_save_management import context


@pytest.mark.skipif(not shutil.which("rclone"), reason="rclone is not installed")
def test_real_rclone_two_devices_history_conflicts_and_restart(tmp_path):
    from udeck.emulator_saves.native import SaveManager
    from udeck.emulator_saves.sync import SyncManager

    cloud = tmp_path / "cloud files 中文"
    cloud.mkdir()
    config = tmp_path / "rclone.conf"
    config.write_text("[isolated]\ntype = local\n")

    async def run():
        a, b = SaveManager(tmp_path / "a"), SaveManager(tmp_path / "b")
        sa = SyncManager(a.root, rclone_config=config)
        sb = SyncManager(b.root, rclone_config=config)
        assert await sa.remotes() == ["isolated"]
        settings = {"enabled": True, "remote": "isolated", "directory": str(cloud)}
        await sa.configure(settings)
        await sb.configure(settings)
        ctx = context()
        b.register(context("other-id", "改名"))
        source = tmp_path / "native.state"
        source.write_bytes(b"first native state")
        a.import_native(ctx, source, confirmed=True)
        result = await sa.sync()
        assert result["phase"] == "idle", result["error"]
        assert (await sb.sync())["phase"] == "idle"
        assert b.store(context("other-id", "改名")).load("1", "b" * 64, "a" * 64)[0].read_bytes() == b"first native state"
        source.write_bytes(b"offline from A")
        a.import_native(ctx, source, confirmed=True)
        source.write_bytes(b"offline from B")
        b.import_native(context("other-id", "改名"), source, confirmed=True)
        await asyncio.gather(sa.sync(), sb.sync())
        await sa.sync()
        assert (await sb.sync())["phase"] == "conflict"
        conflicts = b.reconcile(context("other-id", "改名"))["conflicts"]
        chosen = next(v for v in conflicts[0]["versions"] if v["deviceId"] == a.history.device_id)
        b.restore(context("other-id", "改名"), chosen["id"])
        await sb.sync()
        await sa.sync()
        assert a.store(ctx).load("1", "b" * 64, "a" * 64)[0].read_bytes() == b"offline from A"
        restarted = SyncManager(a.root, rclone_config=config)
        assert restarted.config["enabled"]
        assert (await restarted.sync())["phase"] == "idle"
        assert len(a.history.entries(ctx)) == 4
        assert len(b.history.entries(ctx)) == 4
        await sa.close()
        await sb.close()
        await restarted.close()

    asyncio.run(run())


@pytest.mark.skipif(not shutil.which("rclone"), reason="rclone is not installed")
def test_real_rclone_cancel_does_not_block_native_saves_and_new_profile_recovers(tmp_path):
    from udeck.emulator_saves.sync import SyncManager

    config = tmp_path / "rclone.conf"
    config.write_text("[isolated]\ntype = local\n")

    async def run():
        manager = SyncManager(tmp_path / "data", rclone_config=config)
        settings = {"enabled": True, "remote": "isolated", "directory": str(tmp_path / "cloud")}
        await manager.configure(settings)
        source = tmp_path / "native.state"
        source.write_bytes(b"old progress")
        manager.saves.import_native(context(), source, confirmed=True)
        assert (await manager.sync())["phase"] == "idle"
        source.write_bytes(b"new progress" * 1000)
        manager.saves.import_native(context(), source, confirmed=True)
        original_run = manager.transport.run
        started = asyncio.Event()

        async def slow(*args, **kwargs):
            if args[0] == "bisync":
                started.set()
                args = (*args, "--bwlimit=1", "--tpslimit=1")
            return await original_run(*args, **kwargs)

        manager.transport.run = slow
        manager.schedule()
        await asyncio.wait_for(started.wait(), 5)
        await asyncio.sleep(0.1)
        # This also models acquiring game ownership for an offline launch.
        with manager.saves.session(context()):
            source.write_bytes(b"offline save during transfer")
            manager.saves.store(context()).publish("1", source, {"contentHash": "b" * 64, "coreHash": "a" * 64})
            await asyncio.wait_for(asyncio.to_thread(manager.saves.record_state, context(), "1"), 2)
        await asyncio.wait_for(manager.configure({"enabled": False}), 10)
        assert manager.task.done()
        assert manager.transport.process is None
        assert manager.saves.store(context()).load("1", "b" * 64, "a" * 64)[0].read_bytes() == b"offline save during transfer"
        # Restart on the same bisync baseline, then change the cloud profile.
        restarted = SyncManager(manager.root, rclone_config=config)
        await restarted.configure(settings)
        result = await restarted.sync()
        assert result["phase"] == "idle", result["error"]
        await restarted.configure({**settings, "directory": str(tmp_path / "other cloud")})
        result = await restarted.sync()
        assert result["phase"] == "idle", result["error"]
        assert len(restarted.saves.history.entries()) == 3
        await restarted.close()
        await manager.close()

    asyncio.run(run())


@pytest.mark.skipif(not shutil.which("rclone"), reason="rclone is not installed")
def test_corrupted_download_and_missing_access_marker_never_restore(tmp_path):
    from udeck.emulator_saves.sync import SyncManager

    config = tmp_path / "rclone.conf"
    config.write_text("[isolated]\ntype = local\n")

    async def run():
        a = SyncManager(tmp_path / "a", rclone_config=config)
        b = SyncManager(tmp_path / "b", rclone_config=config)
        settings = {"enabled": True, "remote": "isolated", "directory": str(tmp_path / "cloud")}
        await a.configure(settings)
        await b.configure(settings)
        source = tmp_path / "native.state"
        source.write_bytes(b"good progress")
        entry = a.saves.import_native(context(), source, confirmed=True)
        b.saves.register(context())
        assert (await a.sync())["phase"] == "idle"
        destination = Path(a.destination().split(":", 1)[1])
        (destination / entry["deviceId"] / entry["id"] / "Original.state1").write_bytes(b"corrupt")
        result = await b.sync()
        assert result["phase"] == "error" and "damaged" in result["error"]
        assert b.saves.store(context()).manifest() == {}
        assert not b.saves.history.entries()
        # Losing the established remote root must not create a fresh baseline.
        shutil.rmtree(destination)
        result = await a.sync()
        assert result["phase"] == "error" and "marker" in result["error"]
        assert not destination.exists()
        assert a.saves.store(context()).load("1", "b" * 64, "a" * 64)[0].read_bytes() == b"good progress"
        await a.close()
        await b.close()

    asyncio.run(run())


@pytest.mark.skipif(not shutil.which("rclone"), reason="rclone is not installed")
def test_missing_remote_does_not_publish_config_or_replace_local_saves(tmp_path):
    from udeck.emulator_saves.sync import SyncManager

    config = tmp_path / "empty.conf"
    config.write_text("")

    async def run():
        manager = SyncManager(tmp_path / "data", rclone_config=config)
        with pytest.raises(ValueError, match="remote"):
            await manager.configure({"enabled": True, "remote": "missing", "directory": "backups"})
        assert not manager.config["enabled"]
        assert manager.status()["phase"] == "disabled"
        await manager.close()

    asyncio.run(run())


@pytest.mark.skipif(not shutil.which("rclone"), reason="rclone is not installed")
def test_save_queued_during_transfer_is_uploaded_without_waiting_for_idle_timer(tmp_path):
    from udeck.emulator_saves.sync import SyncManager

    config = tmp_path / "rclone.conf"
    config.write_text("[isolated]\ntype = local\n")

    async def run():
        manager = SyncManager(tmp_path / "data", rclone_config=config)
        await manager.configure({"enabled": True, "remote": "isolated", "directory": str(tmp_path / "cloud")})
        source = tmp_path / "Original.state"
        source.write_bytes(b"before transfer")
        manager.saves.import_native(context(), source, confirmed=True)
        started, release = asyncio.Event(), asyncio.Event()
        transport_run = manager.transport.run

        async def paused(*args, **kwargs):
            if args[0] == "bisync":
                started.set()
                await release.wait()
            return await transport_run(*args, **kwargs)

        manager.transport.run = paused
        manager.schedule()
        await asyncio.wait_for(started.wait(), 5)
        source.write_bytes(b"confirmed during transfer")
        new = manager.saves.import_native(context(), source, confirmed=True)
        manager.schedule()
        release.set()
        await asyncio.wait_for(manager.task, 10)
        cloud = Path(manager.destination().split(":", 1)[1])
        assert (cloud / new["deviceId"] / new["id"] / "Original.state1").read_bytes() == source.read_bytes()
        await manager.close()

    asyncio.run(run())


@pytest.mark.skipif(not shutil.which("rclone"), reason="rclone is not installed")
def test_real_webdav_disconnect_and_reconnect_preserves_offline_progress(tmp_path):
    from udeck.emulator_saves.sync import SyncManager

    cloud = tmp_path / "webdav"
    cloud.mkdir()
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    config = tmp_path / "rclone.conf"
    config.write_text(f"[isolated]\ntype = webdav\nurl = http://127.0.0.1:{port}/\nvendor = other\n")

    async def run():
        server = None
        manager = SyncManager(tmp_path / "data", rclone_config=config)

        async def start():
            process = await asyncio.create_subprocess_exec(
                "rclone", "serve", "webdav", str(cloud), "--addr", f"127.0.0.1:{port}",
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                async with asyncio.timeout(5):
                    while True:
                        try:
                            _, writer = await asyncio.open_connection("127.0.0.1", port)
                            writer.close()
                            await writer.wait_closed()
                            return process
                        except OSError:
                            assert process.returncode is None
                            await asyncio.sleep(0.05)
            except BaseException:
                process.terminate()
                await process.wait()
                raise

        try:
            server = await start()
            await manager.configure({"enabled": True, "remote": "isolated", "directory": "save files"})
            source = tmp_path / "Original.state"
            source.write_bytes(b"before disconnect")
            manager.saves.import_native(context(), source, confirmed=True)
            result = await manager.sync()
            assert result["phase"] == "idle", result["error"]
            server.terminate()
            await asyncio.wait_for(server.wait(), 5)
            source.write_bytes(b"saved offline after disconnect")
            new = manager.saves.import_native(context(), source, confirmed=True)
            result = await asyncio.wait_for(manager.sync(), 30)
            assert result["phase"] == "error" and result["error"]
            assert manager.saves.store(context()).load("1", "b" * 64, "a" * 64)[0].read_bytes() == source.read_bytes()
            server = await start()
            restarted = SyncManager(manager.root, rclone_config=config)
            result = await restarted.sync()
            assert result["phase"] == "idle", result["error"]
            remote = cloud / "save files/uDeck/Emulator/v1"
            assert len(list(remote.glob("*/*/manifest.json"))) == 2
            assert (remote / new["deviceId"] / new["id"] / "Original.state1").read_bytes() == source.read_bytes()
            await restarted.close()
        finally:
            await manager.close()
            if server and server.returncode is None:
                server.terminate()
                await asyncio.wait_for(server.wait(), 5)

    asyncio.run(run())
