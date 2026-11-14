import json
import threading
import time

import pytest
from PySide6.QtCore import QCoreApplication
from PySide6.QtTest import QTest

from udeck.apps.emulator.controller import EmulatorController


def wait_for(predicate, timeout=4000):
    until = time.monotonic() + timeout / 1000
    while not predicate() and time.monotonic() < until:
        QCoreApplication.processEvents()
        QTest.qWait(10)
    assert predicate()


def prepared(tmp_path):
    controller = EmulatorController(tmp_path / "data", tmp_path / "settings.json")
    rom = tmp_path / "Original.gb"
    rom.write_bytes(b"original ROM")
    controller.current = {"id": "local-game", "title": "Original", "path": str(rom),
                          "platform": "gb", "sourceId": "test", "format": "GB"}
    controller.checks = {"coreId": "gambatte", "coreHash": "a" * 64, "core": "/cores/gambatte_libretro.so",
                         "contentHash": "b" * 64, "savestate": True}
    return controller


def test_native_import_requires_confirmation_and_keeps_target_visible(tmp_path):
    controller = prepared(tmp_path)
    native = tmp_path / "foreign.state9"
    native.write_bytes(b"real native format bytes")
    try:
        controller.save_import_confirm(str(native), "2")
        menu = json.loads(controller.snapshotJson)["menu"]
        assert "Original" in menu["body"] and "gambatte" in menu["body"]
        assert not list((tmp_path / "data/emulator-saves").glob("**/slots.json"))
        controller.dispatch("accept")
        wait_for(lambda: not controller.save_jobs)
        assert not controller.error
        store = controller.save_manager.store(controller.save_context())
        assert store.load("2", "b" * 64, "a" * 64)[0].read_bytes() == b"real native format bytes"
    finally:
        controller.close()


def test_save_management_and_cloud_settings_use_existing_menu_navigation(tmp_path):
    controller = prepared(tmp_path)
    try:
        controller.detail_menu()
        assert "Save management" in [str(row["title"]) for row in controller.menus[-1]["options"]]
        controller.save_management()
        assert "Import native save" in [str(row["title"]) for row in controller.menus[-1]["options"]]
        controller.save_settings()
        rows = controller.menus[-1]["options"]
        assert "Back up all games" in [str(row["title"]) for row in rows]
        assert not next(row for row in rows if row["title"] == "Cloud sync")["checked"]
        assert json.loads(controller.snapshotJson)["saveSync"]["enabled"] is False
    finally:
        controller.close()


@pytest.mark.parametrize("operation,title", [("save_history", "Save history"), ("save_export_menu", "Export native save")])
def test_loaded_save_menu_clears_finished_work_notice(tmp_path, operation, title):
    controller = prepared(tmp_path)
    source = tmp_path / "Original.state"
    source.write_bytes(b"existing native save")
    try:
        controller.save_manager.import_native(controller.save_context(), source, confirmed=True)
        getattr(controller, operation)()
        wait_for(lambda: not controller.save_jobs)
        snapshot = json.loads(controller.snapshotJson)
        assert snapshot["menu"]["title"] == title
        assert snapshot["saveManagementBusy"] is False
        assert snapshot["notice"] == ""
    finally:
        controller.close()


def test_cloud_launch_failure_offers_explicit_offline_launch_and_cancel(tmp_path, monkeypatch):
    controller = prepared(tmp_path)
    launches = []
    monkeypatch.setattr(controller, "_start_game", lambda resume=False: launches.append(resume))
    monkeypatch.setattr(controller.save_cloud, "request", lambda *args, **kwargs: None)
    controller.save_cloud.state["enabled"] = True
    try:
        controller.start_game(True)
        assert launches == []
        controller.save_cloud_result({"enabled": True, "phase": "error", "error": "offline", "completedJob": 1})
        rows = controller.menus[-1]["options"]
        index = next(i for i, row in enumerate(rows) if str(row["title"]) == "Play offline")
        controller.choose(index)
        assert launches == [True]
        controller.start_game(False)
        controller.cancel_launch()
        controller.save_cloud_result({"enabled": True, "phase": "idle", "jobId": 2, "completedJob": 2})
        assert launches == [True]
    finally:
        controller.close()


def test_cancelled_sync_reply_cannot_complete_a_new_launch(tmp_path, monkeypatch):
    controller = prepared(tmp_path)
    launches, replies = [], []
    monkeypatch.setattr(controller, "_start_game", lambda resume=False: launches.append(resume))
    monkeypatch.setattr(controller.save_cloud, "request", lambda *args, callback=None: replies.append(callback))
    controller.save_cloud.state["enabled"] = True
    try:
        controller.start_game(True)
        controller.save_cancel_wait()
        controller.start_game(False)
        replies[0]({"phase": "idle", "jobId": 1, "completedJob": 1})
        assert launches == []
        replies[1]({"phase": "idle", "jobId": 2, "completedJob": 2})
        assert launches == [False]
    finally:
        controller.close()


def test_autostart_failure_does_not_change_daemon_configuration(tmp_path, monkeypatch):
    import subprocess

    from udeck.emulator_saves import client

    calls = []

    async def service_call(member, payload=None):
        calls.append(member)
        return {"enabled": member == "Configure", "phase": "idle", "remote": "example", "directory": "saves"}

    monkeypatch.setattr(client.sys, "platform", "linux")
    monkeypatch.setattr(client, "service_call", service_call)
    monkeypatch.setattr(client.subprocess, "run", lambda *args, **kwargs:
                        subprocess.CompletedProcess(args[0], 1, "", "systemd session unavailable"))
    cloud = client.SaveCloudClient(tmp_path)
    results = []
    try:
        cloud.request("Configure", {"enabled": True, "remote": "example", "directory": "saves"}, results.append)
        wait_for(lambda: bool(results))
        assert "Configure" not in calls
        assert cloud.state["enabled"] is False
        assert "systemd session" in cloud.state["error"]
    finally:
        cloud.close()


def test_rapid_confirmed_saves_keep_each_generation_in_order(tmp_path, monkeypatch):
    controller = prepared(tmp_path)
    ctx = controller.save_context()
    controller.running_save_context = ctx
    source = tmp_path / "Original.state"
    entered, release = threading.Event(), threading.Event()
    record = controller.save_manager.record_state

    def delayed(*args, **kwargs):
        entered.set()
        assert release.wait(4)
        return record(*args, **kwargs)

    monkeypatch.setattr(controller.save_manager, "record_state", delayed)
    try:
        for data in (b"first confirmed save", b"second confirmed save"):
            source.write_bytes(data)
            controller.save_manager.store(ctx).publish("1", source, {"contentHash": "b" * 64, "coreHash": "a" * 64})
            controller.record_running_save("1")
            wait_for(entered.is_set)
        release.set()
        wait_for(lambda: not controller.save_jobs)
        entries = controller.save_manager.history.entries(ctx)
        assert len(entries) == 2
        assert entries[0]["parents"] == [entries[1]["id"]]
        assert { (controller.save_manager.history.directory(e["id"]) / "Original.state1").read_bytes()
                 for e in entries } == {b"first confirmed save", b"second confirmed save"}
    finally:
        release.set()
        wait_for(lambda: not controller.save_jobs)
        controller.close()


def test_failed_frontend_start_releases_game_save_ownership(tmp_path):
    from PySide6.QtCore import QProcess

    controller = prepared(tmp_path)
    context = controller.save_context()
    session = controller.save_manager.session(context)
    session.__enter__()
    controller.running_save_context, controller.running_save_session = context, session
    try:
        checks = {**controller.checks, "firmware": str(tmp_path), "executable": str(tmp_path / "missing-retroarch")}
        controller.engine.start(controller.current, checks, controller.save_manager.store(context))
        wait_for(lambda: controller.engine.process.error() == QProcess.ProcessError.FailedToStart)
        assert controller.running_save_session is None
        assert controller.engine.status == "idle"
        assert controller.save_manager.backup(context) == []
    finally:
        controller.close()


@pytest.mark.parametrize("kind", ["state", "sram"])
def test_enabling_cloud_backs_up_existing_library_saves_before_configuring(tmp_path, monkeypatch, kind):
    from test_games_catalog import installed

    from udeck.apps.emulator.controller import content_hash

    controller = prepared(tmp_path)
    controller.catalog = controller.library.catalog = installed(tmp_path, {"gambatte": {"supported_extensions": "gb"}})
    controller.library.items = [controller.current]
    controller.checks["contentHash"] = content_hash(controller.current)
    ctx = controller.save_context()
    source = tmp_path / "Original.state"
    source.write_bytes(b"progress saved before installing this feature")
    store = controller.save_manager.store(ctx)
    if kind == "state":
        store.publish("1", source, {"contentHash": ctx["contentHash"], "coreHash": ctx["coreHash"]})
    else:
        store.prepare_sram()
        (store.sram_root / "Original.srm").write_bytes(source.read_bytes())
    configured = []

    def request(member, payload=None, callback=None):
        if member == "Configure":
            configured.append((payload, controller.save_manager.history.entries(ctx)))

    monkeypatch.setattr(controller.save_cloud, "request", request)
    controller.save_cloud.state["remote"] = "existing"
    try:
        controller.save_configure({"enabled": True})
        wait_for(lambda: not controller.save_jobs)
        assert configured and configured[0][0]["enabled"]
        assert len(configured[0][1]) == 1
        entry = configured[0][1][0]
        assert entry["kind"] == kind
        name = "Original.state1" if kind == "state" else "Original.srm"
        assert (controller.save_manager.history.directory(entry["id"]) / name).read_bytes() == source.read_bytes()
    finally:
        controller.close()


def test_new_cloud_settings_supersede_enable_waiting_for_local_backup(tmp_path, monkeypatch):
    controller = prepared(tmp_path)
    backups, requests = [], []
    monkeypatch.setattr(controller, "save_backup_all", lambda on_complete=None: backups.append(on_complete))
    monkeypatch.setattr(controller.save_cloud, "request", lambda member, payload: requests.append((member, payload)))
    try:
        controller.save_configure({"enabled": True, "remote": "first", "directory": "old"})
        controller.save_configure({"enabled": False, "remote": "second", "directory": "new"})
        backups[0]()
        assert len(requests) == 1
        assert requests[0][1] == {"enabled": False, "remote": "second", "directory": "new"}
    finally:
        controller.close()
