import asyncio

import pytest


def test_duration_defaults_and_persistence(tmp_path):
    from udeck.network_files.lifecycle import ShareSettings
    settings=ShareSettings(tmp_path / "network.json")
    assert settings.load()["duration"] == 0
    settings.save({"enabled":True,"duration":3600,"root":str(tmp_path),"networks":["wifi@home"]})
    assert not settings.load()["enabled"]
    settings.save({"enabled":True,"duration":0,"root":str(tmp_path),"networks":["wifi@home"]})
    assert settings.load()["enabled"]
    assert (tmp_path / "network.json").stat().st_mode & 0o777 == 0o600


def test_network_selection_does_not_expand_and_timer_closes(tmp_path):
    async def scenario():
        from udeck.network_files.lifecycle import ShareManager
        manager=ShareManager(tmp_path / "network.json",port=0)
        row={"key":"wifi@home","id":"wifi","connection":"home","name":"Home","interface":"test","addresses":["127.0.0.1"]}
        await manager.configure({"root":str(tmp_path),"duration":3600,"networks":[row["key"]],"owner":"owner"},candidates=[row])
        assert manager.status()["state"] == "running"
        assert len(manager.status()["urls"]) == 1
        await manager.reconcile([{**row,"key":"wifi@other","connection":"other"}])
        assert manager.status()["state"] == "waiting"
        assert not manager.status()["urls"]
        await manager.reconcile([row])
        assert manager.status()["state"] == "running"
        manager.deadline=0
        await manager.tick(candidates=[row],owner_alive=True)
        assert manager.status()["state"] == "stopped"
        assert not manager.status()["enabled"]
        await manager.close()
    asyncio.run(scenario())


def test_temporary_share_stops_with_owner(tmp_path):
    async def scenario():
        from udeck.network_files.lifecycle import ShareManager
        manager=ShareManager(tmp_path / "config.json",port=0)
        row={"key":"test","name":"Test","addresses":["127.0.0.1"]}
        await manager.configure({"root":str(tmp_path),"duration":21600,"networks":["test"],"owner":"session"},candidates=[row])
        await manager.tick(candidates=[row],owner_alive=False)
        assert manager.status()["state"] == "stopped"
        await manager.close()
    asyncio.run(scenario())


def test_replaced_root_stops_access_and_does_not_share_replacement(tmp_path):
    async def scenario():
        from udeck.network_files.lifecycle import ShareManager
        root = tmp_path / "share"
        root.mkdir()
        manager = ShareManager(tmp_path / "config.json", port=0)
        row = {"key": "home", "addresses": ["127.0.0.1"]}
        await manager.configure({"root": str(root), "duration": 0, "networks": ["home"]}, candidates=[row])
        root.rename(tmp_path / "previous")
        root.mkdir()
        try:
            await manager.reconcile([row])
            assert not manager.status()["urls"]
            assert not manager.status()["enabled"]
            assert manager.status()["errors"]
            await manager.reconcile([row])
            assert not manager.status()["urls"]
        finally:
            await manager.close()
    asyncio.run(scenario())


def test_network_revocation_closes_existing_connection(tmp_path):
    async def scenario():
        from urllib.parse import urlsplit

        from udeck.network_files.lifecycle import ShareManager
        manager = ShareManager(tmp_path / "config.json", port=0)
        row = {"key": "home", "addresses": ["127.0.0.1"]}
        await manager.configure({"root": str(tmp_path), "duration": 0, "networks": ["home"]}, candidates=[row])
        address = urlsplit(manager.status()["urls"][0])
        reader, writer = await asyncio.open_connection(address.hostname, address.port)
        try:
            writer.write(f"GET /api/config HTTP/1.1\r\nHost: {address.netloc}\r\n\r\n".encode())
            await writer.drain()
            header = await reader.readuntil(b"\r\n\r\n")
            size = next(int(line.split(b":", 1)[1]) for line in header.split(b"\r\n") if line.lower().startswith(b"content-length:"))
            await reader.readexactly(size)
            await manager.reconcile([])
            assert await asyncio.wait_for(reader.read(), 2) == b""
        finally:
            writer.close()
            await writer.wait_closed()
            await manager.close()
    asyncio.run(scenario())


def test_invalid_persistent_settings_never_enable_access(tmp_path):
    import json

    from udeck.network_files.lifecycle import ShareSettings
    settings = ShareSettings(tmp_path / "config.json")
    for value in ({"enabled": "false", "networks": ["home"]},
                  {"enabled": True, "root": [], "networks": ["home"]},
                  {"enabled": True, "root": str(tmp_path), "networks": "home"},
                  {"enabled": True, "root": str(tmp_path), "duration": False, "networks": ["home"]}):
        settings.path.write_text(json.dumps(value))
        assert not settings.load()["enabled"]


def test_stop_closes_listeners_even_when_settings_cannot_be_saved(tmp_path, monkeypatch):
    from udeck.network_files.lifecycle import ShareManager

    async def scenario():
        manager = ShareManager(tmp_path / "config.json", port=0)
        row = {"key": "home", "addresses": ["127.0.0.1"]}
        await manager.configure({"root": str(tmp_path), "duration": 0, "networks": ["home"]}, candidates=[row])

        def fail_save(value):
            raise OSError("No space left on device")

        monkeypatch.setattr(manager.settings, "save", fail_save)
        try:
            with pytest.raises(OSError, match="No space left"):
                await manager.stop()
            assert not manager.listeners, "A failed settings write left the shared files accessible"
            assert manager.runner is None
            assert not manager.status()["enabled"]
        finally:
            await manager.close()
    asyncio.run(scenario())


def test_failed_configuration_save_never_starts_the_unsaved_share(tmp_path, monkeypatch):
    from udeck.network_files.lifecycle import ShareManager

    async def scenario():
        manager = ShareManager(tmp_path / "config.json", port=0)
        row = {"key": "home", "addresses": ["127.0.0.1"]}

        def fail_save(value):
            raise OSError("No space left on device")

        monkeypatch.setattr(manager.settings, "save", fail_save)
        try:
            with pytest.raises(OSError, match="No space left"):
                await manager.configure({"root": str(tmp_path), "duration": 0, "networks": ["home"]}, candidates=[row])
            await manager.tick(candidates=[row])
            assert not manager.listeners, "A failed configuration was activated by the next network tick"
            assert not manager.status()["enabled"]
        finally:
            await manager.close()
    asyncio.run(scenario())


def test_failed_reconfiguration_preserves_the_previously_saved_share(tmp_path, monkeypatch):
    from udeck.network_files.lifecycle import ShareManager

    async def scenario():
        original = tmp_path / "original"
        replacement = tmp_path / "replacement"
        original.mkdir()
        replacement.mkdir()
        manager = ShareManager(tmp_path / "config.json", port=0)
        row = {"key": "home", "addresses": ["127.0.0.1"]}
        await manager.configure({"root": str(original), "duration": 0, "networks": ["home"]}, candidates=[row])
        runner, urls = manager.runner, manager.status()["urls"]

        def fail_save(value):
            raise OSError("No space left on device")

        monkeypatch.setattr(manager.settings, "save", fail_save)
        try:
            with pytest.raises(OSError, match="No space left"):
                await manager.configure({"root": str(replacement), "duration": 0, "networks": ["home"]}, candidates=[row])
            assert manager.status()["root"] == str(original)
            assert manager.runner is runner and manager.status()["urls"] == urls
            await manager.tick(candidates=[row])
            assert manager.status()["root"] == str(original)
        finally:
            await manager.close()
    asyncio.run(scenario())


def test_replaced_root_is_revoked_even_if_persistence_fails(tmp_path, monkeypatch):
    from udeck.network_files.lifecycle import ShareManager

    async def scenario():
        root = tmp_path / "share"
        root.mkdir()
        manager = ShareManager(tmp_path / "config.json", port=0)
        row = {"key": "home", "addresses": ["127.0.0.1"]}
        await manager.configure({"root": str(root), "duration": 0, "networks": ["home"]}, candidates=[row])
        root.rename(tmp_path / "previous")
        root.mkdir()

        def fail_save(value):
            raise OSError("No space left on device")

        monkeypatch.setattr(manager.settings, "save", fail_save)
        try:
            with pytest.raises(OSError, match="No space left"):
                await manager.reconcile([row])
            assert not manager.listeners and manager.runner is None
            assert not manager.status()["enabled"]
        finally:
            await manager.close()
    asyncio.run(scenario())


def test_start_failure_restores_previous_web_configuration(tmp_path, monkeypatch):
    from aiohttp import web

    from udeck.network_files.lifecycle import ShareManager

    async def scenario():
        first, second = tmp_path / "first", tmp_path / "second"
        first.mkdir()
        second.mkdir()
        manager = ShareManager(tmp_path / "config.json", port=0)
        row = {"key": "home", "addresses": ["127.0.0.1"]}
        await manager.configure({"root": str(first), "networks": ["home"]}, candidates=[row])
        start = web.TCPSite.start
        fail = True

        async def fail_once(site):
            nonlocal fail
            if fail:
                fail = False
                raise OSError("port already in use")
            await start(site)

        monkeypatch.setattr(web.TCPSite, "start", fail_once)
        try:
            with pytest.raises(OSError, match="port already in use"):
                await manager.configure({"root": str(second), "networks": ["home"]}, candidates=[row])
            assert manager.status()["root"] == str(first)
            assert manager.status()["state"] == "running"
            assert manager.settings.load()["root"] == str(first)
        finally:
            await manager.close()
    asyncio.run(scenario())
