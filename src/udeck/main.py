import argparse
import hashlib
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import unquote

from PySide6.QtCore import QObject, QSize, Qt, QTimer, QUrl, Slot
from PySide6.QtDBus import QDBusConnection
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontDatabase,
    QGuiApplication,
    QIcon,
    QImage,
    QPainter,
    QPen,
)
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickImageProvider

from . import __version__
from .controller import ShellController
from .core import ConfigStore
from .input import Gamepad
from .mock import MockBackend
from .windows import APP_ID, WindowService

CONTROL_PATH = "/io/github/zhubby/uDeck"
CONTROL_INTERFACE = "io.github.zhubby.uDeck.Control"


class IconProvider(QQuickImageProvider):
    def __init__(self):
        super().__init__(QQuickImageProvider.ImageType.Image)

    def requestImage(self, identifier, size, requested_size):
        name = unquote(identifier)
        dimension = max(48, min(160, requested_size.width() if requested_size.width() > 0 else 80))
        icon = QIcon(name) if name.startswith("/") else QIcon.fromTheme(name)
        if not icon.isNull():
            image = icon.pixmap(QSize(dimension, dimension)).toImage()
        else:
            image = self._draw(name, dimension)
        size.setWidth(image.width())
        size.setHeight(image.height())
        return image

    def _draw(self, name, dimension):
        image = QImage(dimension, dimension, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.scale(dimension / 64, dimension / 64)
        painter.setPen(Qt.PenStyle.NoPen)
        shades = ["#394b4d", "#4e4233", "#3d4658", "#4b4351", "#3e4d41"]
        painter.setBrush(QColor(shades[hashlib.sha256(name.encode()).digest()[0] % len(shades)]))
        painter.drawRoundedRect(1, 1, 62, 62, 13, 13)
        painter.setPen(QPen(QColor("#ead7b2"), 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        if "folder" in name or "file-manager" in name:
            painter.drawLine(14, 22, 14, 46)
            painter.drawLine(14, 46, 50, 46)
            painter.drawLine(50, 46, 50, 25)
            painter.drawLine(50, 25, 32, 25)
            painter.drawLine(32, 25, 27, 19)
            painter.drawLine(27, 19, 14, 19)
            painter.drawLine(14, 19, 14, 22)
        elif "terminal" in name:
            painter.drawLine(16, 21, 27, 31)
            painter.drawLine(27, 31, 16, 41)
            painter.drawLine(34, 43, 48, 43)
        elif "code" in name or "geany" in name:
            painter.drawLine(24, 21, 14, 32)
            painter.drawLine(14, 32, 24, 43)
            painter.drawLine(40, 21, 50, 32)
            painter.drawLine(50, 32, 40, 43)
            painter.drawLine(36, 17, 28, 47)
        elif any(term in name for term in ("game", "retro", "libretro")):
            painter.drawRoundedRect(11, 20, 42, 27, 9, 9)
            painter.drawLine(18, 33, 30, 33)
            painter.drawLine(24, 27, 24, 39)
            painter.drawEllipse(40, 28, 3, 3)
            painter.drawEllipse(46, 35, 3, 3)
        elif "grid" in name:
            for horizontal in (16, 36):
                for vertical in (16, 36):
                    painter.drawRoundedRect(horizontal, vertical, 13, 13, 2, 2)
        elif any(term in name for term in ("preferences", "brightness", "audio")):
            for horizontal, vertical in ((20, 24), (32, 39), (44, 28)):
                painter.drawLine(horizontal, 15, horizontal, 49)
                painter.fillRect(horizontal - 4, vertical - 4, 8, 8, QColor("#ead7b2"))
        elif "wireless" in name or "firefox" in name:
            painter.drawEllipse(15, 15, 34, 34)
            painter.drawLine(32, 18, 32, 46)
            painter.drawLine(18, 32, 46, 32)
            painter.drawEllipse(24, 15, 16, 34)
        elif "go-home" in name:
            painter.drawLine(13, 29, 32, 14)
            painter.drawLine(32, 14, 51, 29)
            painter.drawLine(19, 25, 19, 49)
            painter.drawLine(19, 49, 45, 49)
            painter.drawLine(45, 49, 45, 25)
            painter.drawRect(28, 36, 9, 13)
        else:
            painter.drawRoundedRect(17, 13, 30, 38, 3, 3)
            painter.drawLine(24, 25, 40, 25)
            painter.drawLine(24, 33, 40, 33)
            painter.drawLine(24, 41, 34, 41)
        painter.end()
        return image


class Control(QObject):
    def __init__(self, controller, windows):
        super().__init__()
        self.controller = controller
        self.windows = windows
        self.started = time.monotonic()
        self.first_frame = None

    @Slot()
    def Home(self):
        self.controller.dispatch("home")

    @Slot()
    def Switcher(self):
        self.controller.dispatch("switcher")

    @Slot()
    def QuickSettings(self):
        self.controller.dispatch("quick-settings")

    @Slot(result=str)
    def Diagnose(self):
        return json.dumps({
            "version": __version__, "mock": self.controller.mock,
            "uptimeSeconds": round(time.monotonic() - self.started, 3),
            "firstFrameSeconds": self.first_frame,
            "page": self.controller.navigation.page,
            "windowProtocol": bool(self.windows and self.windows.available),
            "windowCount": len(self.controller.data["windows"]),
            "input": self.controller.data["input"],
            "services": {key: self.controller.data[key].get("available", False) for key in ("wifi", "bluetooth", "audio", "brightness", "battery")},
            "serviceErrors": {key: self.controller.data[key]["error"] for key in ("wifi", "bluetooth", "audio", "brightness", "battery") if self.controller.data[key].get("error")},
        }, ensure_ascii=False)


def main(argv=None):
    parser = argparse.ArgumentParser(description="uDeck · uConsole 按键原生桌面")
    parser.add_argument("--mock", action="store_true", help="安全预览，不操作真实硬件、应用或文件")
    parser.add_argument("--windowed", action="store_true", help="以普通窗口运行，不切换桌面会话")
    parser.add_argument("--no-input", action="store_true", help="诊断时不打开或独占手柄设备")
    parser.add_argument("--screenshot", type=Path, help="保存当前窗口 PNG")
    parser.add_argument("--quit-after", type=float, default=0, metavar="SECONDS")
    parser.add_argument("--page", choices=("home", "apps", "windows", "files", "settings"), default="home")
    parser.add_argument("--smoke-test", action="store_true", help="只在 --mock 下执行界面冒烟检查")
    options = parser.parse_args(argv)
    if options.smoke_test and not options.mock:
        parser.error("--smoke-test 必须同时使用 --mock，避免操作真实设备")
    if not options.mock and sys.platform != "linux":
        parser.error("真实桌面仅支持 Linux；请在此平台使用 --mock --windowed")
    os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")
    if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
        os.environ.setdefault("QT_QUICK_BACKEND", "software")
    started = time.monotonic()
    application = QGuiApplication([sys.argv[0]])
    application.setApplicationName(APP_ID)
    application.setDesktopFileName(APP_ID)
    application.setOrganizationName("uDeck")
    families = QFontDatabase.families()
    font_family = next((family for family in ("Noto Sans CJK SC", "PingFang SC", "WenQuanYi Micro Hei") if family in families), application.font().family())
    application.setFont(QFont(font_family))
    temporary = tempfile.TemporaryDirectory(prefix="udeck-preview-") if options.mock else None
    config = ConfigStore(Path(temporary.name) / "settings.json") if temporary else ConfigStore()
    if options.mock:
        backend = MockBackend()
        windows = None
    else:
        from .backend import SystemBackend

        backend = SystemBackend()
        windows = WindowService()
    controller = ShellController(backend, windows, config=config, mock=options.mock)
    control = Control(controller, windows)
    session_bus = QDBusConnection.sessionBus()
    service_name = APP_ID + (".Preview" if options.mock else "")
    ipc_registered = session_bus.isConnected() and not options.mock
    if ipc_registered:
        if not session_bus.registerService(service_name):
            print("uDeck 已在本会话运行；请使用 udeckctl 返回桌面。", file=sys.stderr)
            controller.close()
            if temporary:
                temporary.cleanup()
            return 1
        session_bus.registerObject(CONTROL_PATH, CONTROL_INTERFACE, control, QDBusConnection.RegisterOption.ExportAllSlots)
    gamepad = Gamepad(config.data["input"]) if not options.mock and not options.no_input else None
    calibration = {"buttons": {}, "axes": {}, "step": 0}

    if gamepad:
        gamepad.action.connect(controller.dispatch)
        gamepad.status.connect(controller.input_status)
        controller.foregroundChanged.connect(gamepad.set_foreground)

        def calibrate():
            calibration.update({"buttons": {}, "axes": {}, "step": 0})
            gamepad.calibrating = True
            controller._push({"kind": "calibration", "title": "按键校准 · 上", "body": "请按下物理方向键「上」。\n每次按下后松开；只接收独立手柄事件，Esc 取消。"})

        def captured(kind, code):
            if controller.modal.get("kind") != "calibration":
                gamepad.calibrating = False
                return
            if code in calibration[kind]:
                controller.notify("此按钮已记录，请按屏幕指定的另一个按钮")
                return
            actions = ("up", "down", "left", "right", "accept", "back", "context", "quick-settings")
            labels = ("上", "下", "左", "右", "A", "B", "X", "Y")
            action = actions[calibration["step"]]
            if kind == "axes" and action not in ("up", "down", "left", "right"):
                controller.notify("此步骤请按下 ABXY 按钮，而非方向键")
                return
            calibration[kind][code] = action
            calibration["step"] += 1
            if calibration["step"] == 8:
                gamepad.calibrating = False
                config.data["input"] = gamepad.set_profile(calibration["buttons"], calibration["axes"])
                try:
                    config.save()
                except OSError as error:
                    controller._pop()
                    controller.notify(f"校准在本次运行生效，但配置保存失败：{error}")
                    return
                controller._pop()
                controller.notify("方向键与 ABXY 映射已保存；请继续实测长按、返回和文字输入")
            else:
                label = labels[calibration["step"]]
                controller.modal.update({"title": "按键校准 · " + label, "body": "请按下物理「" + label + "」并松开。\n只接收独立手柄事件，Esc 取消。"})
                controller._publish()

        controller.calibrationRequested.connect(calibrate)
        gamepad.captured.connect(lambda code: captured("buttons", code))
        gamepad.axisCaptured.connect(lambda code: captured("axes", code))
        controller.changed.connect(lambda: setattr(gamepad, "calibrating", controller.modal.get("kind") == "calibration"))
    engine = QQmlApplicationEngine()
    engine.addImageProvider("desktop", IconProvider())
    engine.rootContext().setContextProperty("controller", controller)
    engine.rootContext().setContextProperty("appFont", font_family)
    engine.rootContext().setContextProperty("windowedPreview", options.windowed or options.mock)
    engine.rootContext().setContextProperty("headlessPreview", os.environ.get("QT_QPA_PLATFORM") == "offscreen")
    qml_errors = []
    engine.warnings.connect(lambda warnings: qml_errors.extend(warning.toString() for warning in warnings))
    engine.load(QUrl.fromLocalFile(str(Path(__file__).parent / "qml/Main.qml")))
    if not engine.rootObjects():
        controller.close()
        return 2
    window = engine.rootObjects()[0]

    def first_frame():
        if control.first_frame is None:
            control.first_frame = round(time.monotonic() - started, 3)

    window.frameSwapped.connect(first_frame)
    if windows:
        windows.start()
        controller.present.connect(windows.activate_shell)
    backend.start()
    controller.setPage(options.page)

    def capture():
        if options.screenshot:
            options.screenshot.parent.mkdir(parents=True, exist_ok=True)
            if not window.grabWindow().save(str(options.screenshot)):
                qml_errors.append("截图保存失败")

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
    if gamepad:
        gamepad.close()
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
