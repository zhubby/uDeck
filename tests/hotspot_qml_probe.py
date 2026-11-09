"""Render real hotspot menus and radio states; no hardware is changed."""

import argparse
import json
import tempfile
from copy import deepcopy
from pathlib import Path

from PySide6.QtCore import QPointF, Qt, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine, QQmlEngine, QQmlExpression
from PySide6.QtQuick import QQuickItem
from PySide6.QtTest import QTest
from shiboken6 import delete

from udeck import main
from udeck.controller import ShellController
from udeck.core import ConfigStore
from udeck.i18n import tr
from udeck.mock import MockBackend


def run():
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--language", default="en")
    parser.add_argument("--theme", default="classic")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    application = QGuiApplication([])
    with tempfile.TemporaryDirectory(prefix="udeck-hotspot-") as temporary:
        backend = MockBackend()
        controller = ShellController(backend, config=ConfigStore(Path(temporary) / "settings.json"), mock=True)
        controller.setLanguage(args.language)
        controller.setTheme(args.theme)
        controller.setPage("settings")
        controller.select(next(i for i, item in enumerate(controller._items()) if item["id"] == "hotspot"))
        engine, errors = QQmlApplicationEngine(), []
        engine.warnings.connect(lambda warnings: errors.extend(w.toString() for w in warnings))
        engine.addImageProvider("desktop", main.IconProvider())
        for name, value in (("controller", controller), ("windowedPreview", True), ("headlessPreview", True)):
            engine.rootContext().setContextProperty(name, value)
        engine.load(QUrl.fromLocalFile(str(Path(main.__file__).parent / "qml/Main.qml")))
        assert engine.rootObjects(), errors
        window = engine.rootObjects()[0]
        window.setWidth(args.width)
        window.setHeight(args.height)
        captures = []

        def choose(action):
            controller.chooseModal(next(i for i, item in enumerate(controller.modal["options"]) if item["action"] == action))

        def capture(name):
            QTest.qWait(80)
            for item in window.findChildren(QQuickItem):
                if item.objectName() in ("dialogPanel", "dialogContent") and item.isVisible():
                    pos = item.mapToItem(window.contentItem(), QPointF(0, 0))
                    assert pos.x() >= -1 and pos.y() >= -1, name
                    assert pos.x() + item.width() <= window.width() + 1, name
                    assert pos.y() + item.height() <= window.height() + 1, name
            expression = QQmlExpression(QQmlEngine.contextForObject(window), window, """
                JSON.stringify((function() {
                    const icons = []
                    function visit(item) {
                        if (!item.visible) return
                        if (item.objectName === 'wirelessStatusIcon' && item.deviceId) {
                            const p = item.mapToItem(contentItem, 0, 0)
                            icons.push({id: item.deviceId, kind: item.kind, status: item.status,
                                x: p.x, y: p.y, width: item.width, height: item.height})
                        }
                        for (const child of item.children) visit(child)
                    }
                    visit(contentItem)
                    return icons
                })())
            """)
            value, undefined = expression.evaluate()
            assert not undefined and not expression.hasError(), expression.error().toString()
            icons = json.loads(value)
            expected = json.loads(controller.snapshotJson)["wifiIndicators"]
            assert [(i["id"], i["kind"], i["status"]) for i in icons] == [(i["id"], i["kind"], i["status"]) for i in expected]
            for first, second in zip(icons, icons[1:], strict=False):
                assert second["x"] >= first["x"] + first["width"] + 8, name
            for icon in icons:
                assert icon["x"] > 300 and icon["x"] + icon["width"] <= window.width(), name
            assert window.grabWindow().save(str(args.output / (name + ".png")))
            captures.append(name)

        controller.activateSetting("hotspot")
        capture("adapters")
        controller.chooseModal(next(i for i, item in enumerate(controller.modal["options"]) if item.get("deviceId") == "usb"))
        capture("configuration")
        choose("hotspot-name")
        controller.editText("网" * 11)
        controller.dispatch("accept")
        assert controller.modal["error"]
        capture("invalid-name")
        controller.editText("uDeck Pocket")
        controller.dispatch("accept")
        controller.editText("short")
        controller.dispatch("accept")
        assert controller.modal["error"]
        capture("password-validation")
        editor = next(item for item in window.findChildren(QQuickItem) if item.property("displayText") is not None)
        assert editor.property("displayText") != "short"
        QTest.keyClick(window, Qt.Key.Key_F10)
        QTest.qWait(30)
        assert editor.property("displayText") == "short"
        assert "short" not in controller.snapshotJson
        capture("password-visible")
        controller.editText("preview-password")
        controller.dispatch("accept")
        choose("hotspot-start")
        assert controller.data["wifi"]["devices"][1]["hotspot"]["status"] == "active"
        capture("client-and-hotspot")
        for status in ("starting", "stopping", "restoring", "failed"):
            wifi = deepcopy(backend.state["wifi"])
            wifi["devices"][1]["hotspot"].update(status=status, message=tr("Hotspot transition failed or timed out") if status == "failed" else "")
            controller._update({"wifi": wifi})
            capture(status)
        controller._update({"wifi": deepcopy(backend.state["wifi"])})
        choose("hotspot-stop")
        capture("stopped")
        controller.dispatch("back")
        controller.chooseModal(next(i for i, item in enumerate(controller.modal["options"]) if item.get("deviceId") == "builtin"))
        choose("hotspot-name")
        controller.dispatch("accept")
        controller.editText("preview-password")
        controller.dispatch("accept")
        choose("hotspot-start")
        assert controller.modal["kind"] == "confirm" and controller.modal["index"] == 0
        capture("replace-wifi-confirmation")
        controller.dispatch("right")
        controller.dispatch("accept")
        controller.dispatch("back")
        controller.chooseModal(next(i for i, item in enumerate(controller.modal["options"]) if item.get("deviceId") == "usb"))
        choose("hotspot-start")
        capture("two-hotspots")
        controller._cancel_modals()
        controller.toast = ""
        controller._publish()
        capture("status-overview")
        controller.activateSetting("hotspot")
        controller.chooseModal(next(i for i, item in enumerate(controller.modal["options"]) if item.get("deviceId") == "usb"))
        wifi = deepcopy(backend.state["wifi"])
        wifi["devices"] = wifi["devices"][:1]
        backend.updated.emit({"wifi": wifi})
        assert controller.modal["source"] == "hotspot"
        capture("adapter-removed")
        while controller.modal:
            QTest.keyClick(window, Qt.Key.Key_Escape)
            QTest.qWait(10)
        assert controller.navigation.page == "settings"
        assert controller._items()[controller.navigation.index]["id"] == "hotspot"
        assert "preview-password" not in controller.snapshotJson
        delete(engine)
        controller.close()
        application.processEvents()
        print(json.dumps({"scenarios": captures, "qmlErrors": errors}))


if __name__ == "__main__":
    run()
