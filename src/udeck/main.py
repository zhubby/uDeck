import argparse
import json
import os
import sys
import tempfile
import time
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QTimer, QUrl, Slot
from PySide6.QtDBus import QDBusConnection
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtQml import QQmlApplicationEngine

from . import __version__
from .console import ConsolePanel
from .controller import ShellController
from .core import ConfigStore
from .cursor import PointerCursor
from .i18n import render, tr
from .icons import IconProvider
from .input import Gamepad
from .mock import MockBackend
from .pointer import PointerGuard
from .sounds import InterfaceSounds
from .windows import APP_ID, WindowService

CONTROL_PATH = "/io/github/zhubby/uDeck"
CONTROL_INTERFACE = "io.github.zhubby.uDeck.Control"


class Control(QObject):
    def __init__(self, controller, windows):
        super().__init__()
        self.controller = controller
        self.windows = windows
        self.started = time.monotonic()
        self.first_frame = None
        self.startup_frame = None
        self.terminal_broker = None
        self.application_router = None
        self.isolation = None
        self.console_panel = None
        self.shortcut_session = None

    @Slot()
    def Console(self):
        if self.console_panel:
            self.console_panel.open()

    @Slot()
    def Home(self):
        if self.application_router:
            self.application_router.leave_menu()
        self.controller.dispatch("home")

    @Slot()
    def Switcher(self):
        if self.application_router:
            self.application_router.leave_menu()
        self.controller.dispatch("switcher")

    @Slot()
    def AppMenu(self):
        if self.application_router:
            self.application_router.open_menu()
        else:
            self.controller.notify(tr('完整应用兼容模式需要独立 uDeck 会话'))
            self.controller.present.emit()

    @Slot(str, result=bool)
    def InputMode(self, mode):
        return bool(self.application_router and self.application_router.set_mode(mode))

    @Slot(str, result=bool)
    def InputConfigApplied(self, token):
        if self.shortcut_session:
            return self.shortcut_session.acknowledge(token)
        return bool(self.isolation and self.isolation.acknowledge(token))

    @Slot(str, result=bool)
    def GlobalAction(self, action):
        if action in ('apps', 'files', 'settings') and self.application_router:
            self.application_router.leave_menu()
        return self.controller.globalAction(action)

    @Slot(result=str)
    def ReloadShortcuts(self):
        if self.shortcut_session:
            state = self.controller.data.get('sessionInput', {})
            if state.get('available') and state.get('active') and not state.get('locked'):
                self.shortcut_session.start(retry=True)
        return json.dumps(self.controller._shortcut_state(), ensure_ascii=False)

    @Slot()
    def Lock(self):
        self.controller.activateSetting('lock')

    @Slot()
    def QuickSettings(self):
        if self.application_router and not self.application_router.shell:
            self.application_router.open_menu()
            self.application_router.menu_action('quick-settings')
            return
        self.controller.dispatch("quick-settings")

    @Slot(result=str)
    def TerminalInputState(self):
        return json.dumps(self.terminal_broker.state() if self.terminal_broker else {"available": False})

    @Slot(str, result=str)
    def NativeInputState(self, app_id):
        return json.dumps(self.suite_broker.state(app_id))

    @Slot(str)
    def ActivateNativeApp(self, app_id):
        from .app_routing import NATIVE_APPS

        if self.windows and app_id in NATIVE_APPS:
            for entry in self.windows.entries():
                if entry.get("appId") == app_id:
                    self.windows.request(entry["id"], "activate")
                    break

    @Slot(result=str)
    def Diagnose(self):
        return json.dumps({
            "version": __version__, "mock": self.controller.mock,
            "uptimeSeconds": round(time.monotonic() - self.started, 3),
            "firstFrameSeconds": self.first_frame,
            "startupFrameSeconds": self.startup_frame,
            "page": self.controller.navigation.page,
            "windowProtocol": bool(self.windows and self.windows.available),
            "windowCount": len(self.controller.data["windows"]),
            "input": self.controller.data["input"],
            "shortcuts": self.controller._shortcut_state(),
            "services": {key: self.controller.data[key].get("available", False) for key in ("wifi", "bluetooth", "audio", "brightness", "battery")},
            "serviceErrors": {key: self.controller.data[key]["error"] for key in ("wifi", "bluetooth", "audio", "brightness", "battery") if self.controller.data[key].get("error")},
        }, ensure_ascii=False)


def main(argv=None):
    language = ConfigStore().data["preferences"]["language"]
    parser = argparse.ArgumentParser(description=render(tr('uDeck · uConsole 按键原生桌面'), language))
    parser.add_argument("--mock", action="store_true", help=render(tr('安全预览，不操作真实硬件、应用或文件'), language))
    parser.add_argument("--windowed", action="store_true", help=render(tr('以普通窗口运行，不切换桌面会话'), language))
    parser.add_argument("--no-input", action="store_true", help=render(tr('诊断时不接管手柄和鼠标设备'), language))
    parser.add_argument("--screenshot", type=Path, help=render(tr('保存当前窗口 PNG'), language))
    parser.add_argument("--quit-after", type=float, default=0, metavar="SECONDS")
    parser.add_argument("--page", choices=("home", "apps", "windows", "files", "settings"), default="home")
    parser.add_argument("--smoke-test", action="store_true", help=render(tr('只在 --mock 下执行界面冒烟检查'), language))
    options = parser.parse_args(argv)
    if options.smoke_test and not options.mock:
        parser.error(render(tr('--smoke-test 必须同时使用 --mock，避免操作真实设备'), language))
    if not options.mock and sys.platform != "linux":
        parser.error(render(tr('真实桌面仅支持 Linux；请在此平台使用 --mock --windowed'), language))
    os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")
    if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
        os.environ.setdefault("QT_QUICK_BACKEND", "software")
    started = time.monotonic()
    application = QGuiApplication([sys.argv[0]])
    application.setOverrideCursor(Qt.CursorShape.BlankCursor)
    application.setApplicationName(APP_ID)
    application.setDesktopFileName(APP_ID)
    application.setOrganizationName("uDeck")
    application.setWindowIcon(QIcon(str(Path(__file__).parent / "assets/branding/udeck.svg")))
    temporary = tempfile.TemporaryDirectory(prefix="udeck-preview-") if options.mock else None
    config = ConfigStore(Path(temporary.name) / "settings.json") if temporary else ConfigStore()
    if options.mock:
        backend = MockBackend()
        windows = None
    else:
        from .backend import SystemBackend

        backend = SystemBackend()
        windows = WindowService()
    controller = ShellController(backend, windows, config=config, mock=options.mock, defer_startup=True)
    control = Control(controller, windows)
    session_bus = QDBusConnection.sessionBus()
    service_name = APP_ID + (".Preview" if options.mock else "")
    ipc_registered = session_bus.isConnected() and not options.mock
    if ipc_registered:
        if not session_bus.registerService(service_name):
            print(render(tr('uDeck 已在本会话运行；请使用 udeckctl 返回桌面。'), controller.language), file=sys.stderr)
            controller.close()
            if temporary:
                temporary.cleanup()
            return 1
        session_bus.registerObject(CONTROL_PATH, CONTROL_INTERFACE, control, QDBusConnection.RegisterOption.ExportAllSlots)
    gamepad = Gamepad(config.data["input"]) if not options.mock and not options.no_input else None
    pointer = PointerGuard() if not options.mock and not options.windowed and not options.no_input else None
    from .terminal_routing import SuiteInputBroker, TerminalInputBroker

    control.terminal_broker = TerminalInputBroker(windows, pointer)
    control.suite_broker = SuiteInputBroker(windows, pointer)
    application_router = None
    virtual_input = None
    direction_reader = None
    isolation = None
    shortcut_session = None
    if not options.mock:
        from .virtual_input import VirtualInput

        virtual_input = VirtualInput()
        virtual_input.start()
        if controller.shortcut_store:
            from .shortcut_session import ShortcutSession
            shortcut_session = ShortcutSession(controller.shortcut_store, virtual_input)
            controller.attachShortcutSession(shortcut_session)
            control.shortcut_session = shortcut_session
            def enable_shortcuts(values):
                state = values.get('sessionInput', {})
                if state.get('available') and state.get('active') and not state.get('locked'):
                    shortcut_session.start()
            backend.updated.connect(enable_shortcuts)
    if gamepad and pointer and shortcut_session and shortcut_session.available and os.environ.get('UDECK_SESSION') == '1':
        from .compatibility import ApplicationRouter
        from .directions import DirectionReader
        from .session_config import DirectionIsolation
        isolation = DirectionIsolation(virtual_input, coordinator=shortcut_session)
        if isolation.available:
            application_router = ApplicationRouter(controller, windows, gamepad, virtual_input, isolation)
            application_router.session_safe = False
            control.application_router = application_router
            control.isolation = isolation
            direction_reader = DirectionReader()
            direction_reader.direction.connect(application_router.direction)
            direction_reader.status.connect(application_router.direction_status)
            virtual_input.failed.connect(application_router._failed)
            gamepad.button.connect(application_router.button)
            gamepad.status.connect(application_router.gamepad_status)
            pointer.shoulder.connect(application_router.shoulder)
            controller.inputSuspended.connect(application_router.set_suspended)
            backend.updated.connect(lambda values: application_router.session_update(values['sessionInput']) if 'sessionInput' in values else None)
            direction_reader.start()
    if not application_router:
        controller.input_status({'compatibility': {
            'available': False, 'mode': 'unavailable', 'application': '', 'windowId': '',
            'virtualInput': bool(virtual_input and virtual_input.available), 'directionIsolation': False,
            'directionReader': False, 'sessionSafe': False, 'configurationPending': False,
            'error': tr('完整应用兼容模式需要独立 uDeck 会话；窗口预览和原桌面不接管应用输入'),
        }})
    if pointer:
        pointer.action.connect(application_router.action if application_router else controller.dispatch)
        pointer.button.connect(lambda action, pressed: controller.testButton(action, pressed, "shoulder"))
        pointer.middleButton.connect(lambda pressed: controller.testButton("pointer-click", pressed, "pointer"))
        pointer.motion.connect(controller.testPointerMotion)
        pointer.status.connect(controller.input_status)
        controller.foregroundChanged.connect(pointer.set_foreground)
    console_panel = ConsolePanel(controller, windows, application_router)
    control.console_panel = console_panel
    trackball = None
    if pointer:
        from .trackball import TrackballInput

        trackball = TrackballInput(pointer, controller, windows, virtual_input)
    calibration = {"buttons": {}, "axes": {}, "keyboard": {}, "step": 0}

    if gamepad:
        gamepad.auxiliaryButton.connect(lambda action, pressed: controller.testButton(action, pressed, "gamepad"))
        gamepad.button.connect(lambda action, pressed: controller.testButton(action, pressed, "gamepad")
                               if action not in ("up", "down", "left", "right") else None)
        gamepad.direction.connect(lambda action, pressed: controller.testButton(action, pressed, "gamepad"))
        gamepad.action.connect(application_router.action if application_router else controller.dispatch)
        gamepad.status.connect(controller.input_status)
        controller.foregroundChanged.connect(application_router.window_active if application_router else gamepad.set_foreground)

        def calibrate():
            calibration.update({"buttons": {}, "axes": {}, "keyboard": {}, "step": 0})
            gamepad.calibrating = True
            controller._push({"kind": "calibration", "title": tr('按键校准 · 上'), "body": tr('请按下物理方向键「上」并松开。\n方向键支持原生键盘事件；ABXY 仅接收独立手柄事件。Esc 取消。')})

        def captured(kind, code):
            if controller.modal.get("kind") != "calibration":
                gamepad.calibrating = False
                return
            if code in calibration[kind]:
                controller.notify(tr('此按钮已记录，请按屏幕指定的另一个按钮'))
                return
            actions = ("up", "down", "left", "right", "accept", "back", "context", "quick-settings")
            labels = (tr('上'), tr('下'), tr('左'), tr('右'), "A", "B", "X", "Y")
            action = actions[calibration["step"]]
            if kind == "keyboard" and (code != action or action not in ("up", "down", "left", "right")):
                controller.notify(tr('请按屏幕指定的方向；ABXY 步骤只接收独立手柄事件'))
                return
            if kind == "axes" and action not in ("up", "down", "left", "right"):
                controller.notify(tr('此步骤请按下 ABXY 按钮，而非方向键'))
                return
            calibration[kind][code] = action
            calibration["step"] += 1
            if calibration["step"] == 8:
                gamepad.calibrating = False
                config.data["input"] = gamepad.set_profile(calibration["buttons"], calibration["axes"], list(calibration["keyboard"]))
                try:
                    config.save()
                except OSError as error:
                    controller._pop()
                    controller.notify(tr('校准在本次运行生效，但配置保存失败：{value0}', value0=error))
                    return
                controller._pop()
                controller.notify(tr('方向键与 ABXY 映射已保存；请继续实测长按、返回和文字输入'))
            else:
                label = labels[calibration["step"]]
                controller.modal.update({"title": tr('按键校准 · ') + label, "body": tr('请按下物理「') + label + tr('」并松开。\n方向键支持原生键盘事件；ABXY 仅接收独立手柄事件。Esc 取消。')})
                controller._publish()

        controller.calibrationRequested.connect(calibrate)
        gamepad.captured.connect(lambda code: captured("buttons", code))
        gamepad.axisCaptured.connect(lambda code: captured("axes", code))
        controller.calibrationDirection.connect(lambda direction: captured("keyboard", direction))
        controller.changed.connect(lambda: setattr(gamepad, "calibrating", controller.modal.get("kind") == "calibration"))
    engine = QQmlApplicationEngine()
    engine.addImageProvider("desktop", IconProvider())
    engine.rootContext().setContextProperty("controller", controller)
    engine.rootContext().setContextProperty("windowedPreview", options.windowed or options.mock)
    engine.rootContext().setContextProperty("headlessPreview", os.environ.get("QT_QPA_PLATFORM") == "offscreen")
    qml_errors = []
    engine.warnings.connect(lambda warnings: qml_errors.extend(warning.toString() for warning in warnings))
    engine.load(QUrl.fromLocalFile(str(Path(__file__).parent / "qml/Main.qml")))
    if not engine.rootObjects():
        controller.close()
        return 2
    window = engine.rootObjects()[0]
    from .key_test import KeyTestFilter

    key_test_filter = KeyTestFilter(controller, window)
    from .shortcut_recorder import ShortcutRecorder
    controller.shortcut_recorder = ShortcutRecorder(controller, engine, window, virtual_input)
    pointer_cursor = PointerCursor(window, pointer=pointer, gamepad=gamepad)
    window.setProperty("pointerCursor", pointer_cursor)
    from .key_test_device import KeyTestReader

    key_test_reader = KeyTestReader()
    key_test_reader.key.connect(controller.testHardwareKey)
    key_test_reader.reset.connect(controller.resetHardwareKeys)
    key_test_reader.status.connect(controller.input_status)

    def key_test_warning(message):
        if controller.modal.get("kind") == "key-test" and controller.modal.get("deviceWarning") != message:
            controller.modal["deviceWarning"] = message
            controller._publish()

    key_test_reader.warning.connect(key_test_warning)
    controller.changed.connect(lambda: key_test_reader.set_enabled(
        not options.mock and controller.modal.get("kind") == "key-test" and controller._test_active))
    controller.foregroundChanged.connect(lambda active: key_test_reader.set_enabled(
        not options.mock and active and controller.modal.get("kind") == "key-test"))

    def first_frame():
        if control.startup_frame is None:
            control.startup_frame = round(time.monotonic() - started, 3)
        if control.first_frame is None and not controller.startup["active"]:
            control.first_frame = round(time.monotonic() - started, 3)

    window.frameSwapped.connect(first_frame)
    window.frameSwapped.connect(controller.startupFrameSwapped)
    if windows:
        windows.start()
        controller.present.connect(windows.activate_shell)
    backend.start()
    if pointer:
        pointer.start()
    controller.setPage(options.page)
    sounds = InterfaceSounds(config.path, window, silent=os.environ.get("QT_QPA_PLATFORM") == "offscreen")
    controller.soundRequested.connect(sounds.request)

    def capture():
        if options.screenshot:
            options.screenshot.parent.mkdir(parents=True, exist_ok=True)
            if not window.grabWindow().save(str(options.screenshot)):
                qml_errors.append(tr('截图保存失败'))

    if options.smoke_test:
        def smoke():
            for page in ("home", "apps", "windows", "files", "settings"):
                controller.setPage(page)
                for action in ("up", "down", "right", "left", "context", "back"):
                    controller.dispatch(action)
            controller.dispatch("quick-settings")
            controller.dispatch("back")
            controller.setPage(options.page)
            print(json.dumps({"smoke": "passed" if not qml_errors else "failed", "qmlErrors": qml_errors, "diagnostics": json.loads(control.Diagnose())}, ensure_ascii=False), flush=True)

        QTimer.singleShot(800, smoke)
    if options.screenshot:
        QTimer.singleShot(1500, capture)
    if options.quit_after:
        QTimer.singleShot(round(options.quit_after * 1000), application.quit)
    elif options.smoke_test:
        QTimer.singleShot(2000, application.quit)
    result = application.exec()
    key_test_reader.close()
    console_panel.close()
    if trackball:
        trackball.close()
    window.removeEventFilter(key_test_filter)
    pointer_cursor.close()
    if application_router:
        application_router.close()
    if direction_reader:
        direction_reader.close()
    if isolation:
        isolation.restore()
    if virtual_input:
        virtual_input.close()
    if gamepad:
        gamepad.close()
    if pointer:
        pointer.close()
    sounds.close()
    controller.close()
    backend.close()
    if windows:
        windows.close()
    if ipc_registered:
        session_bus.unregisterObject(CONTROL_PATH)
        session_bus.unregisterService(service_name)
    if temporary:
        temporary.cleanup()
    return 2 if qml_errors else result


if __name__ == "__main__":
    raise SystemExit(main())
