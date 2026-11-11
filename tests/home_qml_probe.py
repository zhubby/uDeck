import argparse
import json
import tempfile
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine, QQmlEngine, QQmlExpression
from PySide6.QtQuick import QQuickItem
from PySide6.QtTest import QTest
from shiboken6 import delete

from udeck import main
from udeck.controller import ShellController
from udeck.core import ConfigStore
from udeck.mock import MockBackend


def run():
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--language", choices=("en", "zh_CN"), default="zh_CN")
    parser.add_argument("--theme", choices=("classic", "dark"), default="classic")
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    options = parser.parse_args()
    application = QGuiApplication([])
    with tempfile.TemporaryDirectory(prefix="udeck-home-config-") as temporary:
        controller = ShellController(MockBackend(), config=ConfigStore(Path(temporary) / "settings.json"), mock=True)
        controller.setLanguage(options.language)
        controller.setTheme(options.theme)
        engine = QQmlApplicationEngine()
        errors = []
        engine.warnings.connect(lambda warnings: errors.extend(warning.toString() for warning in warnings))
        engine.addImageProvider("desktop", main.IconProvider())
        for key, value in (("controller", controller), ("windowedPreview", True), ("headlessPreview", True)):
            engine.rootContext().setContextProperty(key, value)
        engine.load(QUrl.fromLocalFile(str(Path(main.__file__).parent / "qml/Main.qml")))
        assert engine.rootObjects(), errors
        window = engine.rootObjects()[0]
        window.setWidth(options.width)
        window.setHeight(options.height)
        QTest.qWait(200)

        def visual_item(name):
            pending = [window.contentItem()]
            while pending:
                item = pending.pop()
                if item.objectName() == name:
                    return item
                pending.extend(item.childItems())
            return None

        screen = window.findChild(QQuickItem, "homeScreen")
        strip = window.findChild(QQuickItem, "homeStrip")
        navigation = window.findChild(QQuickItem, "mainNavigation")
        assert screen is not None and strip is not None and navigation is not None
        tabs = [item for item in navigation.childItems() if item.objectName().startswith("mainTab-")]
        assert len(tabs) == 4
        assert strip.property("count") == 7
        first = visual_item("homeTile-0")
        second = visual_item("homeTile-1")
        assert first is not None and second is not None
        assert first.y() == second.y() and first.x() < second.x()
        options.output.mkdir(parents=True, exist_ok=True)
        captures = []

        def capture(name):
            QTest.qWait(180)
            assert not errors, errors
            assert window.grabWindow().save(str(options.output / (name + ".png")))
            captures.append(name)

        def key(value):
            QTest.keyClick(window, value)
            QTest.qWait(30)

        def selected_visible():
            tile = visual_item("homeTile-" + str(controller.navigation.index))
            assert tile is not None
            position = tile.mapToItem(strip, QPointF(0, 0))
            assert position.x() >= -1, position.x()
            assert position.x() + tile.width() <= strip.width() + 1, (position.x(), tile.width(), strip.width())
            card = tile.childItems()[0]
            bounds = card.mapRectToItem(strip, QRectF(0, 0, card.width(), card.height()))
            assert bounds.left() >= 0 and bounds.right() <= strip.width(), bounds

        def fully_visible():
            visible = []
            for index in range(7):
                tile = visual_item("homeTile-" + str(index))
                if tile is None:
                    continue
                position = tile.mapToItem(strip, QPointF(0, 0))
                if position.x() >= -1 and position.x() + tile.width() <= strip.width() + 1:
                    visible.append(index)
                elif options.width >= 1280:
                    assert position.x() + tile.width() <= 0 or position.x() >= strip.width(), position.x()
            return visible

        capture("home")
        selected_visible()
        if options.width >= 1280:
            assert fully_visible() == list(range(6))
            for index in range(6):
                tile = visual_item("homeTile-" + str(index))
                assert tile is not None
                position = tile.mapToItem(strip, QPointF(0, 0))
                assert position.x() >= 0 and position.x() + tile.width() <= strip.width()
        for index in range(1, 7):
            key(Qt.Key.Key_Right)
            assert controller.navigation.index == index
            selected_visible()
            if index == 3:
                capture("home-reader")
            if index == 5:
                icon = visual_item("homeIcon-browser")
                assert icon is not None
                expression = QQmlExpression(QQmlEngine.contextForObject(icon), icon, "Number(status)")
                status, undefined = expression.evaluate()
                assert not undefined and not expression.hasError(), expression.error().toString()
                assert status == 1
                assert icon.property("source").toString().endswith("globe2.svg")
                capture("home-browser")
        key(Qt.Key.Key_Right)
        assert controller.navigation.index == 6
        assert strip.property("contentX") > 0
        if options.width >= 1280:
            assert fully_visible() == list(range(1, 7))
        capture("home-settings")
        # Scrolling back must recover the original six visible cards.
        for index in reversed(range(6)):
            key(Qt.Key.Key_Left)
            assert controller.navigation.index == index
            selected_visible()
        if options.width >= 1280:
            assert fully_visible() == list(range(6))
        for _ in range(6):
            key(Qt.Key.Key_Right)
        key(Qt.Key.Key_Up)
        assert controller.navigation.zone == "tabs"
        for page in ("apps", "windows", "files", "files"):
            key(Qt.Key.Key_Right)
            assert controller.navigation.page == page
        controller.dispatch("home")
        QTest.qWait(40)
        assert controller.navigation.index == 6
        key(Qt.Key.Key_Return)
        assert controller.navigation.page == "settings"
        assert json.loads(controller.snapshotJson)["activeTab"] == "home"
        capture("settings")
        key(Qt.Key.Key_Escape)
        assert controller.navigation.page == "home" and controller.navigation.index == 6
        selected_visible()
        key(Qt.Key.Key_F1)
        assert controller.modal.get("source") == "quick-settings"
        capture("quick-settings")
        key(Qt.Key.Key_Escape)
        assert controller.navigation.page == "home" and controller.navigation.index == 6
        assert not controller.backend.actions
        assert not errors, errors
        print(json.dumps({"tabCount": len(tabs), "shortcutCount": strip.property("count"),
                          "focusRestored": True, "captures": captures, "qmlErrors": errors}), flush=True)
        window.close()
        controller.close()
        delete(engine)
        application.processEvents()


if __name__ == "__main__":
    run()
