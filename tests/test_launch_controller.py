"""
[INPUT]: 依赖桌面控制器、可控执行器与隔离的会话调用边界。
[OUTPUT]: 验证启动反馈、异步文件参数和单实例转发回退。
[POS]: 桌面启动编排回归；真实进程由外部边界替身隔离。
[PROTOCOL]: Update this header on change, then check AGENTS.md
"""

import json
import threading
import time
from concurrent.futures import Future
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QCoreApplication
from PySide6.QtDBus import QDBusMessage

from udeck.controller import ShellController
from udeck.core import ConfigStore
from udeck.desktop import DesktopCatalog
from udeck.i18n import render
from udeck.mock import MockBackend

APP = {"id": "io.github.zhubby.uDeck.Reader.desktop", "name": "Reader", "icon": "book", "category": "Office"}


class ManualExecutor:
    def __init__(self):
        self.jobs = []

    def submit(self, work):
        future = Future()
        self.jobs.append((work, future))
        return future

    def finish(self, error=None):
        _work, future = self.jobs[-1]
        if error is None:
            future.set_result(None)
        else:
            future.set_exception(error)

    def shutdown(self, **_options):
        pass


@pytest.fixture
def controller(tmp_path, monkeypatch):
    # 冷启动测试不连接主机中运行的应用；转发测试自行提供总线。
    monkeypatch.setattr("udeck.launch_controller.QDBusConnection", SimpleNamespace(
        sessionBus=lambda: SimpleNamespace(isConnected=lambda: False)))
    application = QCoreApplication.instance() or QCoreApplication([])
    shell = ShellController(MockBackend(), config=ConfigStore(tmp_path / "config.json"), mock=True)
    shell._test_application = application
    shell.mock = False
    shell.window_service = SimpleNamespace(available=True)
    yield shell
    shell.close()


def test_desktop_catalog_preserves_window_matching_metadata(tmp_path):
    (tmp_path / "example.desktop").write_text(
        "[Desktop Entry]\nType=Application\nName=Example\nExec=example\nStartupWMClass=ExampleWindow\n"
    )
    assert DesktopCatalog([tmp_path]).entries()[0]["startupWMClass"] == "ExampleWindow"


def test_application_launch_is_independent_of_file_busy_state(controller):
    executor = ManualExecutor()
    controller.launch_executor.shutdown(wait=True)
    controller.launch_executor = executor
    controller.busy = True
    controller._launch(APP)
    assert len(executor.jobs) == 1
    assert controller.busy
    assert json.loads(controller.viewSnapshotJson)["appLaunch"]["pending"]
    executor.finish()
    assert controller.busy
    assert json.loads(controller.viewSnapshotJson)["appLaunch"]["pending"]
    assert APP["id"] in controller.config.data["recent"]


def test_back_restores_original_selection_and_deduplicates_request(controller):
    executor = ManualExecutor()
    controller.launch_executor.shutdown(wait=True)
    controller.launch_executor = executor
    controller.setPage("apps")
    controller.select(2)
    controller._launch(APP)
    controller.dispatch("right")
    assert controller.navigation.index == 2
    controller.dispatch("back")
    assert controller.navigation.index == 2
    assert controller.navigation.page == "apps"
    assert not json.loads(controller.viewSnapshotJson)["appLaunch"]["pending"]
    controller._launch(APP)
    assert len(executor.jobs) == 1
    assert json.loads(controller.viewSnapshotJson)["appLaunch"]["pending"]


def test_launch_failure_clears_wait_and_names_the_application(controller):
    executor = ManualExecutor()
    controller.launch_executor.shutdown(wait=True)
    controller.launch_executor = executor
    controller._launch(APP)
    executor.finish(RuntimeError("permission denied"))
    assert not json.loads(controller.viewSnapshotJson)["appLaunch"]["pending"]
    assert "Reader" in render(controller.toast, "en")
    assert "permission denied" in render(controller.toast, "en")


def test_active_window_ends_wait_without_presenting_shell(controller):
    executor = ManualExecutor()
    controller.launch_executor.shutdown(wait=True)
    controller.launch_executor = executor
    presented = []
    controller.present.connect(lambda: presented.append(True))
    controller._launch(APP)
    controller._windows_changed([{"id": "1", "appId": "io.github.zhubby.uDeck.Reader", "active": True}])
    assert not json.loads(controller.viewSnapshotJson)["appLaunch"]["pending"]
    assert not presented


def test_mock_launch_never_executes_desktop_command(controller):
    controller.mock = True
    controller.catalog.launch = lambda *_arguments: pytest.fail("Mock launched a real application")
    controller._launch(APP)
    assert json.loads(controller.viewSnapshotJson)["appLaunch"]["pending"]


@pytest.mark.parametrize("paths", [(), ("中文 file %.mp4",)])
def test_cold_launch_freezes_absolute_file_paths_before_async_submission(controller, tmp_path, monkeypatch, paths):
    executor = ManualExecutor()
    controller.launch_executor.shutdown(wait=True)
    controller.launch_executor = executor
    monkeypatch.chdir(tmp_path)
    launched = []
    controller.catalog.launch = lambda identifier, paths=(): launched.append((identifier, paths))
    files = list(paths)
    expected = (str(tmp_path / "中文 file %.mp4"),) if paths else ()
    controller._start_application(APP, files=files)
    files[:] = ["replaced.mp4"]
    monkeypatch.chdir(tmp_path.parent)
    executor.jobs[0][0]()
    assert launched == [(APP["id"], expected)]


@pytest.mark.parametrize("error_name", ["", "org.freedesktop.DBus.Error.ServiceUnknown",
                                      "org.freedesktop.DBus.Error.NameHasNoOwner",
                                      "org.freedesktop.DBus.Error.NoReply"])
def test_native_forwarding_preserves_files_and_only_absent_service_spawns(controller, tmp_path, monkeypatch, error_name):
    executor = ManualExecutor()
    controller.launch_executor.shutdown(wait=True)
    controller.launch_executor = executor
    messages = []
    callbacks = []
    reply = SimpleNamespace(
        type=lambda: QDBusMessage.MessageType.ErrorMessage if error_name else QDBusMessage.MessageType.ReplyMessage,
        errorName=lambda: error_name, errorMessage=lambda: "request timed out", arguments=lambda: [""])

    class Watcher:
        finished = SimpleNamespace(connect=callbacks.append)

        def reply(self):
            return reply

        def deleteLater(self):
            pass

        def isFinished(self):
            return False

    watcher = Watcher()

    class Bus:
        def isConnected(self):
            return True

        def asyncCall(self, message, timeout):
            messages.append(message)
            assert timeout == 2000
            return None

    monkeypatch.setattr("udeck.launch_controller.QDBusConnection", SimpleNamespace(sessionBus=Bus))
    monkeypatch.setattr("udeck.launch_controller.QDBusPendingCallWatcher", lambda *_arguments: watcher)
    native = {**APP, "id": "io.github.zhubby.uDeck.Video.desktop"}
    files = [str(tmp_path / "中文 file %.mp4")]
    controller._start_application(native, files=files)
    assert json.loads(messages[0].arguments()[0]) == {"files": files, "command": ""}
    files[:] = ["replaced.mp4"]
    launched = []
    controller.catalog.launch = lambda identifier, paths=(): launched.append((identifier, paths))
    callbacks[0]()
    if error_name in ("org.freedesktop.DBus.Error.ServiceUnknown", "org.freedesktop.DBus.Error.NameHasNoOwner"):
        assert len(executor.jobs) == 1
        executor.jobs[0][0]()
        assert launched == [(native["id"], (str(tmp_path / "中文 file %.mp4"),))]
    else:
        assert not executor.jobs
        if error_name:
            assert "timed out" in render(controller.toast, "en")


def test_startup_scans_off_main_thread_and_waits_for_desktop_frame(tmp_path):
    application = QCoreApplication.instance() or QCoreApplication([])
    main_thread = threading.get_ident()
    threads = []

    class Catalog:
        def entries(self):
            threads.append(threading.get_ident())
            return [APP]

    shell = ShellController(MockBackend(), config=ConfigStore(tmp_path / "settings.json"),
                            catalog=Catalog(), defer_startup=True)
    try:
        assert not threads
        assert json.loads(shell.viewSnapshotJson)["startup"]["active"]
        shell.startupFrameSwapped()
        deadline = time.monotonic() + 3
        while shell.startup["phase"] != "ready" and time.monotonic() < deadline:
            application.processEvents()
            time.sleep(0.001)
        assert shell.startup["phase"] == "ready"
        assert threads and threads[0] != main_thread
        assert shell.startup["active"]
        shell.startupFrameSwapped()
        assert not shell.startup["active"]
        assert shell.applications == [APP]
    finally:
        shell.close()


def test_startup_catalog_error_still_allows_settings_navigation(tmp_path):
    application = QCoreApplication.instance() or QCoreApplication([])

    class Catalog:
        def entries(self):
            raise OSError("catalog unavailable")

    shell = ShellController(MockBackend(), config=ConfigStore(tmp_path / "settings.json"),
                            catalog=Catalog(), defer_startup=True)
    try:
        shell.startupFrameSwapped()
        deadline = time.monotonic() + 3
        while shell.startup["phase"] != "ready" and time.monotonic() < deadline:
            application.processEvents()
            time.sleep(0.001)
        assert shell.startup["phase"] == "ready"
        shell.startupFrameSwapped()
        shell.dispatch("quick-settings")
        assert shell.modal
        assert "catalog unavailable" in render(shell.toast, "en")
    finally:
        shell.close()


def test_deferred_startup_preserves_saved_application_selection(tmp_path):
    application = QCoreApplication.instance() or QCoreApplication([])
    config = ConfigStore(tmp_path / "settings.json")
    config.data["focus"] = {"apps": 2}
    shell = ShellController(MockBackend(), config=config, mock=True, defer_startup=True)
    shell._test_application = application
    try:
        shell.setPage("apps")
        assert shell.navigation.index == 2
        entries = [{**APP, "id": f"io.github.zhubby.uDeck.{name}.desktop"} for name in ("Reader", "Music", "Video", "Browser")]
        shell._complete_startup((entries, None))
        shell.startupFrameSwapped()
        assert shell.navigation.index == 2
    finally:
        shell.close()


@pytest.mark.parametrize("mock", [False, True])
def test_external_launch_is_rejected_before_tracking_or_forwarding(controller, monkeypatch, mock):
    controller.mock = mock
    monkeypatch.setattr(controller, "_forward_application", lambda *_args: pytest.fail("External app forwarded"))
    monkeypatch.setattr(controller, "_submit_application", lambda *_args: pytest.fail("External app submitted"))
    controller._start_application({**APP, "id": "xarchiver.desktop"})
    assert not controller.launches.requests
    assert not controller.config.data["recent"]
    assert controller.toast


def test_application_views_and_startup_filter_external_entries(controller):
    external = {**APP, "id": "xarchiver.desktop", "category": "Graphics"}
    controller._complete_startup(([external, APP], None))
    assert controller.applications == [APP]
    controller.applications.append(external)
    controller.setPage("apps")
    assert [item["id"] for item in controller._items()] == [APP["id"]]
    controller._execute_option({"action": "categories"})
    assert "Graphics" not in [option["id"] for option in controller.modal["options"]]


@pytest.mark.parametrize("deferred", [False, True])
def test_external_only_saved_category_falls_back_to_native_apps(tmp_path, deferred):
    application = QCoreApplication.instance() or QCoreApplication([])
    config = ConfigStore(tmp_path / "settings.json")
    config.data["preferences"]["category"] = "Graphics"
    shell = ShellController(MockBackend(), config=config, mock=True, defer_startup=deferred)
    try:
        if deferred:
            shell._complete_startup(([APP], None))
            shell.startupFrameSwapped()
        shell.setPage("apps")
        assert shell.category == "All"
        assert shell._items()
        application.processEvents()
    finally:
        shell.close()
