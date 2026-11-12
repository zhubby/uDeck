import asyncio
import io
import os
import zipfile

import pytest
from aiohttp import ClientSession, web


def run(coro):
    return asyncio.run(coro)


def test_network_feature_is_available():
    from udeck.network_files.server import create_app
    assert callable(create_app)


def test_confined_files_and_upload_commit(tmp_path):
    from udeck.network_files.filesystem import SharedRoot
    root=tmp_path / "share"
    root.mkdir()
    outside=tmp_path / "outside"
    outside.mkdir()
    (outside / "secret").write_text("secret")
    (root / "link").symlink_to(outside, target_is_directory=True)
    fs=SharedRoot(root)
    try:
        for path in ("../outside/secret", "/etc/passwd", "link/secret", "a/../b", "a\\b"):
            with pytest.raises((ValueError, OSError)):
                fs.open_file(path)
        upload=fs.begin_upload("中文/空文件.txt", 0, "error", parents=True)
        upload.commit()
        assert (root / "中文/空文件.txt").read_bytes() == b""
        with pytest.raises(FileExistsError):
            fs.begin_upload("中文/空文件.txt", 0, "error")
        pending=fs.begin_upload("cancel.bin", 8, "error")
        pending.write(b"partial")
        pending.abort()
        assert not (root / "cancel.bin").exists()
        assert not list(root.glob(".udeck-web-*"))
        with pytest.raises((ValueError, OSError)):
            fs.begin_upload("link/secret", 1, "replace")
        assert (outside / "secret").read_text() == "secret"
    finally:
        fs.close()


@pytest.mark.parametrize("path", ["", "nested"])
def test_directory_refresh_observes_committed_changes(tmp_path, path):
    from udeck.network_files.filesystem import SharedRoot

    root = tmp_path / "share"
    folder = root / path
    folder.mkdir(parents=True)
    (folder / "original.txt").write_text("original")
    fs = SharedRoot(root)
    try:
        def names():
            return {row["name"] for row in fs.listing(path)["entries"]}

        assert names() == {"original.txt"}
        fs.mkdir("/".join(filter(None, [path, "new-folder"])))
        assert names() == {"original.txt", "new-folder"}
        fs.rename("/".join(filter(None, [path, "original.txt"])), "renamed.txt")
        assert names() == {"renamed.txt", "new-folder"}
        (folder / "renamed.txt").unlink()
        assert names() == {"new-folder"}
    finally:
        fs.close()


def test_real_http_file_workflow(tmp_path):
    async def scenario():
        from udeck.network_files.server import create_app
        root=tmp_path / "share"
        root.mkdir()
        (root / "original.txt").write_bytes(b"original")
        app=create_app(root, state_directory=tmp_path / "state")
        runner=web.AppRunner(app)
        await runner.setup()
        site=web.TCPSite(runner,"127.0.0.1",0)
        await site.start()
        port=site._server.sockets[0].getsockname()[1]
        url=f"http://127.0.0.1:{port}"
        try:
            async with ClientSession() as client:
                response=await client.get(url + "/api/files")
                assert response.status == 200
                assert (await response.json())["entries"][0]["name"] == "original.txt"
                response=await client.get(url + "/api/config")
                config=await response.json()
                headers={"X-UDeck-Request":config["requestToken"]}
                response=await client.post(url + "/api/folders",json={"path":"新文件夹"},headers=headers)
                assert response.status == 200, await response.text()
                content=os.urandom(1024*1024+5)
                response=await client.post(url + "/api/uploads",json={"path":"新文件夹/中文.bin","size":len(content)},headers=headers)
                assert response.status == 200, await response.text()
                upload=await response.json()
                response=await client.put(url + "/api/uploads/"+upload["id"],data=content,headers=headers)
                assert response.status == 200, await response.text()
                assert (root / "新文件夹/中文.bin").read_bytes() == content
                response=await client.get(url + "/api/download",params={"path":"新文件夹/中文.bin"})
                assert await response.read() == content
                response=await client.get(url + "/api/download",params={"path":"original.txt"},headers={"Range":"bytes=1-3"})
                assert response.status == 206
                assert await response.read() == b"rig"
                response=await client.post(url + "/api/tasks",json={"action":"copy","paths":["original.txt"],"destination":"新文件夹"},headers=headers)
                assert response.status == 200, await response.text()
                task=await response.json()
                for _ in range(200):
                    response=await client.get(url + "/api/tasks/"+task["id"])
                    report=await response.json()
                    if report["state"] in ("completed","failed","cancelled"):
                        break
                    await asyncio.sleep(.01)
                assert report["state"] == "completed",report
                response=await client.post(url + "/api/archives",json={"paths":["新文件夹","original.txt"]},headers=headers)
                assert response.status == 200, await response.text()
                ticket=await response.json()
                response=await client.get(url + "/api/archives/"+ticket["id"])
                with zipfile.ZipFile(io.BytesIO(await response.read())) as archive:
                    assert archive.read("新文件夹/中文.bin") == content
                    assert archive.read("original.txt") == b"original"
                assert (await client.get(url + "/api/files",params={"path":"../"})).status == 400
                assert (await client.post(url+"/api/folders",json={"path":"forbidden"})).status == 403
                assert (await client.post(url+"/api/folders",json={"path":"forbidden"},headers={**headers,"Origin":"http://elsewhere"})).status == 403
        finally:
            await runner.cleanup()
    run(scenario())
