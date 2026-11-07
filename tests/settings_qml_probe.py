"""Render settings and exercise keyboard edges through the real QQuickWindow."""

import argparse
import json
import tempfile
from pathlib import Path

from PySide6.QtCore import QEvent, Qt, QUrl
from PySide6.QtGui import QGuiApplication, QKeyEvent
from PySide6.QtQml import QQmlApplicationEngine, QQmlEngine, QQmlExpression
from PySide6.QtTest import QTest
from shiboken6 import delete

from udeck import main
from udeck.controller import ShellController
from udeck.core import ConfigStore
from udeck.key_test import KeyTestFilter
from udeck.mock import MockBackend


def run():
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--language", default="en")
    parser.add_argument("--theme", default="classic")
    options = parser.parse_args()
    options.output.mkdir(parents=True, exist_ok=True)
    application = QGuiApplication([])
    temporary = tempfile.TemporaryDirectory(prefix="udeck-settings-")
    controller = ShellController(MockBackend(), config=ConfigStore(Path(temporary.name) / "settings.json"), mock=True)
    controller.setLanguage(options.language)
    controller.setTheme(options.theme)
    controller.setPage("settings")
    engine = QQmlApplicationEngine()
    errors, captures = [], []
    engine.warnings.connect(lambda warnings: errors.extend(w.toString() for w in warnings))
    engine.addImageProvider("desktop", main.IconProvider())
    context = engine.rootContext()
    for name, value in (("controller", controller), ("windowedPreview", True), ("headlessPreview", True)):
        context.setContextProperty(name, value)
    engine.load(QUrl.fromLocalFile(str(Path(main.__file__).parent / "qml/Main.qml")))
    assert engine.rootObjects(), errors
    window = engine.rootObjects()[0]
    window.setWidth(options.width)
    window.setHeight(options.height)
    event_filter = KeyTestFilter(controller, window)

    def inspect():
        expression = QQmlExpression(QQmlEngine.contextForObject(window), window, """
            JSON.stringify((function() {
                const result = {caps: [], icons: []}
                function visit(item) {
                    if (!item.visible) return
                    const p = item.mapToItem(contentItem, 0, 0)
                    const rect = {x: p.x, y: p.y, width: item.width, height: item.height}
                    if (item.objectName === 'dialogPanel') result.panel = rect
                    if (item.objectName === 'dialogContent') result.content = rect
                    if (item.objectName.indexOf('testKey-') === 0) result.caps.push(Object.assign(rect,
                        {name: item.objectName, pressed: item.pressed, tested: item.tested, scale: item.scale}))
                    if (item.objectName === 'inputPromptIcon') result.icons.push({key: item.keyId, status: item.status})
                    for (const child of item.children) visit(child)
                }
                visit(contentItem)
                return result
            })())
        """)
        value, undefined = expression.evaluate()
        assert not undefined and not expression.hasError(), expression.error().toString()
        return json.loads(value)

    def capture(name):
        QTest.qWait(150)
        report = inspect()
        if controller.modal:
            panel, content = report["panel"], report["content"]
            assert panel["x"] >= 32 and panel["y"] >= 32, report
            assert panel["x"] + panel["width"] <= window.width() - 32, report
            assert panel["y"] + panel["height"] <= window.height() - 32, report
            assert content["y"] + content["height"] <= panel["y"] + panel["height"], report
            for cap in report["caps"]:
                assert cap["x"] >= content["x"] and cap["x"] + cap["width"] <= content["x"] + content["width"], report
        assert all(icon["status"] == 1 for icon in report["icons"]), report
        assert window.grabWindow().save(str(options.output / f"{name}.png"))
        captures.append({"name": name, **report})
        return report

    try:
        timezone_position = next(i for i, item in enumerate(controller._items()) if item["id"] == "timezone")
        controller.select(timezone_position)
        capture("settings")
        controller.dispatch("accept")
        capture("timezone-regions")
        controller.dispatch("accept")
        controller.chooseModal(next(i for i, item in enumerate(controller.modal["options"]) if item["id"] == "Asia/Tokyo"))
        capture("timezone-cities")
        assert window.property("clockText") == controller.currentTime()
        controller._update({"timezone": {**controller.data["timezone"], "available": False, "error": "timedated: permission denied"}})
        capture("timezone-error")
        controller.dispatch("back")
        controller.dispatch("back")
        assert controller.navigation.index == timezone_position
        key_position = next(i for i, item in enumerate(controller._items()) if item["id"] == "key-test")
        controller.select(key_position)
        controller.dispatch("accept")
        owner = controller.modal["key"]
        report = capture("key-test-idle")
        assert len(report["caps"]) == 10 and not any(cap["pressed"] for cap in report["caps"])
        QTest.keyPress(window, Qt.Key_J)
        assert controller.modal["lastKey"] == "J" and not controller.modal["pressed"]
        count = controller.modal["pressCount"]
        application.sendEvent(window, QKeyEvent(QEvent.Type.KeyPress, Qt.Key_J, Qt.KeyboardModifier.NoModifier, "j", True))
        assert controller.modal["pressCount"] == count
        for key in (Qt.Key_Up, Qt.Key_Return, Qt.Key_F10, Qt.Key_PageUp):
            QTest.keyPress(window, key)
        report = capture("key-test-pressed")
        assert {cap["name"] for cap in report["caps"] if cap["pressed"]} == {"testKey-up", "testKey-accept", "testKey-context", "testKey-previous-page"}
        assert all(abs(cap["scale"] - 0.91) < 0.01 for cap in report["caps"] if cap["pressed"])
        assert controller.modal["key"] == owner and controller.navigation.index == key_position
        controller.notify("A background operation returned a longer message. " * 16)
        capture("key-test-long-message")
        controller._clear_toast()
        for key in (Qt.Key_J, Qt.Key_Up, Qt.Key_Return, Qt.Key_F10, Qt.Key_PageUp):
            QTest.keyRelease(window, key)
        QTest.keyClick(window, Qt.Key_Escape)
        report = capture("key-test-released")
        assert controller.modal["key"] == owner
        assert not any(cap["pressed"] for cap in report["caps"])
        assert sum(cap["tested"] for cap in report["caps"]) == 5
        assert all(abs(cap["scale"] - 1) < 0.01 for cap in report["caps"])
        QTest.keyPress(window, Qt.Key_Escape)
        capture("key-test-exit-hold")
        QTest.qWait(1200)
        QTest.keyRelease(window, Qt.Key_Escape)
        assert not controller.modal and controller.navigation.index == key_position
        assert controller.backend.actions == ["timezone_set"]
        assert not errors, errors
        print(json.dumps({"captures": captures, "qmlErrors": errors}))
    finally:
        window.removeEventFilter(event_filter)
        window.close()
        delete(engine)
        controller.close()
        application.processEvents()
        temporary.cleanup()


if __name__ == "__main__":
    run()
