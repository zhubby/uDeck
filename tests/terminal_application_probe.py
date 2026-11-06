"""Full QML application lifecycle against real, independent PTYs."""

import os
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

from PySide6.QtCore import Q_RETURN_ARG, QMetaObject
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from udeck.terminal.core import LaunchRequest, TerminalPreferences
from udeck.terminal.main import Coordinator

app = QApplication([])
app.setQuitOnLastWindowClosed(False)
with tempfile.TemporaryDirectory(prefix="udeck-application-test-") as folder:
    directory = Path(folder)
    options = SimpleNamespace(mock=False, no_input=True, windowed=True)
    coordinator = Coordinator(app, options, TerminalPreferences(directory / "prefs"), time.monotonic())
    assert coordinator.diagnostics()["installedBuildId"] is None, "Source execution must not attest to an installed build"

    def wait(condition, timeout=5):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            app.processEvents()
            if condition():
                return
            QTest.qWait(20)
        raise AssertionError(f"Application probe timed out: {coordinator.diagnostics()}")

    child = directory / "ticker.py"
    child.write_text("import time\nfrom pathlib import Path\np=Path('counter')\nwhile True:\n p.write_text(str(time.monotonic()))\n time.sleep(0.1)\n")
    request = LaunchRequest(str(directory), ["/usr/bin/python3", str(child)], "中文 任务", dict(os.environ), True)
    try:
        coordinator.open(request)
        entry = coordinator.recent
        window, controller = entry["window"], entry["controller"]
        wait(lambda: (directory / "counter").is_file())
        assert window.title() == "中文 任务"
        sessions = list(controller.native_sessions.values())
        assert len(sessions) == 1
        first_pid = QMetaObject.invokeMethod(sessions[0], "getShellPID", Q_RETURN_ARG(int))
        first_id = controller.current
        controller.newTab()
        wait(lambda: len(controller.native_sessions) == 2)
        assert QMetaObject.invokeMethod(sessions[0], "getShellPID", Q_RETURN_ARG(int)) == first_pid
        controller.selectTab(first_id)
        previous = (directory / "counter").read_text()
        window.showMinimized()
        wait(lambda: (directory / "counter").read_text() != previous)
        coordinator.activate(window)
        controller.requestCloseWindow()
        controller.dispatch("accept")
        assert len(controller.requests) == 2
        os.kill(first_pid, 0)
        controller.command("close-tab")
        controller.dispatch("down")
        controller.dispatch("accept")
        wait(lambda: len(controller.requests) == 1)
        assert first_id not in controller.requests
        # A naturally exiting command closes only its own window.
        coordinator.open(LaunchRequest(str(directory), ["/bin/sh", "-c", "exit 0"], "自然退出", dict(os.environ), True))
        wait(lambda: len(coordinator.windows) == 1)
        window.close()
        assert controller.mode == "close"
        controller.dispatch("back")
        assert window.isVisible()
        controller.requestCloseWindow()
        controller.dispatch("down")
        controller.dispatch("accept")
        wait(lambda: not coordinator.windows)
        assert not coordinator.errors, coordinator.errors
        print('{"application":"passed","stablePtys":true,"background":true,"closeConfirmation":true,"naturalExit":true}')
    finally:
        coordinator.close()
