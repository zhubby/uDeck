import asyncio
import os
import sys

import pytest
from aiohttp import web
from test_network_files_edges import workspace

from udeck.file_trash import TrashStore


@pytest.mark.parametrize("scenario", [
    "history", "destination-loading", "destination-race", "hidden-destination", "destination-pagination",
    "file-workflow", "pagination", "initial-reconnect", "initial-reconnect-folder", "reconnect-refresh", "failed-load", "missing-folder",
])
def test_network_files_web_interactions(tmp_path, monkeypatch, scenario):
    if scenario.startswith("initial-reconnect"):
        from udeck.network_files import server
        original_config = server.configuration
        requests = 0

        async def configuration(request):
            nonlocal requests
            requests += 1
            if requests == 2:
                raise web.HTTPServiceUnavailable(reason="Temporary connection failure")
            return await original_config(request)

        monkeypatch.setattr(server, "configuration", configuration)

    async def check():
        root = tmp_path / "share"
        root.mkdir()
        (root / "Documents").mkdir()
        (root / "Documents/readme.txt").write_text("document")
        (root / ".hidden-folder").mkdir()
        (root / "target").mkdir()
        (root / "hello.txt").write_text("hello")
        if scenario == "pagination":
            (root / "pages").mkdir()
            for index in range(205):
                (root / "pages" / f"item-{index:03}.txt").write_text(str(index))
        if scenario == "destination-pagination":
            (root / "many").mkdir()
            for index in range(501):
                (root / "many" / f"folder-{index:03}").mkdir()
        async with workspace(root, tmp_path / "state") as (_, _, url, _):
            page_url = url.rstrip("/") + "/#Documents" if scenario == "initial-reconnect-folder" else url
            process = await asyncio.create_subprocess_exec(
                sys.executable, "tests/network_files_web_probe.py", page_url, scenario,
                env={**os.environ, "QT_QPA_PLATFORM": "offscreen", "QT_QUICK_BACKEND": "software",
                     "QTWEBENGINE_CHROMIUM_FLAGS": "--disable-gpu", "XDG_CONFIG_HOME": str(tmp_path / "config"),
                     "XDG_DATA_HOME": str(tmp_path / "data")},
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(process.communicate(), 40)
            except TimeoutError:
                process.kill()
                stdout, stderr = await process.communicate()
                pytest.fail("Browser probe timed out: " + (stdout + stderr).decode())
            assert process.returncode == 0, (stdout + stderr).decode()
            if scenario == "file-workflow":
                assert (root / "target/已重命名.txt").read_text() == "browser upload"
                assert not (root / "Documents/已重命名.txt").exists()
                trash = TrashStore(roots=[{"path": str(tmp_path / "state/Trash"), "top": str(root), "home": True}])
                entries = trash.entries()
                assert len(entries) == 1 and entries[0]["name"] == "已重命名.txt"
                assert trash.restore(entries[0]).read_text() == "browser upload"
    asyncio.run(check())
