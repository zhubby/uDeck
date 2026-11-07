"""Exercise the real Wi-Fi menus with isolated simulated data and keyboard input."""

import argparse
import json
import os
import tempfile
from copy import deepcopy
from pathlib import Path

from PySide6.QtCore import QPointF, Qt, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickItem
from PySide6.QtTest import QTest
from shiboken6 import delete

from udeck import main
from udeck.controller import ShellController
from udeck.core import ConfigStore
from udeck.i18n import tr
from udeck.mock import MockBackend
from udeck.wifi import wifi_failure


def run():
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--language", default="en")
    parser.add_argument("--theme", default="classic")
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    args = parser.parse_args()
    os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")
    app = QGuiApplication([])
    with tempfile.TemporaryDirectory(prefix="udeck-wifi-management-") as temporary:
        backend = MockBackend()
        controller = ShellController(backend, config=ConfigStore(Path(temporary) / "settings.json"), mock=True)
        controller.setLanguage(args.language)
        controller.setTheme(args.theme)
        controller.setPage("settings")
        controller.select(next(i for i, item in enumerate(controller._items()) if item["id"] == "wifi"))
        baseline = deepcopy(backend.state["wifi"])
        engine, errors = QQmlApplicationEngine(), []
        engine.warnings.connect(lambda warnings: errors.extend(w.toString() for w in warnings))
        engine.addImageProvider("desktop", main.IconProvider())
        for key, value in (("controller", controller), ("windowedPreview", True), ("headlessPreview", True)):
            engine.rootContext().setContextProperty(key, value)
        engine.load(QUrl.fromLocalFile(str(Path(main.__file__).parent / "qml/Main.qml")))
        assert engine.rootObjects(), errors
        window = engine.rootObjects()[0]
        window.setWidth(args.width)
        window.setHeight(args.height)
        args.output.mkdir(parents=True, exist_ok=True)
        captures = []

        def choose(action):
            controller.chooseModal(next(i for i, item in enumerate(controller.modal["options"]) if item["action"] == action))

        def open_device(identifier="builtin"):
            controller._cancel_modals()
            controller.toast = ""
            backend.state["wifi"] = deepcopy(baseline)
            controller._update({"wifi": backend.state["wifi"]})
            controller.activateSetting("wifi")
            controller.chooseModal(next(i for i, item in enumerate(controller.modal["options"]) if item.get("deviceId") == identifier))

        def capture(name):
            QTest.qWait(80)
            for item in window.findChildren(QQuickItem):
                if item.objectName() in ("dialogPanel", "dialogContent") and item.isVisible():
                    pos = item.mapToItem(window.contentItem(), QPointF(0, 0))
                    assert pos.x() >= -1 and pos.y() >= -1, (name, item.objectName(), pos)
                    assert pos.x() + item.width() <= window.width() + 1
                    assert pos.y() + item.height() <= window.height() + 1, (name, item.objectName(), item.height())
            assert window.grabWindow().save(str(args.output / (name + ".png")))
            captures.append(name)

        open_device()
        choose("wifi-connect")
        capture("network-menu")
        choose("wifi-password")
        controller.editText("short")
        controller.dispatch("accept")
        assert controller.modal["error"] and controller.modal["text"] == "short"
        capture("password-validation")
        editor = next(item for item in window.findChildren(QQuickItem) if item.property("displayText") is not None)
        hidden = editor.property("displayText")
        QTest.keyClick(window, Qt.Key.Key_F10)
        QTest.qWait(30)
        assert editor.property("displayText") != hidden
        assert editor.property("displayText") == "short"
        assert controller.modal["text"] == "short"
        capture("password-visible")
        controller.dispatch("back")
        choose("wifi-forget")
        capture("forget-confirmation")
        controller.dispatch("back")
        device = backend.state["wifi"]["devices"][0]
        device["addresses"] = {"ip": ["10.8.0.2/24", "2001:db8:abcd:1234:ffff:abcd:1234:5678/64"], "gateway": ["10.8.0.1"], "dns": ["10.8.0.1"]}
        backend.updated.emit({"wifi": deepcopy(backend.state["wifi"])})
        choose("wifi-details")
        capture("network-details")
        controller.dispatch("down")
        controller.dispatch("down")
        controller.dispatch("down")
        controller.dispatch("down")
        controller.dispatch("down")
        capture("network-addresses")
        open_device("usb")
        choose("wifi-connect")
        capture("shared-configuration")
        usb = backend.state["wifi"]["devices"][1]
        own_profile = {**usb["saved"][0], "id": "usb-independent", "uuid": "usb-independent", "revision": "fixture",
                       "name": "Workshop (USB)", "blocked": "", "mutationBlocked": "", "active": False}
        usb["saved"].append(own_profile)
        usb["operation"] = {"id": "joining-fixture", "profileUuid": own_profile["uuid"], "networkKey": usb["networks"][0]["key"], "status": "connecting", "message": tr("Obtaining a network address"), "timedOut": True}
        usb["deviceState"] = 70
        backend.updated.emit({"wifi": deepcopy(backend.state["wifi"])})
        capture("join-progress")
        usb["operation"].update(status="failed", message=wifi_failure(5), timedOut=False)
        usb["deviceState"] = 120
        backend.updated.emit({"wifi": deepcopy(backend.state["wifi"])})
        password_option = next(option for option in controller.modal["options"] if option["action"] == "wifi-password")
        assert not password_option.get("disabled") and password_option["payload"]["profileUuid"] == own_profile["uuid"]
        capture("join-failure")
        open_device()
        backend.state["wifi"]["enabled"] = False
        backend.updated.emit({"wifi": deepcopy(backend.state["wifi"])})
        choose("wifi-saved")
        choose("wifi-saved-connect")
        capture("wifi-off-management")
        open_device("usb")
        usb = backend.state["wifi"]["devices"][1]
        usb["scan"] = {"status": "scanning"}
        backend.updated.emit({"wifi": deepcopy(backend.state["wifi"])})
        capture("scanning")
        choose("wifi-connect")
        backend.state["wifi"]["devices"] = backend.state["wifi"]["devices"][:1]
        backend.updated.emit({"wifi": deepcopy(backend.state["wifi"])})
        assert controller.modal["source"] == "wifi"
        capture("adapter-removed")
        while controller.modal:
            QTest.keyClick(window, Qt.Key.Key_Escape)
            QTest.qWait(10)
        assert controller.navigation.page == "settings"
        assert controller._items()[controller.navigation.index]["id"] == "wifi"
        delete(engine)
        controller.close()
        app.processEvents()
        print(json.dumps({"scenarios": captures, "qmlErrors": errors, "width": args.width, "height": args.height}))


if __name__ == "__main__":
    run()
