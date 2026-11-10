import json
import threading
import time
from concurrent.futures import Future
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QCoreApplication

from udeck.controller import ShellController
from udeck.core import ConfigStore
from udeck.desktop import DesktopCatalog
from udeck.i18n import render
from udeck.mock import MockBackend

APP = {"id": "org.example.Reader.desktop", "name": "Reader", "icon": "book", "category": "Office"}


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
def controller(tmp_path):
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
    controller._windows_changed([{"id": "1", "appId": "org.example.Reader", "active": True}])
    assert not json.loads(controller.viewSnapshotJson)["appLaunch"]["pending"]
    assert not presented


def test_mock_launch_never_executes_desktop_command(controller):
    controller.mock = True
    controller.catalog.launch = lambda *_arguments: pytest.fail("Mock launched a real application")
    controller._launch(APP)
    assert json.loads(controller.viewSnapshotJson)["appLaunch"]["pending"]


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
        entries = [{**APP, "id": f"example-{index}.desktop"} for index in range(4)]
        shell._complete_startup((entries, None))
        shell.startupFrameSwapped()
        assert shell.navigation.index == 2
    finally:
        shell.close()
