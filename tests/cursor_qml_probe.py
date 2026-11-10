import argparse
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

from PySide6.QtCore import QEvent, QObject, QPoint, QPointF, Qt, QUrl
from PySide6.QtGui import QEnterEvent, QGuiApplication, QMouseEvent
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow
from PySide6.QtTest import QTest
from shiboken6 import delete

from udeck import main
from udeck.controller import ShellController
from udeck.core import ConfigStore
from udeck.cursor import PointerCursor
from udeck.input import Gamepad
from udeck.key_test import KeyTestFilter
from udeck.mock import MockBackend
from udeck.pointer import PointerGuard


def run():
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--theme", default="classic")
    parser.add_argument("--reduced-motion", action="store_true")
    options = parser.parse_args()
    os.environ["UDECK_REDUCED_MOTION"] = "1" if options.reduced_motion else "0"
    application = QGuiApplication([])
    application.setOverrideCursor(Qt.CursorShape.BlankCursor)
    options.output.mkdir(parents=True, exist_ok=True)
    config = ConfigStore(options.output / "settings.json")
    config.data["preferences"].update(
        theme=options.theme, language="en" if options.theme == "classic" else "zh_CN")
    controller = ShellController(MockBackend(), config=config, mock=True)
    engine = QQmlApplicationEngine()
    errors, captures, events, ownership = [], [], [], []
    engine.warnings.connect(lambda warnings: errors.extend(warning.toString() for warning in warnings))
    engine.addImageProvider("desktop", main.IconProvider())
    engine.rootContext().setContextProperty("controller", controller)
    engine.rootContext().setContextProperty("windowedPreview", True)
    engine.rootContext().setContextProperty("headlessPreview", True)
    engine.load(QUrl.fromLocalFile(str(Path(main.__file__).parent / "qml/Main.qml")))
    assert engine.rootObjects(), errors
    window = engine.rootObjects()[0]
    window.resize(options.width, options.height)
    reader, writer = os.pipe()
    device = SimpleNamespace(
        path="/dev/input/event8", name="ClockworkPI uConsole Mouse", fd=reader,
        info=SimpleNamespace(vendor=0x1EAF, product=0x0024), uniq="20230713",
        capabilities=lambda: {1: [272, 273, 274], 2: [0, 1, 8]},
        active_keys=lambda: [], grab=lambda: ownership.append("grab"),
        ungrab=lambda: ownership.append("ungrab"), close=lambda: None,
        read=lambda: list(events),
    )
    sys.modules["evdev"] = SimpleNamespace(InputDevice=lambda path: device,
                                           list_devices=lambda: [device.path])
    pointer = PointerGuard()
    gamepad = Gamepad()
    key_test_filter = KeyTestFilter(controller, window)
    cursor = PointerCursor(window, pointer=pointer, gamepad=gamepad)
    window.setProperty("pointerCursor", cursor)
    pointer.action.connect(controller.dispatch)
    pointer.motion.connect(controller.testPointerMotion)
    controller.foregroundChanged.connect(pointer.set_foreground)
    pointer.start()

    def raw(event_type, code, value):
        events[:] = [SimpleNamespace(type=event_type, code=code, value=value)]
        pointer._read(device.path)

    def mouse_move(horizontal, vertical):
        position = QPointF(horizontal, vertical)
        event = QMouseEvent(QEvent.Type.MouseMove, position, position,
                            Qt.MouseButton.NoButton, Qt.MouseButton.NoButton,
                            Qt.KeyboardModifier.NoModifier)
        application.sendEvent(window, event)

    def capture(name):
        QTest.qWait(35)
        image = window.grabWindow()
        assert not image.isNull()
        assert image.save(str(options.output / (name + ".png")))
        captures.append(name)
        return image

    other = QQuickWindow()
    try:
        window.requestActivate()
        QTest.qWait(100)
        assert window.isActive()
        pointer.set_foreground(True)
        orb = window.findChild(QObject, "pointerOrb")
        layer = window.findChild(QObject, "pointerLayer")
        assert orb is not None and layer is not None
        assert not cursor.visible and not layer.property("visible")
        hidden = capture("hidden")
        raw(2, 8, 1)
        raw(1, 274, 1)
        raw(1, 274, 0)
        raw(2, 0, 0)
        assert not cursor.visible
        raw(2, 0, 24)
        raw(2, 1, -12)
        expected = QPointF(options.width / 2 + 24, options.height / 2 - 12)
        assert cursor.position == expected and cursor.visible
        assert orb.width() == orb.height()
        assert orb.property("radius") == orb.width() / 2
        assert orb.x() + orb.width() / 2 == expected.x()
        assert orb.y() + orb.height() / 2 == expected.y()
        assert not layer.property("enabled")
        shown = capture("trackball")
        center = expected.toPoint()
        assert hidden.pixelColor(center) != shown.pixelColor(center)
        assert hidden.pixelColor(20, 20) == shown.pixelColor(20, 20)

        controller.setPage("apps")
        assert cursor.visible
        QTest.keyClick(window, Qt.Key.Key_Right)
        assert not cursor.visible and controller.navigation.index == 1
        raw(2, 0, 1)
        raw(1, 273, 1)
        raw(1, 273, 0)
        assert not cursor.visible and controller.navigation.page == "windows"
        controller.setPage("home")
        raw(2, 0, 1)
        gamepad.button.emit("accept", False)
        assert cursor.visible
        gamepad.direction.emit("right", True)
        assert not cursor.visible
        raw(2, 0, 1)
        gamepad.auxiliaryButton.emit("home", True)
        assert not cursor.visible

        controller.activateSetting("key-test")
        raw(2, 0, 2)
        assert cursor.visible
        QTest.keyClick(window, Qt.Key.Key_Left)
        assert not cursor.visible and controller.modal["kind"] == "key-test"
        assert "left" in controller.modal["tested"]
        controller._pop()

        raw(2, 0, 100000)
        raw(2, 1, -100000)
        assert 0 <= cursor.position.x() - orb.width() / 2
        assert cursor.position.x() + orb.width() / 2 <= window.width()
        assert 0 <= cursor.position.y() - orb.height() / 2
        window.resize(960, 600)
        QTest.qWait(20)
        assert cursor.position.x() + orb.width() / 2 <= 960
        window.resize(options.width, options.height)
        QTest.qWait(20)
        cursor.hide()

        raw(2, 0, -100)
        cursor.timer.setInterval(80)
        mouse_move(210, 180)
        QTest.qWait(45)
        mouse_move(210, 180)
        QTest.qWait(65)
        assert not cursor.visible and not cursor.timer.isActive()
        mouse_move(220, 190)
        assert cursor.visible and cursor.position == QPointF(220, 190)
        cursor.timer.setInterval(3000)
        capture("preview")
        controller.setPage("apps")
        QTest.mouseClick(window, Qt.MouseButton.LeftButton,
                         Qt.KeyboardModifier.NoModifier, QPoint(220, 190))
        assert controller.navigation.page == "home"
        application.sendEvent(window, QEvent(QEvent.Type.Leave))
        assert not cursor.visible
        application.sendEvent(window, QEnterEvent(QPointF(220, 190), QPointF(220, 190),
                                                  QPointF(window.mapToGlobal(center))))
        assert not cursor.visible

        raw(2, 0, 15)
        assert cursor.visible
        other.show()
        other.requestActivate()
        QTest.qWait(50)
        assert not window.isActive() and not cursor.visible
        inactive_position = QPointF(cursor.position)
        raw(2, 0, 100)
        mouse_move(30, 30)
        assert not cursor.visible and cursor.position == inactive_position
        window.requestActivate()
        QTest.qWait(50)
        assert window.isActive() and not cursor.visible
        raw(2, 0, 1)
        assert cursor.visible
        window.hide()
        assert not cursor.visible
        hidden_position = QPointF(cursor.position)
        raw(2, 0, 100)
        assert cursor.position == hidden_position and not cursor.visible
        window.show()
        window.requestActivate()
        QTest.qWait(50)

        controller.select(0)
        now = [0.0]
        controller.launches.clock = lambda: now[0]
        controller.launches.begin(controller._items()[0], observable=True)
        controller._refresh_launch()
        controller._publish()
        now[0] = 0.3
        controller._advance_launches()
        QTest.qWait(170)
        overlay = window.findChild(QObject, "appLaunchOverlay")
        assert overlay.property("visible"), controller.app_launch
        mouse_move(options.width / 2, options.height / 2)
        assert cursor.visible and layer.property("z") > overlay.property("z")
        capture("loading")
        QTest.keyClick(window, Qt.Key.Key_Escape)
        assert not cursor.visible and not controller.app_launch["pending"]
        QTest.qWait(140)
        QTest.keyClick(window, Qt.Key.Key_Right)
        assert controller.navigation.index == 1

        raw(2, 0, 1)
        cursor.close()
        assert not cursor.visible and not cursor.timer.isActive()
        raw(2, 0, 100)
        mouse_move(300, 300)
        assert not cursor.visible
        pointer.close()
        assert ownership == ["grab", "ungrab"]
        assert not errors, errors
        print(json.dumps({"qmlErrors": errors, "captures": captures,
                          "navigationPreserved": True, "inputReleased": True,
                          "inactiveMotionIgnored": True}))
    finally:
        cursor.close()
        pointer.close()
        gamepad.close()
        window.removeEventFilter(key_test_filter)
        delete(other)
        delete(engine)
        controller.close()
        application.restoreOverrideCursor()
        os.close(reader)
        os.close(writer)
        application.processEvents()


if __name__ == "__main__":
    run()
