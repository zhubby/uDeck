"""Independent uDeck Terminal process.

SPDX-License-Identifier: GPL-2.0-or-later
"""

import json
import os
import sys
import tempfile
import time
from pathlib import Path

from PySide6.QtCore import QEvent, QObject, QTimer, QUrl
from PySide6.QtDBus import QDBusConnection, QDBusMessage
from PySide6.QtQml import QQmlComponent, QQmlContext, QQmlEngine
from PySide6.QtQuick import QQuickWindow  # noqa: F401 - register the native QML window wrapper
from PySide6.QtWidgets import QApplication, QMessageBox

from ..core import ConfigStore
from ..i18n import render, tr
from ..performance import StartupTrace
from ..sounds import InterfaceSounds
from . import APP_ID, INTERFACE, OBJECT_PATH, __version__
from .controller import TerminalController
from .core import TerminalPreferences, parse_launch, plugin_paths
from .ipc import TerminalControl, forward, interface, service_name


class Coordinator(QObject):
    def __init__(self, application, options, preferences, started, trace=None):
        super().__init__()
        self.application, self.options = application, options
        self.preferences, self.started = preferences, started
        self.trace = trace or StartupTrace(started=started)
        self.language_path = preferences.path.with_name("settings.json")
        interface = ConfigStore(self.language_path).data["preferences"]
        self.language, self.theme = interface["language"], interface["theme"]
        self.language_timer = QTimer(self)
        self.language_timer.setInterval(1000)
        self.language_timer.timeout.connect(self.refresh_language)
        self.language_timer.start()
        self.installed_build_id = None
        if Path(__file__).resolve() == Path("/usr/lib/python3/dist-packages/udeck/terminal/runtime.py"):
            try:
                self.installed_build_id = json.loads(Path("/usr/share/udeck-terminal/build-info.json").read_text())["buildId"]
            except (OSError, ValueError, KeyError):
                pass
        self.engine = QQmlEngine()
        for path in plugin_paths():
            self.engine.addImportPath(str(path))
        self.errors = []
        self.engine.warnings.connect(lambda warnings: self.errors.extend(w.toString() for w in warnings))
        self.component = QQmlComponent(self.engine, QUrl.fromLocalFile(str(Path(__file__).parent / "qml/Main.qml")))
        self.trace.mark('qmlReady')
        if self.component.isError():
            raise RuntimeError("\n".join(error.toString() for error in self.component.errors()))
        self.windows = []
        self.recent = None
        self.first_frame = None
        self.inputs = None
        if not options.mock and not options.no_input and sys.platform == "linux":
            from .input import TerminalInput

            self.inputs = TerminalInput(self, ConfigStore().data["input"])
        application.installEventFilter(self)

    def open(self, request):
        self.trace.request_activation()
        if not request.new_window and self.recent:
            self.activate(self.recent["window"])
            return
        controller = TerminalController(request, self.preferences, mock=self.options.mock, language=self.language, theme=self.theme)
        self.trace.mark('controllerReady')
        context = QQmlContext(self.engine.rootContext())
        context.setContextProperty("controller", controller)
        context.setContextProperty("windowed", self.options.windowed or self.options.mock)
        context.setContextProperty("useMock", self.options.mock)
        window = self.component.create(context)
        if window is None:
            raise RuntimeError("\n".join(error.toString() for error in self.component.errors()))
        sounds = InterfaceSounds(self.language_path, window, silent=os.environ.get("QT_QPA_PLATFORM") == "offscreen")
        controller.soundRequested.connect(sounds.request)
        entry = {"window": window, "controller": controller, "context": context, "sounds": sounds}
        self.windows.append(entry)
        self.recent = entry
        controller.closed.connect(lambda: QTimer.singleShot(0, lambda: self.retire(entry)))
        controller.home.connect(lambda: self.desktop_action("Home", window))
        controller.quickSettings.connect(lambda: self.quick_settings(entry))
        controller.clipboardRequested.connect(lambda: controller.preparePaste(self.application.clipboard().text()))
        window.activeChanged.connect(self.focus_changed)
        window.frameSwapped.connect(self.record_frame)
        try:
            self.trace.graphics_api = window.rendererInterface().graphicsApi().name
        except (AttributeError, RuntimeError):
            pass
        self.activate(window)

    def refresh_language(self):
        preferences = ConfigStore(self.language_path).data["preferences"]
        language, theme = preferences["language"], preferences["theme"]
        if language != self.language:
            self.language = language
            for entry in self.windows:
                entry["controller"].setLanguage(language)
        if theme != self.theme:
            self.theme = theme
            for entry in self.windows:
                entry["controller"].setTheme(theme)

    def activate(self, window):
        window.showNormal() if self.options.windowed or self.options.mock else window.showFullScreen()
        window.raise_()
        window.requestActivate()
        window.requestUpdate()
        self.trace.active_changed(window.isActive())

    def record_frame(self):
        self.trace.frame_swapped()
        if self.first_frame is None:
            self.first_frame = round(time.monotonic() - self.started, 3)

    def focus_changed(self):
        active = next((entry for entry in self.windows if entry["window"].isActive()), None)
        if active:
            self.recent = active
            self.trace.active_changed(True)
        if self.inputs:
            self.inputs.set_foreground(bool(active))

    def eventFilter(self, watched, event):
        # Consume pointer input inside all windows, including transient UI. The
        # built-in L/R mouse interface is separately owned by TerminalInput.
        if event.type() in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease,
                            QEvent.Type.MouseButtonDblClick, QEvent.Type.Wheel):
            return True
        return False

    def desktop_action(self, action, window):
        bus = QDBusConnection.sessionBus()
        if bus.isConnected() and bus.interface().isServiceRegistered("io.github.zhubby.uDeck").value():
            request = QDBusMessage.createMethodCall("io.github.zhubby.uDeck", "/io/github/zhubby/uDeck", "io.github.zhubby.uDeck.Control", action)
            bus.asyncCall(request)
            return True
        if action == "Home":
            window.showMinimized()
        return False

    def quick_settings(self, entry):
        if not self.desktop_action("QuickSettings", entry["window"]):
            entry["controller"].command("settings")

    def retire(self, entry):
        if entry not in self.windows:
            return
        self.windows.remove(entry)
        entry["sounds"].close()
        entry["window"].deleteLater()
        entry["context"].deleteLater()
        entry["controller"].deleteLater()
        self.recent = self.windows[-1] if self.windows else None
        self.focus_changed()
        if not self.windows:
            self.application.quit()

    def shoulder(self, generation, action):
        if self.inputs:
            self.inputs.shoulder(generation, action)

    def route(self, generation, enabled):
        if self.inputs:
            self.inputs.route(generation, enabled)

    def diagnostics(self):
        return {"version": __version__, "mock": self.options.mock,
                "installedBuildId": self.installed_build_id,
                "windows": len(self.windows), "sessions": sum(len(e["controller"].requests) for e in self.windows),
                "localShells": sum(not request.argv for entry in self.windows for request in entry["controller"].requests.values()),
                "firstFrameSeconds": self.first_frame,
                "performance": self.trace.snapshot(),
                "uptimeSeconds": round(time.monotonic() - self.started, 3),
                "input": self.inputs.diagnostics() if self.inputs else {"enabled": False},
                "qmlErrors": self.errors}

    def close(self):
        self.language_timer.stop()
        if self.inputs:
            self.inputs.close()
        # Destroy native delegates before their controllers/context disappear.
        for entry in list(self.windows):
            entry["sounds"].close()
            entry["window"].setProperty("allowClose", True)
            entry["window"].close()
            entry["window"].deleteLater()
        self.application.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.windows.clear()


def main(argv=None, *, request=None, options=None, trace=None):
    started = time.monotonic()
    trace = trace or StartupTrace()
    trace.mark('runtimeImported')
    os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")
    if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
        os.environ.setdefault("QT_QUICK_BACKEND", "software")
    application = QApplication(["udeck-terminal"])
    trace.mark('qtReady')
    application.setQuitOnLastWindowClosed(False)
    application.setApplicationName(APP_ID)
    application.setDesktopFileName(APP_ID)
    application.setOrganizationName("uDeck")
    temporary = None
    coordinator = None
    registered = False
    bus = QDBusConnection.sessionBus()
    try:
        if request is None or options is None:
            request, options = parse_launch(argv)
        if options.doctor:
            remote = interface()
            if remote.isValid():
                reply = remote.call("Diagnose")
                if reply.type() == QDBusMessage.MessageType.ErrorMessage:
                    raise RuntimeError(reply.errorMessage())
                print(reply.arguments()[0])
            else:
                print(json.dumps({"running": False, "plugins": [str(p) for p in plugin_paths()]}, ensure_ascii=False))
            return 0
        request.executable()
        if not options.mock:
            if not bus.isConnected():
                raise RuntimeError(tr('无法连接图形会话 D-Bus；请从已登录的桌面启动终端。'))
            if forward(request):
                return 0
            registered = bus.registerService(service_name())
            if not registered:
                if forward(request):
                    return 0
                raise RuntimeError(tr('终端进程启动冲突，请重试'))
            if not plugin_paths():
                raise RuntimeError(tr('缺少 QMLTermWidget 原生插件。请安装完整的 udeck-terminal 软件包，或运行 tools/build-terminal-plugin。'))
        if options.mock:
            temporary = tempfile.TemporaryDirectory(prefix="udeck-terminal-preview-")
        preferences = TerminalPreferences(Path(temporary.name) / "preferences.json" if temporary else None)
        coordinator = Coordinator(application, options, preferences, started, trace)
        control = TerminalControl(coordinator)
        if registered and not bus.registerObject(OBJECT_PATH, INTERFACE, control, QDBusConnection.RegisterOption.ExportAllSlots):
            raise RuntimeError(tr('无法注册终端 D-Bus 接口'))
        coordinator.open(request)
        def capture():
            if options.screenshot and coordinator.recent:
                options.screenshot.parent.mkdir(parents=True, exist_ok=True)
                if not coordinator.recent["window"].grabWindow().save(str(options.screenshot)):
                    coordinator.errors.append(tr('截图保存失败'))

        def smoke():
            controller = coordinator.recent["controller"]
            for action in ("new-tab", "menu"):
                controller.command(action)
            controller.dispatch("back")
            controller.command("history")
            for action in ("up", "accept", "right", "accept"):
                controller.dispatch(action)
            print(json.dumps({"smoke": "failed" if coordinator.errors else "passed", **coordinator.diagnostics()}, ensure_ascii=False), flush=True)

        if options.smoke_test:
            QTimer.singleShot(800, smoke)
        if options.screenshot:
            QTimer.singleShot(1500, capture)
        if options.quit_after or options.smoke_test:
            QTimer.singleShot(int(1000 * (options.quit_after or 2)), application.quit)
        result = application.exec()
        return 2 if coordinator.errors else result
    except (OSError, ValueError, RuntimeError) as error:
        language = coordinator.language if coordinator else ConfigStore().data["preferences"]["language"]
        message = render(error, language)
        print(f"uDeck Terminal: {message}", file=sys.stderr)
        if os.environ.get("QT_QPA_PLATFORM") != "offscreen":
            QMessageBox.critical(None, "uDeck Terminal", message)
        return 2
    finally:
        if coordinator:
            coordinator.close()
        if registered:
            bus.unregisterObject(OBJECT_PATH)
            bus.unregisterService(service_name())
        if temporary:
            temporary.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
