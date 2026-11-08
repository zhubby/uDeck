"""Full QML application lifecycle against real, independent PTYs."""

import os
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

from PySide6.QtCore import Q_RETURN_ARG, QMetaObject
from PySide6.QtGui import QRawFont
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from udeck.core import ConfigStore
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
    child.write_text("import time\nfrom pathlib import Path\nprint('\\n'.join(f'persistent-scrollback-{index}' for index in range(80)), flush=True)\ncounter=Path('counter')\nwhile True:\n counter.write_text(str(time.monotonic()))\n time.sleep(0.1)\n")
    request = LaunchRequest(str(directory), ["/usr/bin/python3", str(child)], "中文 任务", dict(os.environ), True)
    try:
        coordinator.open(request)
        entry = coordinator.recent
        window, controller = entry["window"], entry["controller"]
        wait(lambda: (directory / "counter").is_file())
        assert window.title() == "中文 任务"
        def terminal_families(target=window):
            pending = [target.contentItem()]
            families = []
            while pending:
                item = pending.pop()
                if item.objectName() == "nativeTerminal":
                    families.append(QRawFont.fromFont(item.property("font")).familyName())
                pending.extend(item.childItems())
            return families

        assert terminal_families() == ["JetBrains Mono"]
        sessions = list(controller.native_sessions.values())
        assert len(sessions) == 1
        first_pid = QMetaObject.invokeMethod(sessions[0], "getShellPID", Q_RETURN_ARG(int))
        wait(lambda: "persistent-scrollback-40" in sessions[0].property("history"))
        first_id = controller.current
        controller.newTab()
        wait(lambda: len(controller.native_sessions) == 2)
        assert QMetaObject.invokeMethod(sessions[0], "getShellPID", Q_RETURN_ARG(int)) == first_pid
        session_objects = dict(controller.native_sessions)
        controller.selectTab(first_id)
        controller.command("menu")
        configuration = ConfigStore(directory / "settings.json")
        configuration.data["preferences"]["language"] = "zh_CN"
        configuration.save()
        wait(lambda: controller.language == "zh_CN")
        wait(lambda: terminal_families() == ["LXGW WenKai Mono"] * len(controller.requests))
        assert controller.native_sessions == session_objects
        assert QMetaObject.invokeMethod(sessions[0], "getShellPID", Q_RETURN_ARG(int)) == first_pid
        assert window.title() == "中文 任务"
        coordinator.open(LaunchRequest(str(directory), ["/bin/sh", "-c", "printf second-window; exec sleep 600"],
                                       "第二窗口", dict(os.environ), True))
        second = coordinator.recent
        wait(lambda: bool(second["controller"].native_sessions))
        second_sessions = dict(second["controller"].native_sessions)
        wait(lambda: any("second-window" in session.property("history") for session in second_sessions.values()))
        coordinator.activate(window)
        QTest.qWait(100)
        focus = [(current["window"], current["window"].activeFocusItem()) for current in coordinator.windows]
        process_ids = [(session, QMetaObject.invokeMethod(session, "getShellPID", Q_RETURN_ARG(int)))
                       for current in coordinator.windows for session in current["controller"].native_sessions.values()]
        histories = [(session, session.property("history")) for session, process_id in process_ids]
        for theme in ("dark", "classic"):
            configuration.data["preferences"]["theme"] = theme
            configuration.save()
            wait(lambda theme=theme: controller.theme == theme)
            assert controller.native_sessions == session_objects
            assert QMetaObject.invokeMethod(sessions[0], "getShellPID", Q_RETURN_ARG(int)) == first_pid
            assert second["controller"].theme == theme
            assert second["controller"].native_sessions == second_sessions
            for current in coordinator.windows:
                pending = [current["window"].contentItem()]
                while pending:
                    item = pending.pop()
                    if item.objectName() == "nativeTerminal":
                        assert item.property("colorScheme") == ("udeck-dark" if theme == "dark" else "udeck")
                    pending.extend(item.childItems())
            assert all(target.activeFocusItem() is item for target, item in focus)
            assert all(QMetaObject.invokeMethod(session, "getShellPID", Q_RETURN_ARG(int)) == process_id
                       for session, process_id in process_ids)
            assert all(session.property("history") == history for session, history in histories)
            assert controller.current == first_id and controller.mode == "menu"
        second["controller"].requestCloseWindow()
        second["controller"].dispatch("down")
        second["controller"].dispatch("accept")
        wait(lambda: len(coordinator.windows) == 1)
        coordinator.activate(window)
        configuration.data["preferences"]["language"] = "en"
        configuration.save()
        wait(lambda: controller.language == "en")
        wait(lambda: terminal_families() == ["JetBrains Mono"] * len(controller.requests))
        assert controller.native_sessions == session_objects
        controller.dispatch("back")
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
