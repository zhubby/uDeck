"""
[INPUT]: 依赖桌面和共享应用 QML、隔离控制器与本地封面。
[OUTPUT]: 验证增删补位、Toast 保留、封面和菜单连续输入。
[POS]: 完整动效的真实 Qt 探针，不连接用户应用或存档。
[PROTOCOL]: Update this header on change, then check AGENTS.md
"""

import json
import os
import sys
import time
from pathlib import Path

from PySide6.QtCore import QMetaObject, QPointF, Qt, QUrl
from PySide6.QtGui import QImage
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from shiboken6 import delete

from udeck import main
from udeck.apps.common.controller import AppController
from udeck.controller import ShellController
from udeck.core import ConfigStore
from udeck.mock import MockBackend


def visual(owner, name):
    pending = [owner.contentItem() if hasattr(owner, "contentItem") else owner]
    while pending:
        item = pending.pop()
        if item.objectName() == name:
            return item
        pending.extend(item.childItems())
    raise AssertionError(("missing visual", name))


def wait(predicate):
    deadline = time.monotonic() + 3
    while not predicate() and time.monotonic() < deadline:
        QTest.qWait(10)
    assert predicate()


class LibraryController(AppController):
    def create_library(self, app):
        return None

    def rows(self):
        return [{"id": str(i), "title": "Track " + str(i), "subtitle": "test"} for i in range(8)]


def run():
    root = Path(sys.argv[1])
    root.mkdir(parents=True, exist_ok=True)
    reduced = os.environ.get("UDECK_REDUCED_MOTION") == "1"
    application = QApplication([])
    errors, engines, windows = [], [], []
    config = ConfigStore(root / "settings.json")
    config.data["preferences"]["theme"] = sys.argv[2]
    config.save()
    shell = ShellController(MockBackend(), config=config, mock=True)
    app = LibraryController("music", root / "app-state", root / "settings.json")

    def load(controller, source, context):
        engine = QQmlApplicationEngine()
        engines.append(engine)
        engine.warnings.connect(lambda warnings: errors.extend(w.toString() for w in warnings))
        engine.addImageProvider("desktop", main.IconProvider())
        engine.rootContext().setContextProperty("controller", controller)
        for name, value in context.items():
            engine.rootContext().setContextProperty(name, value)
        engine.load(QUrl.fromLocalFile(str(Path(main.__file__).parent / source)))
        assert engine.rootObjects(), errors
        window = engine.rootObjects()[0]
        windows.append(window)
        QTest.qWait(200)
        return window, engine

    try:
        window, _ = load(shell, "qml/Main.qml", {"windowedPreview": True, "headlessPreview": True})
        shell.setPage("apps")
        application.processEvents()
        QTest.qWait(25)
        page = visual(window, "pageContent")
        if not reduced:
            assert page.property("offsetX") > 0
        QTest.qWait(180)
        assert abs(page.property("offsetX")) < 0.1
        shell.toast = "Saved"
        shell._publish()
        toast = visual(window, "shellToast")
        wait(lambda: toast.opacity() == 1)
        shell.toast = ""
        shell._publish()
        application.processEvents()
        if not reduced:
            assert toast.isVisible() and visual(toast, "toastMessage").property("text") == "Saved"
        QTest.qWait(160)
        assert not toast.isVisible()
        shell._windows_changed([{"id": str(i), "appId": "motion." + str(i), "name": "App " + str(i)} for i in range(3)])
        shell.runtime_console.timer.stop()
        shell.setPage("windows")
        QTest.qWait(200)
        rows = list(shell.consoleModel.rows)
        target = visual(window, "consoleRow-" + rows[1]["applicationKey"])
        listing = visual(window, "consoleList")
        def row_position():
            return target.mapToScene(QPointF()).y() - listing.mapToScene(QPointF()).y() + listing.property("contentY")
        before = row_position()
        shell.consoleModel.update(rows[1:])
        application.processEvents()
        if not reduced:
            target.setProperty("visualY", before)
            assert QMetaObject.invokeMethod(target, "positionRow")
            assert any(child.property("property") == "visualY" and child.property("running") for child in target.children())
            os.environ["UDECK_REDUCED_MOTION"] = "1"
            shell._publish()
            application.processEvents()
            QTest.qWait(20)
            assert abs(row_position()) < 0.1, "reducing motion did not finish row reflow"
            os.environ["UDECK_REDUCED_MOTION"] = "0"
            shell._publish()
        QTest.qWait(180)
        assert abs(row_position()) < 0.1

        app_window, engine = load(app, "apps/common/qml/Main.qml", {"windowed": True})
        app.select("0")
        QTest.qWait(120)
        app.select("2")
        application.processEvents()
        focus = visual(app_window, "appCardFocus")
        wait(lambda: abs(focus.x() - focus.property("target").x()) < 0.1)
        app.menu("Actions", [("One", lambda: None), ("Two", lambda: None)])
        QTest.qWait(180)
        modal = visual(app_window, "applicationModal")
        assert modal.isVisible()
        app.dispatch("back")
        application.processEvents()
        if not reduced:
            assert modal.isVisible()
            point = visual(app_window, "appCards").mapToScene(QPointF(30, 30))
            QTest.mouseClick(app_window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, point.toPoint())
            assert app.selected == "2"
        QTest.keyClick(app_window, Qt.Key.Key_Left)
        application.processEvents()
        assert app.selected == "1" and not modal.isVisible()
        app.notice = "Complete"
        app.publish()
        notice = visual(app_window, "appToast")
        wait(lambda: notice.opacity() == 1)
        app.notice = ""
        app.publish()
        application.processEvents()
        if not reduced:
            assert visual(notice, "toastMessage").property("text") == "Complete"
        app.notice = "Latest"
        app.publish()
        wait(lambda: notice.opacity() == 1)
        assert visual(notice, "toastMessage").property("text") == "Latest"

        cover = root / "cover.png"
        image = QImage(40, 40, QImage.Format.Format_RGB32)
        image.fill(Qt.GlobalColor.red)
        assert image.save(str(cover))
        art = visual(visual(app_window, "appCards").property("currentItem"), "cardArtwork")
        cover_image = visual(art, "coverImage")
        art.setProperty("cover", cover.as_uri())
        wait(lambda: cover_image.isVisible() and cover_image.property("paintedWidth") > 0)
        if not reduced:
            assert cover_image.opacity() < 1
            os.environ["UDECK_REDUCED_MOTION"] = "1"
            app.publish()
            application.processEvents()
            assert cover_image.opacity() == 1, "reducing motion did not finish the cover fade"
            os.environ["UDECK_REDUCED_MOTION"] = "0"
            app.publish()
        QTest.qWait(160)
        assert cover_image.opacity() == 1
        art.setProperty("cover", "")
        application.processEvents()
        assert not cover_image.isVisible()
        print(json.dumps({"qmlErrors": errors, "rowReflow": True, "toastRetained": True,
                          "coverReadyFade": True, "appInputImmediate": True, "reducedMotion": reduced}), flush=True)
    finally:
        for window in windows:
            window.hide()
        for engine in engines:
            delete(engine)
        app.close()
        shell.close()
        application.processEvents()


if __name__ == "__main__":
    run()
