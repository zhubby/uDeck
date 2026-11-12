import asyncio
import io
import os
import threading
import zipfile
from contextlib import asynccontextmanager

import pytest
from aiohttp import ClientSession, web


@asynccontextmanager
async def workspace(root, state):
    from udeck.network_files.server import create_app
    app = create_app(root, state_directory=state)
    runner = web.AppRunner(app, shutdown_timeout=.2)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    url = "http://127.0.0.1:" + str(site._server.sockets[0].getsockname()[1])
    try:
        async with ClientSession() as client:
            response = await client.get(url + "/api/config")
            token = (await response.json())["requestToken"]
            yield app, client, url, {"X-UDeck-Request": token}
    finally:
        await runner.cleanup()


def test_conflicts_batch_move_trash_and_partial_failure(tmp_path):
    async def scenario():
        root = tmp_path / "share"
        root.mkdir()
        (root / "target").mkdir()
        (root / "a.txt").write_text("source")
        (root / "target/a.txt").write_text("existing")
        async with workspace(root, tmp_path / "state") as (_, client, url, headers):
            response = await client.post(url + "/api/conflicts", json={"paths": ["a.txt"], "destination": "target"}, headers=headers)
            assert (await response.json())["conflicts"] == ["a.txt"]

            async def job(**value):
                response = await client.post(url + "/api/tasks", json=value, headers=headers)
                assert response.status == 200, await response.text()
                task = await response.json()
                for _ in range(100):
                    response = await client.get(url + "/api/tasks/" + task["id"])
                    task = await response.json()
                    if task["state"] not in ("queued", "running"):
                        return task
                    await asyncio.sleep(.01)
                pytest.fail("The file task never completed")

            task = await job(action="copy", paths=["a.txt"], destination="target", policy="keep")
            assert task["state"] == "completed"
            assert (root / "target/a (2).txt").read_text() == "source"
            task = await job(action="move", paths=["a.txt", "missing"], destination="target", policy="replace")
            assert task["state"] == "failed" and task["doneItems"] == 1
            assert task["errors"][0]["path"] == "missing"
            assert not (root / "a.txt").exists()
            assert (root / "target/a.txt").read_text() == "source"
            task = await job(action="trash", paths=["target/a.txt"])
            assert task["state"] == "completed"
            assert not (root / "target/a.txt").exists()
            from udeck.file_trash import TrashStore
            trash = TrashStore(roots=[{"path": str(tmp_path / "state/Trash"), "top": str(root), "home": True}])
            entries = trash.entries()
            assert len(entries) == 1 and entries[0]["name"] == "a.txt"
            assert trash.restore(entries[0]).read_text() == "source"
    asyncio.run(scenario())


@pytest.mark.parametrize("host", ["[", "[invalid]"])
def test_malformed_host_is_rejected_without_server_error(tmp_path, host):
    async def scenario():
        root = tmp_path / "share"
        root.mkdir()
        async with workspace(root, tmp_path / "state") as (_, client, url, _):
            response = await client.get(url + "/api/files", headers={"Host": host})
            assert response.status == 403, await response.text()
            assert (await response.json())["error"] == "Invalid server address"
    asyncio.run(scenario())


@pytest.mark.parametrize("policy", ["error", "keep", "replace"])
def test_upload_cancelled_while_waiting_to_commit_does_not_publish(tmp_path, policy):
    from udeck.network_files.server import STATE

    async def scenario():
        root = tmp_path / "share"
        root.mkdir()
        if policy == "replace":
            (root / "late.txt").write_bytes(b"original")
        async with workspace(root, tmp_path / "state") as (app, client, url, headers):
            response = await client.post(url + "/api/uploads", headers=headers,
                                         json={"path": "late.txt", "size": 3, "policy": policy})
            assert response.status == 200, await response.text()
            ticket = (await response.json())["id"]
            lock = app[STATE].mutation_lock
            await lock.acquire()
            pending = asyncio.create_task(client.put(url + "/api/uploads/" + ticket, data=b"new", headers=headers))
            try:
                async with asyncio.timeout(5):
                    while not lock._waiters:
                        await asyncio.sleep(.01)
                response = await client.delete(url + "/api/uploads/" + ticket, headers=headers)
                assert response.status == 200
            finally:
                lock.release()
            response = await asyncio.wait_for(pending, 5)
            assert response.status == 400, await response.text()
            assert (await response.json())["error"] == "Upload cancelled"
            assert not list(root.glob(".udeck-web-*"))
            assert ticket not in app[STATE].uploads
            if policy == "replace":
                assert (root / "late.txt").read_bytes() == b"original"
            else:
                assert not (root / "late.txt").exists()
    asyncio.run(scenario())


def test_upload_cancelled_during_sync_preserves_existing_file(tmp_path, monkeypatch):
    from udeck.network_files.filesystem import SharedRoot

    (tmp_path / "existing.txt").write_bytes(b"original")
    root = SharedRoot(tmp_path)
    cancelled = threading.Event()
    original_sync = os.fsync

    def cancel_after_sync(descriptor):
        original_sync(descriptor)
        cancelled.set()

    monkeypatch.setattr(os, "fsync", cancel_after_sync)
    upload = root.begin_upload("existing.txt", 3, "replace")
    try:
        upload.write(b"new")
        with pytest.raises(ValueError, match="Upload cancelled"):
            upload.commit(cancelled)
        assert upload.closed
        assert (tmp_path / "existing.txt").read_bytes() == b"original"
        assert not list(tmp_path.glob(".udeck-web-*"))
    finally:
        upload.abort()
        root.close()


@pytest.mark.parametrize(("sent", "policy"), [(0, "error"), (1, "error"), (1, "replace")])
def test_cancelling_stalled_upload_releases_session_and_temporary_file(tmp_path, sent, policy):
    from urllib.parse import urlsplit

    from udeck.network_files.server import STATE

    async def scenario():
        root = tmp_path / "share"
        root.mkdir()
        if policy == "replace":
            (root / "stalled.txt").write_bytes(b"original")
        async with workspace(root, tmp_path / "state") as (app, client, url, headers):
            response = await client.post(url + "/api/uploads", headers=headers,
                                         json={"path": "stalled.txt", "size": 3, "policy": policy})
            assert response.status == 200, await response.text()
            ticket = (await response.json())["id"]
            address = urlsplit(url)
            reader, writer = await asyncio.open_connection(address.hostname, address.port)
            try:
                request = (f"PUT /api/uploads/{ticket} HTTP/1.1\r\nHost: {address.netloc}\r\n"
                           f"X-UDeck-Request: {headers['X-UDeck-Request']}\r\nContent-Length: 3\r\n\r\n")
                writer.write(request.encode() + b"a" * sent)
                await writer.drain()
                async with asyncio.timeout(3):
                    while not app[STATE].uploads[ticket]["active"] or app[STATE].uploads[ticket]["upload"].written != sent:
                        await asyncio.sleep(.01)
                response = await client.delete(url + "/api/uploads/" + ticket, headers=headers)
                assert response.status == 200
                async with asyncio.timeout(3):
                    while ticket in app[STATE].uploads:
                        await asyncio.sleep(.01)
                header = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 3)
                assert header.startswith(b"HTTP/1.1 400"), header
                assert not list(root.glob(".udeck-web-*"))
                if policy == "replace":
                    assert (root / "stalled.txt").read_bytes() == b"original"
                else:
                    assert not (root / "stalled.txt").exists()
            finally:
                writer.close()
                await writer.wait_closed()
    asyncio.run(scenario())


def test_cancelled_upload_waiting_for_a_transfer_slot_is_released(tmp_path):
    from urllib.parse import urlsplit

    from udeck.network_files.server import STATE

    async def scenario():
        root = tmp_path / "share"
        root.mkdir()
        async with workspace(root, tmp_path / "state") as (app, client, url, headers):
            response = await client.post(url + "/api/uploads", headers=headers, json={"path": "queued.txt", "size": 3})
            ticket = (await response.json())["id"]
            limit = app[STATE].upload_limit
            await limit.acquire()
            await limit.acquire()
            address = urlsplit(url)
            reader, writer = await asyncio.open_connection(address.hostname, address.port)
            try:
                request = (f"PUT /api/uploads/{ticket} HTTP/1.1\r\nHost: {address.netloc}\r\n"
                           f"X-UDeck-Request: {headers['X-UDeck-Request']}\r\nContent-Length: 3\r\n\r\nabc")
                writer.write(request.encode())
                await writer.drain()
                async with asyncio.timeout(3):
                    while not app[STATE].uploads[ticket]["active"]:
                        await asyncio.sleep(.01)
                response = await client.delete(url + "/api/uploads/" + ticket, headers=headers)
                assert response.status == 200
                async with asyncio.timeout(3):
                    while ticket in app[STATE].uploads:
                        await asyncio.sleep(.01)
                header = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 3)
                assert header.startswith(b"HTTP/1.1 400"), header
                assert not list(root.iterdir())
            finally:
                limit.release()
                limit.release()
                writer.close()
                await writer.wait_closed()
    asyncio.run(scenario())


def test_repeated_upload_cancellation_waits_for_the_file_worker(tmp_path, monkeypatch):
    from udeck.network_files.server import STATE

    async def scenario():
        root = tmp_path / "share"
        root.mkdir()
        async with workspace(root, tmp_path / "state") as (app, client, url, headers):
            response = await client.post(url + "/api/uploads", headers=headers, json={"path": "writing.txt", "size": 3})
            ticket = (await response.json())["id"]
            upload = app[STATE].uploads[ticket]["upload"]
            started, release = threading.Event(), threading.Event()
            original_write = upload.write

            def slow_write(data):
                started.set()
                assert release.wait(5)
                original_write(data)

            monkeypatch.setattr(upload, "write", slow_write)
            pending = asyncio.create_task(client.put(url + "/api/uploads/" + ticket, data=b"abc", headers=headers))
            try:
                assert await asyncio.to_thread(started.wait, 3)
                for _attempt in range(2):
                    response = await client.delete(url + "/api/uploads/" + ticket, headers=headers)
                    assert response.status == 200
                assert not upload.closed, "Cancellation closed a file descriptor still owned by the worker"
            finally:
                release.set()
                response = await asyncio.wait_for(pending, 5)
            assert response.status == 400, await response.text()
            assert upload.closed and not app[STATE].workers
            assert not list(root.iterdir())
    asyncio.run(scenario())


def test_directory_upload_policy_and_rename_are_non_destructive(tmp_path):
    async def scenario():
        root = tmp_path / "share"
        root.mkdir()
        (root / "folder").mkdir()
        (root / "folder/existing.txt").write_text("keep")
        async with workspace(root, tmp_path / "state") as (_, client, url, headers):
            for policy, status in (("error", 409), ("replace", 400)):
                response = await client.post(url + "/api/folders", json={"path": "folder", "policy": policy}, headers=headers)
                assert response.status == status, await response.text()
            response = await client.post(url + "/api/folders", json={"path": "folder", "policy": "keep"}, headers=headers)
            assert (await response.json())["path"] == "folder (2)"
            response = await client.post(url + "/api/rename", json={"path": "folder (2)", "name": "中文"}, headers=headers)
            assert response.status == 200
            response = await client.post(url + "/api/rename", json={"path": "中文", "name": "folder"}, headers=headers)
            assert response.status == 409
            assert (root / "folder/existing.txt").read_text() == "keep"
            assert (root / "中文").is_dir()
    asyncio.run(scenario())


def test_cancelled_wrong_size_and_racing_uploads_leave_no_partial_files(tmp_path):
    async def scenario():
        root = tmp_path / "share"
        root.mkdir()
        async with workspace(root, tmp_path / "state") as (_, client, url, headers):
            async def create(path="upload.bin", size=3):
                response = await client.post(url + "/api/uploads", json={"path": path, "size": size}, headers=headers)
                assert response.status == 200, await response.text()
                return (await response.json())["id"]
            pending = await create()
            response = await client.put(url + "/api/uploads/" + pending, data=b"ab", headers=headers)
            assert response.status == 400
            assert not (root / "upload.bin").exists()
            pending = await create()
            await client.delete(url + "/api/uploads/" + pending, headers=headers)
            assert not list(root.iterdir())
            first, second = await create(), await create()
            statuses = []
            for ticket in (first, second):
                response = await client.put(url + "/api/uploads/" + ticket, data=b"abc", headers=headers)
                statuses.append(response.status)
            assert statuses == [200, 409]
            assert (root / "upload.bin").read_bytes() == b"abc"
            assert not list(root.glob(".udeck-web-*"))
    asyncio.run(scenario())


def test_host_origin_pagination_and_empty_zip_entries(tmp_path):
    async def scenario():
        root = tmp_path / "share"
        root.mkdir()
        (root / "empty").mkdir()
        (root / "<img src=x onerror=alert(1)>.txt").write_text("plain")
        (root / ".hidden").write_text("hidden")
        async with workspace(root, tmp_path / "state") as (_, client, url, headers):
            response = await client.head(url + "/assets/font/LXGWWenKaiScreen.ttf")
            assert response.status == 200 and "max-age" in response.headers["Cache-Control"]
            response = await client.get(url + "/api/config")
            assert response.headers["Cache-Control"] == "no-store"
            response = await client.get(url + "/api/files", headers={"Host": "attacker.example"})
            assert response.status == 403
            response = await client.post(url + "/api/folders", json={"path": "evil"}, headers={**headers, "Sec-Fetch-Site": "cross-site"})
            assert response.status == 403
            response = await client.get(url + "/api/files?limit=1")
            data = await response.json()
            assert len(data["entries"]) == 1 and data["total"] == 2
            response = await client.get(url + "/api/files?hidden=1")
            assert (await response.json())["total"] == 3
            response = await client.post(url + "/api/archives", json={"paths": ["empty"]}, headers=headers)
            ticket = await response.json()
            response = await client.get(url + "/api/archives/" + ticket["id"])
            with zipfile.ZipFile(io.BytesIO(await response.read())) as archive:
                assert archive.namelist() == ["empty/"]
            response = await client.get(url + "/api/download?path=.hidden", headers={"Range": "bytes=-3"})
            assert response.status == 206 and await response.read() == b"den"
    asyncio.run(scenario())


def test_copy_cancellation_and_special_files_do_not_publish_staging(tmp_path):
    from udeck.network_files.filesystem import SharedRoot
    (tmp_path / "target").mkdir()
    (tmp_path / "source").mkdir()
    (tmp_path / "source/data").write_bytes(os.urandom(2 * 1024 * 1024))
    outside = tmp_path.parent / (tmp_path.name + "-outside")
    outside.mkdir(exist_ok=True)
    (outside / "secret").write_text("secret")
    (tmp_path / "source/link").symlink_to(outside, target_is_directory=True)
    fs = SharedRoot(tmp_path)
    try:
        with pytest.raises((ValueError, OSError)):
            fs.transfer("source", "target")
        assert not list((tmp_path / "target").iterdir())
        (tmp_path / "source/link").unlink()
        cancelled = threading.Event()
        with pytest.raises(InterruptedError):
            fs.transfer("source", "target", cancelled=cancelled, progress=lambda _: cancelled.set())
        assert not list((tmp_path / "target").iterdir())
        assert (tmp_path / "source/data").stat().st_size == 2 * 1024 * 1024
        os.mkfifo(tmp_path / "fifo")
        with pytest.raises(ValueError):
            fs.open_file("fifo")
    finally:
        fs.close()


def test_moved_upload_parent_cannot_publish_outside_shared_root(tmp_path):
    from udeck.network_files.filesystem import SharedRoot
    root = tmp_path / "share"
    root.mkdir()
    (root / "folder").mkdir()
    fs = SharedRoot(root)
    try:
        upload = fs.begin_upload("folder/file.bin", 3)
        (root / "folder").rename(tmp_path / "outside")
        upload.write(b"abc")
        with pytest.raises(OSError):
            upload.commit()
        assert not list((tmp_path / "outside").iterdir())
    finally:
        fs.close()


def test_permanent_service_restore_and_port_conflict_report(tmp_path):
    async def scenario():
        from udeck.network_files.lifecycle import ShareManager
        row = {"key": "home", "addresses": ["127.0.0.1"]}
        config = tmp_path / "config.json"
        first = ShareManager(config, port=0)
        await first.configure({"root": str(tmp_path), "networks": ["home"], "duration": 0}, candidates=[row])
        port = next(iter(first.listeners.values()))["site"]._server.sockets[0].getsockname()[1]
        restored = ShareManager(config, port=port)
        try:
            await restored.reconcile([row])
            assert restored.status()["state"] == "waiting"
            assert restored.status()["errors"] and not restored.status()["urls"]
            await first.close()
            await restored.reconcile([row])
            assert restored.status()["state"] == "running"
            await restored.stop()
        finally:
            await first.close()
            await restored.close()
        assert not ShareManager(config).value["enabled"]
    asyncio.run(scenario())


def test_cancelled_request_waits_for_descriptor_worker(tmp_path):
    async def scenario():
        from udeck.network_files.server import Workspace
        server = Workspace(tmp_path)
        entered, finish = threading.Event(), threading.Event()
        def blocking():
            entered.set()
            finish.wait(2)
            return os.fstat(server.fs.fd).st_ino
        request = asyncio.create_task(server.run(blocking))
        await asyncio.to_thread(entered.wait, 2)
        request.cancel()
        await asyncio.sleep(.01)
        assert not request.done()
        finish.set()
        with pytest.raises(asyncio.CancelledError):
            await request
        await server.close()
    asyncio.run(scenario())


def test_linux_network_identity_fails_closed_without_metadata(monkeypatch):
    from udeck.network_files import networks
    monkeypatch.setattr(networks.sys, "platform", "linux")
    monkeypatch.setattr(networks, "interfaces", lambda: [{"id": "mac:one", "kind": "wifi", "key": "mac:one", "connection": "", "addresses": ["192.0.2.1"]}])
    assert asyncio.run(networks.discover()) == []


def test_wifi_selection_uses_permanent_adapter_and_connection_uuid(monkeypatch):
    from types import SimpleNamespace

    from dbus_next import Variant

    from udeck.network_files import networks
    row = {"id": "mac:random", "interface": "wlan1", "kind": "wifi", "name": "wlan1",
           "key": "mac:random", "connection": "", "addresses": ["192.0.2.1"]}
    monkeypatch.setattr(networks, "interfaces", lambda: [dict(row)])
    class Bus:
        connection = "home"
        async def call(self, message):
            if message.member == "GetDevices":
                return SimpleNamespace(error_name=None, body=[["/device"]])
            values = {
                "org.freedesktop.NetworkManager.Device": {"Interface": Variant("s", "wlan1"), "DeviceType": Variant("u", 2), "ActiveConnection": Variant("o", "/active")},
                "org.freedesktop.NetworkManager.Connection.Active": {"Uuid": Variant("s", self.connection), "State": Variant("u", 2), "Id": Variant("s", "Home")},
                "org.freedesktop.NetworkManager.Device.Wireless": {"PermHwAddress": Variant("s", "AA:BB:CC:DD:EE:FF")},
            }
            return SimpleNamespace(error_name=None, body=[values[message.body[0]]])
    bus = Bus()
    first = asyncio.run(networks.discover(bus))
    assert first[0]["key"] == "mac:aa:bb:cc:dd:ee:ff@home"
    bus.connection = "other"
    assert asyncio.run(networks.discover(bus))[0]["key"] != first[0]["key"]


def test_disconnect_aborts_upload_and_streaming_zip(tmp_path):
    async def scenario():
        from udeck.network_files.server import STATE
        root = tmp_path / "share"
        root.mkdir()
        (root / "large.bin").write_bytes(os.urandom(4 * 1024 * 1024))
        async with workspace(root, tmp_path / "state") as (app, client, url, headers):
            response = await client.post(url + "/api/uploads", json={"path": "interrupted.bin", "size": 1048576}, headers=headers)
            ticket = (await response.json())["id"]
            sent, release = asyncio.Event(), asyncio.Event()
            async def content():
                yield b"partial" * 4096
                sent.set()
                await release.wait()
            request = asyncio.create_task(client.put(url + "/api/uploads/" + ticket, data=content(), headers={**headers, "Content-Length": "1048576"}))
            await sent.wait()
            request.cancel()
            with pytest.raises(asyncio.CancelledError):
                await request
            for _ in range(100):
                if not app[STATE].uploads:
                    break
                await asyncio.sleep(.01)
            assert not app[STATE].uploads
            assert not (root / "interrupted.bin").exists()
            assert not list(root.glob(".udeck-web-*"))
            response = await client.post(url + "/api/archives", json={"paths": ["large.bin"]}, headers=headers)
            ticket = (await response.json())["id"]
            response = await client.get(url + "/api/archives/" + ticket)
            await response.content.read(1024)
            response.close()
        assert not app[STATE].workers and app[STATE].fs.fd == -1
    asyncio.run(scenario())
