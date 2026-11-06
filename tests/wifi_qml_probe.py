"""Render the real QML Wi-Fi flows using the safe MockBackend."""

import argparse
import json
import os
import tempfile
from pathlib import Path

from PySide6.QtCore import QPointF, Qt, QUrl
from PySide6.QtGui import QFont, QFontDatabase, QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtTest import QTest
from shiboken6 import delete

from udeck import main
from udeck.controller import ShellController
from udeck.core import ConfigStore
from udeck.mock import MockBackend


def choose(controller, action):
    controller.chooseModal(next(index for index, option in enumerate(controller.modal["options"]) if option["action"] == action))


def run():
    os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")
    parser = argparse.ArgumentParser()
    parser.add_argument("scenario", choices=("adapters", "networks", "confirm", "saved", "off", "single", "empty", "unplug", "long-name"))
    parser.add_argument("screenshot", type=Path)
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    options = parser.parse_args()
    application = QGuiApplication([])
    families = QFontDatabase.families()
    family = next((font for font in ("Noto Sans CJK SC", "PingFang SC", "WenQuanYi Micro Hei") if font in families), application.font().family())
    application.setFont(QFont(family))
    temporary = tempfile.TemporaryDirectory(prefix="udeck-wifi-preview-")
    controller = ShellController(MockBackend(), config=ConfigStore(Path(temporary.name) / "settings.json"), mock=True)
    controller.setPage("settings")
    controller.select(3)
    if options.scenario == "single":
        controller.data["wifi"]["devices"] = controller.data["wifi"]["devices"][:1]
    elif options.scenario == "empty":
        controller.data["wifi"].update({"available": False, "devices": []})
    elif options.scenario == "off":
        controller.backend.request("wifi_power", {"enabled": False})
    elif options.scenario == "long-name":
        controller.data["wifi"]["devices"][1]["networks"][0]["name"] = "这是一条非常长的无线网络名称-WiFi-Workshop-Guest-" * 8
    engine = QQmlApplicationEngine()
    errors = []
    engine.warnings.connect(lambda warnings: errors.extend(warning.toString() for warning in warnings))
    engine.addImageProvider("desktop", main.IconProvider())
    context = engine.rootContext()
    for name, value in (("controller", controller), ("appFont", family), ("windowedPreview", True), ("headlessPreview", True)):
        context.setContextProperty(name, value)
    engine.load(QUrl.fromLocalFile(str(Path(main.__file__).parent / "qml/Main.qml")))
    assert engine.rootObjects(), errors
    window = engine.rootObjects()[0]
    window.setWidth(options.width)
    window.setHeight(options.height)
    controller.activateSetting("wifi")
    if options.scenario in ("networks", "confirm", "saved", "unplug", "long-name"):
        controller.chooseModal(next(index for index, option in enumerate(controller.modal["options"]) if option.get("deviceId") == "usb"))
        if options.scenario in ("confirm", "long-name"):
            choose(controller, "wifi-connect")
        elif options.scenario == "saved":
            choose(controller, "wifi-saved")
        elif options.scenario == "unplug":
            choose(controller, "wifi-connect")
            controller.data["wifi"]["devices"] = controller.data["wifi"]["devices"][:1]
            controller._update({"wifi": controller.data["wifi"]})
    QTest.qWait(200)
    pending = list(window.contentItem().childItems())
    panels = []
    while pending:
        item = pending.pop()
        pending.extend(item.childItems())
        if item.objectName() in ("dialogPanel", "dialogContent"):
            panels.append(item)
    bounds = []
    for panel in panels:
        origin = panel.mapToItem(window.contentItem(), QPointF(0, 0))
        bounds.append({"name": panel.objectName(), "x": origin.x(), "y": origin.y(), "width": panel.width(), "height": panel.height()})
    options.screenshot.parent.mkdir(parents=True, exist_ok=True)
    assert window.grabWindow().save(str(options.screenshot))
    # Exercise actual QML key routing back through the stack after capturing.
    for _ in range(4):
        if not controller.modal:
            break
        QTest.keyClick(window, Qt.Key.Key_Escape)
        QTest.qWait(10)
    report = {"bounds": bounds, "backReachedSettings": not controller.modal and controller.navigation.page == "settings",
              "width": window.width(), "height": window.height()}
    delete(engine)
    controller.close()
    application.processEvents()
    temporary.cleanup()
    print(json.dumps({**report, "qmlErrors": errors}, ensure_ascii=False))


if __name__ == "__main__":
    run()
