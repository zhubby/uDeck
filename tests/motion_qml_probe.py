"""
[INPUT]: 依赖真实桌面 QML、隔离配置与可控启动时钟。
[OUTPUT]: 验证焦点改向、模态关闭隔离与局部启动反馈。
[POS]: 独立进程回归探针，不修改设备安装包或用户数据。
[PROTOCOL]: Update this header on change, then check AGENTS.md
"""

import json
import os
import sys
import time
from pathlib import Path

from PySide6.QtCore import QMetaObject, QPointF, Qt, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtTest import QTest
from shiboken6 import delete

from udeck import main
from udeck.controller import ShellController
from udeck.core import ConfigStore
from udeck.mock import MockBackend


def wait_until(predicate):
    deadline = time.monotonic() + 2
    while not predicate() and time.monotonic() < deadline:
        QTest.qWait(10)
    assert predicate()


def run():
    output = Path(sys.argv[1])
    output.mkdir(parents=True, exist_ok=True)
    reduced = os.environ.get("UDECK_REDUCED_MOTION") == "1"
    application = QGuiApplication([])
    controller = ShellController(MockBackend(), config=ConfigStore(output / "settings.json"), mock=True)
    controller.setLanguage("en")
    controller.setTheme(sys.argv[2])
    controller._windows_changed([{"id": str(i), "appId": "motion." + str(i),
                                  "name": "Motion " + str(i), "active": False} for i in range(12)])
    controller.runtime_console.timer.stop()
    engine = QQmlApplicationEngine()
    errors = []
    engine.warnings.connect(lambda warnings: errors.extend(w.toString() for w in warnings))
    engine.addImageProvider("desktop", main.IconProvider())
    for key, value in (("controller", controller), ("windowedPreview", True), ("headlessPreview", True)):
        engine.rootContext().setContextProperty(key, value)
    engine.load(QUrl.fromLocalFile(str(Path(main.__file__).parent / "qml/Main.qml")))
    assert engine.rootObjects(), errors
    window = engine.rootObjects()[0]

    def visual_items(item):
        yield item
        for child in item.childItems():
            yield from visual_items(child)

    def visual(name):
        item = next((item for item in visual_items(window.contentItem()) if item.objectName() == name), None)
        assert item is not None, ("missing visual", name)
        return item

    try:
        QTest.qWait(200)
        controller.setPage("apps")
        controller.select(0)
        QTest.qWait(200)
        focus = visual("appFocus")
        start_x = focus.x()
        controller.select(4)
        assert controller.navigation.index == 4
        application.processEvents()
        target = visual("applicationGrid").property("currentItem")
        if reduced:
            assert abs(focus.x() - target.x()) < 1
        else:
            focus.setX(start_x)
            assert QMetaObject.invokeMethod(focus, "position")
            assert any(child.property("property") == "x" and child.property("running") for child in focus.children())
            QTest.qWait(30)
            assert start_x < focus.x() <= target.x(), (focus.x(), target.x())
        for index in (3, 1, 4, 2):
            controller.select(index)
            assert controller.navigation.index == index
            application.processEvents()
        wait_until(lambda: abs(focus.x() - visual("applicationGrid").property("currentItem").x()) < 1)
        if not reduced:
            controller.select(4)
            QTest.qWait(20)
            os.environ["UDECK_REDUCED_MOTION"] = "1"
            controller._publish()
            application.processEvents()
            assert abs(focus.x() - visual("applicationGrid").property("currentItem").x()) < 1
            os.environ["UDECK_REDUCED_MOTION"] = "0"
            controller._publish()
            application.processEvents()

        retained = visual("applicationGrid").property("currentItem")
        destroyed = []
        retained.destroyed.connect(lambda: destroyed.append(True))
        controller.setPage("home")
        QTest.qWait(180)
        controller.setPage("apps")
        QTest.qWait(180)
        assert not destroyed, "hidden application page discarded its delegates"

        controller.setPage("windows")
        QTest.qWait(180)
        controller.consoleAppAction("motion.0", "details")
        application.processEvents()
        shade = visual("modalShade")
        wait_until(lambda: shade.opacity() > 0.99)
        controller.runtime_console.summaryChanged.emit()
        QTest.qWait(20)
        assert shade.opacity() > 0.99, "metric refresh restarts modal animation"
        QTest.keyClick(window, Qt.Key_Escape)
        application.processEvents()
        assert not controller.modal
        assert not visual("dialogPanel").isEnabled()
        if not reduced:
            assert shade.isVisible(), "modal disappeared before closing transition"
            row = visual("consoleRow-motion.1")
            point = row.mapToScene(QPointF(80, 24)).toPoint()
            QTest.mouseClick(window, Qt.LeftButton, pos=point)
            application.processEvents()
            assert not controller.modal, "closing modal leaked a click into the list"
        wait_until(lambda: not shade.isVisible())
        controller.consoleAppAction("motion.0", "details")
        QTest.qWait(180)
        QTest.keyClick(window, Qt.Key_Escape)
        QTest.keyClick(window, Qt.Key_Down)
        assert controller.navigation.index == 1, "next navigation waits for animation"
        application.processEvents()
        assert not shade.isVisible(), "new navigation retained stale closing content"
        controller.consoleAppAction("motion.0", "details")
        QTest.qWait(180)
        controller.dispatch("back")
        controller.dispatch("down")
        application.processEvents()
        assert controller.navigation.index == 1 and not shade.isVisible(), "gamepad navigation retained the closing modal"
        if not reduced:
            controller.consoleAppAction("motion.0", "details")
            QTest.qWait(180)
            controller.dispatch("back")
            application.processEvents()
            os.environ["UDECK_REDUCED_MOTION"] = "1"
            controller._publish()
            application.processEvents()
            assert not shade.isVisible(), "reducing motion did not finish the closing modal"
            os.environ["UDECK_REDUCED_MOTION"] = "0"
            controller._publish()
            application.processEvents()

        controller.setPage("home")
        controller.select(1)
        QTest.qWait(180)
        selected = controller._items()[1]
        now = [0.0]
        controller.launches.clock = lambda: now[0]
        token, _created = controller.launches.begin(selected, observable=True)
        controller._refresh_launch()
        controller._publish()
        application.processEvents()
        assert not visual("appLaunchOverlay").property("shown")
        assert visual("homeTile-1").property("launchPending"), "no local feedback before loading overlay"
        assert "Opening" in visual("homeSelectedDescription").property("text")
        controller.launches.finish(token)
        controller._refresh_launch()
        controller._publish()
        application.processEvents()
        assert not visual("homeTile-1").property("launchPending")
        assert not errors, errors
        window.grabWindow().save(str(output / "motion.png"))
        print(json.dumps({"qmlErrors": errors, "focusRetargeted": True, "dialogInputIsolated": True,
                          "launchImmediate": True, "pageDelegatesRetained": True, "reducedMotion": reduced}))
    finally:
        delete(engine)
        controller.close()
        application.processEvents()


if __name__ == "__main__":
    run()
