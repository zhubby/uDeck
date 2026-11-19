"""
[INPUT]: 依赖真实桌面 QML、隔离后端与可控导航序列。
[OUTPUT]: 验证同步发布、初始几何、滚动改向与补位连续性。
[POS]: 独立进程探针；只操作临时配置与测试窗口。
[PROTOCOL]: Update this header on change, then check AGENTS.md
"""

import json
import os
import shutil
import sys
import time
from pathlib import Path

from PySide6.QtCore import QPointF, Qt, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtTest import QTest
from shiboken6 import delete

from udeck import main
from udeck.controller import ShellController
from udeck.core import ConfigStore
from udeck.files import FileOperations
from udeck.mock import MockBackend


def visual(owner, name):
    pending = [owner.contentItem() if hasattr(owner, "contentItem") else owner]
    while pending:
        item = pending.pop()
        if item.objectName() == name:
            return item
        pending.extend(item.childItems())
    raise AssertionError(("missing visual", name))


def wait_for_initial_layout(window, application):
    previous = None
    stable_since = time.monotonic()
    deadline = stable_since + 5
    while time.monotonic() < deadline:
        application.processEvents()
        name = "itemList" if window.property("renderedPage") == "settings" else "homeStrip"
        strip = visual(window, name)
        item = strip.property("currentItem")
        signature = (window.width(), window.height(), strip.width(), strip.height(),
                     strip.property("contentX"), strip.property("contentY"),
                     strip.property("contentWidth"), strip.property("contentHeight"),
                     strip.property("currentIndex"), (item.x(), item.y()) if item else None)
        now = time.monotonic()
        if signature != previous:
            previous, stable_since = signature, now
        if strip.width() > 0 and strip.height() > 0 and item is not None and now - stable_since >= .15:
            return
        QTest.qWait(10)
    raise AssertionError(("初始布局没有稳定", previous))


def run():
    directory, case, theme = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
    directory.mkdir(parents=True, exist_ok=True)
    application = QGuiApplication([])
    controller = ShellController(MockBackend(), config=ConfigStore(directory / "settings.json"), mock=True)
    controller.setTheme(theme)
    if case == "settings-refresh":
        controller.setLanguage("en")
        controller.setPage("settings")
        controller.select(next(index for index, item in enumerate(controller._settings()) if item["id"] == "ui-sounds"))
    engine = QQmlApplicationEngine()
    errors = []
    engine.warnings.connect(lambda warnings: errors.extend(w.toString() for w in warnings))
    engine.addImageProvider("desktop", main.IconProvider())
    for key, value in (("controller", controller), ("windowedPreview", True), ("headlessPreview", True)):
        engine.rootContext().setContextProperty(key, value)
    qml = Path(os.environ.get("UDECK_CONTINUITY_BASELINE_QML", str(Path(main.__file__).parent / "qml")))
    if case == "files-layout":
        copied_qml = directory / "qml"
        shutil.copytree(qml, copied_qml)
        for name in ("fonts", "assets"):
            (directory / name).symlink_to(Path(main.__file__).parent / name, target_is_directory=True)
        source = (copied_qml / "FilesScreen.qml").read_text()
        source = source.replace("id: root", "id: root\n    property int observedLayouts: 0", 1)
        source = source.replace("fileGrid.forceLayout()", "root.observedLayouts++; fileGrid.forceLayout()")
        (copied_qml / "FilesScreen.qml").write_text(source)
        qml = copied_qml
    engine.load(QUrl.fromLocalFile(str(qml / "Main.qml")))
    assert engine.rootObjects(), errors
    window = engine.rootObjects()[0]
    fixture = None
    try:
        wait_for_initial_layout(window, application)
        if case == "publication":
            for page, surface_name, model_name in (("apps", "applicationGrid", "itemModel"), ("settings", "itemList", "settingsModel")):
                controller.setPage(page)
                assert window.property("renderedPage") == page, ("页面发布遗留到下一轮事件", page, window.property("renderedPage"))
                model = window.property(model_name).toVariant()
                assert len(model) == len(controller._items()), ("页面可见时模型未就绪", page, len(model))
                assert visual(window, surface_name).isVisible()
            controller.setPage("home")
            assert window.property("renderedPage") == "home"
            controller.dispatch("quick-settings")
            shade = visual(window, "modalShade")
            assert shade.property("shown") and shade.property("lastDialog") == controller.modal["key"], "弹窗显示和内容同步分属不同事件"
        elif case == "initial-geometry":
            engine.loadData(("""
                import QtQuick
                import "@SHARED@" as Shared
                Item {
                    width: 500; height: 200
                    property alias viewportWidth: listing.width
                    property alias scrollX: listing.contentX
                    ListView {
                        id: listing; width: -56; height: 100
                        orientation: ListView.Horizontal; spacing: 18
                        leftMargin: 12; rightMargin: 12
                        model: 7; currentIndex: 0
                        highlightFollowsCurrentItem: false
                        interactive: false; cacheBuffer: 1200
                        delegate: Item { width: 180; height: 100 }
                    }
                    Shared.SelectionViewport { view: listing }
                }
            """.replace("@SHARED@", QUrl.fromLocalFile(str(Path(main.__file__).parent / "qml")).toString())).encode(), QUrl())
            fixture = engine.rootObjects()[-1]
            QTest.qWait(40)
            assert abs(fixture.property("scrollX") + 12) < 0.1, ("布局未就绪时移动了滚动位置", fixture.property("scrollX"))
            fixture.setProperty("viewportWidth", 1190)
            QTest.qWait(40)
            assert abs(fixture.property("scrollX") + 12) < 0.1
        elif case == "page":
            controller.setPage("apps")
            QTest.qWait(180)
            controller.setPage("windows")
            application.processEvents()
            page = visual(window, "pageContent")
            assert page.opacity() == 1, "切页不应抹掉已替换的内容"
            start = page.property("offsetX")
            assert 0 < abs(start) <= 6.1
            QTest.qWait(35)
            before = page.property("offsetX")
            assert abs(before) < abs(start)
            controller.setPage("files")
            application.processEvents()
            assert 0 <= page.property("offsetX") <= before + 0.2, "连续切页重置了位移起点"
            assert page.opacity() == 1
            QTest.qWait(150)
            assert abs(page.property("offsetX")) < 0.1
            controller.setPage("windows")
            application.processEvents()
            assert page.property("offsetX") < 0, "反向切页未使用反向位移"
            QTest.qWait(30)
            before = page.property("offsetX")
            controller._publish()
            application.processEvents()
            assert before - 0.2 <= page.property("offsetX") <= 0, "同页刷新重播切页动画"
            QTest.qWait(150)
            assert abs(page.property("offsetX")) < 0.1
        elif case == "scroll":
            strip = visual(window, "homeStrip")
            initial = strip.property("contentX")
            scroll_changes = []
            strip.contentXChanged.connect(lambda: scroll_changes.append(strip.property("contentX")))
            controller.select(6)
            application.processEvents()
            assert controller.navigation.index == 6
            assert strip.property("contentX") < 189, ("选择移动直接跳到末端", initial, strip.property("contentX"), scroll_changes)
            QTest.qWait(30)
            before = strip.property("contentX")
            assert before > initial + 1
            controller.select(0)
            assert abs(strip.property("contentX") - before) < 1, "滚动改向未保留当前位置"
            application.processEvents()
            assert initial <= strip.property("contentX") <= before, (
                "滚动改向超出原区间", initial, before, strip.property("contentX"),
                {name: strip.property(name) for name in ("originX", "width", "contentWidth", "currentIndex", "moving")},
                [(child.metaObject().className(), child.property("animating"))
                 for child in strip.parentItem().childItems() if child.metaObject().indexOfProperty("animating") >= 0],
                scroll_changes,
            )
            QTest.qWait(140)
            assert abs(strip.property("contentX") - initial) < 1
            controller.select(2)
            application.processEvents()
            QTest.qWait(35)
            assert abs(strip.property("contentX") - initial) < 1, "安全区内选择触发滚动"
            controller.select(6)
            QTest.qWait(25)
            os.environ["UDECK_REDUCED_MOTION"] = "1"
            controller._publish()
            application.processEvents()
            assert abs(strip.property("contentX") - 190) < 1, "减少动画未立即结束滚动"
            QTest.qWait(100)
            assert abs(strip.property("contentX") - 190) < 1
        elif case == "settings-refresh":
            position = next(index for index, item in enumerate(controller._settings()) if item["id"] == "ui-sounds")
            listing = visual(window, "itemList")
            before = listing.property("contentY")
            start = listing.property("currentItem").mapToItem(listing, QPointF()).y()
            initial_geometry = (before, listing.property("originY"), start)
            QTest.keyClick(window, Qt.Key_Return)
            QTest.qWait(160)
            selected = listing.property("currentItem")
            assert selected is not None and controller.navigation.index == position
            assert listing.property("currentIndex") == position, (
                "设置模型刷新重置视图选择", listing.property("currentIndex"), position,
                selected.property("index"), selected.y(), listing.property("contentY"),
            )
            point = selected.mapToItem(listing, QPointF())
            assert point.y() >= -1 and point.y() + selected.height() <= listing.height() + 1, (
                "设置值刷新后选中项离开视口", before, listing.property("contentY"),
                listing.property("originY"), selected.y(), point.y(), selected.height(), listing.height(),
            )
            assert abs(point.y() - start) < 1, (
                "同尺寸设置刷新改变选中项位置", initial_geometry,
                listing.property("contentY"), listing.property("originY"), point.y(),
            )
            children, texts = [selected], []
            while children:
                child = children.pop()
                texts.append(child.property("text"))
                children.extend(child.childItems())
            assert "Off" in texts, "设置行未显示刷新后的值"
            QTest.keyClick(window, Qt.Key_Down)
            QTest.qWait(140)
            assert listing.property("currentIndex") == position + 1, "模型刷新后选择绑定失效"
        elif case == "focus":
            engine.loadData(("""
                import QtQuick
                import "@SHARED@" as Shared
                Item {
                    width: 500; height: 200
                    property bool second: false
                    property bool reduce: false
                    Rectangle { id: first; width: 80; height: 60 }
                    Rectangle { id: next; x: 180; y: 80; width: 170; height: 90 }
                    Shared.FocusFrame {
                        objectName: "fixtureFocus"
                        target: parent.second ? next : first
                        accent: "red"; reducedMotion: parent.reduce
                    }
                }
            """.replace("@SHARED@", QUrl.fromLocalFile(str(Path(main.__file__).parent / "qml")).toString())).encode(), QUrl())
            assert len(engine.rootObjects()) == 2, errors
            fixture = engine.rootObjects()[-1]
            QTest.qWait(30)
            focus = visual(fixture, "fixtureFocus")
            fixture.setProperty("second", True)
            application.processEvents()
            assert abs(focus.width() - 80) < 1, "焦点尺寸直接跳到新代理"
            QTest.qWait(35)
            assert 80 < focus.width() < 170
            before = focus.width()
            fixture.setProperty("second", False)
            assert abs(focus.width() - before) < 1
            application.processEvents()
            assert 80 < focus.width() <= before
            fixture.setProperty("reduce", True)
            application.processEvents()
            assert abs(focus.x()) < 0.1 and abs(focus.width() - 80) < 0.1
        elif case in ("files-layout", "files-scroll", "files-task"):
            folder = directory / "files"
            folder.mkdir()
            for index in range(40):
                (folder / f"file-{index:02}.txt").write_text("test")
            controller._browse(folder)
            controller.data["files"] = FileOperations().list_directory(folder)
            controller._publish()
            controller.setPage("files")
            controller.select(0)
            QTest.qWait(220)
            screen = visual(window, "filesScreen")
            grid = visual(window, "fileGrid")
            if case == "files-layout":
                before = screen.property("observedLayouts")
                for index in (1, 2, 3, 4):
                    controller.select(index)
                    application.processEvents()
                QTest.qWait(120)
                assert screen.property("observedLayouts") == before, "普通文件选择强制布局"
                controller.setPage("home")
                application.processEvents()
                QTest.qWait(180)
                assert screen.property("observedLayouts") == before, "隐藏文件页仍强制布局"
            elif case == "files-scroll":
                initial = grid.property("contentY")
                controller.select(10)
                application.processEvents()
                first = grid.property("contentY")
                QTest.qWait(140)
                final = grid.property("contentY")
                assert initial <= first < final - 1, ("文件网格跨行直接跳到目标", initial, first, final)
                controller.select(0)
                application.processEvents()
                QTest.qWait(140)
                assert abs(grid.property("contentY") - initial) < 1
                controller.select(10)
                QTest.qWait(25)
                controller.setPage("home")
                application.processEvents()
                stopped = grid.property("contentY")
                QTest.qWait(130)
                assert abs(grid.property("contentY") - stopped) < 0.1, "隐藏视口仍继续滚动"
                controller.setPage("files")
                QTest.qWait(150)
                controller.select(39)
                application.processEvents()
                QTest.qWait(140)
                last = grid.property("currentItem")
                assert last is not None, "未实例化的远端选择没有定位"
                position = last.mapToItem(grid, QPointF())
                assert position.y() >= -1
                assert position.y() + last.height() <= grid.height() + 1
            else:
                before = grid.property("cellHeight")
                selected = controller._file_current()["id"]
                controller.file_task = {"state": "running", "phase": "running", "summary": "Copying"}
                controller._publish()
                application.processEvents()
                QTest.qWait(140)
                assert grid.property("cellHeight") == before, "任务条出现导致网格重新缩放"
                assert controller._file_current()["id"] == selected
        elif case == "console":
            controller._windows_changed([{"id": str(i), "appId": "continuity." + str(i), "name": "App " + str(i)} for i in range(5)])
            controller.runtime_console.timer.stop()
            controller.setPage("windows")
            controller.select(1)
            QTest.qWait(200)
            rows = list(controller.consoleModel.rows)
            target = visual(window, "consoleRow-" + rows[1]["applicationKey"])
            controller.consoleModel.update(rows[1:])
            controller.select(0)
            application.processEvents()
            QTest.qWait(25)
            listing = visual(window, "consoleList")
            focus = visual(window, "consoleFocus")
            target_y = target.mapToItem(listing.property("contentItem"), QPointF()).y()
            assert abs(focus.y() - target_y) < 1, ("补位中的焦点与实际行脱节", focus.y(), target_y)
            QTest.qWait(160)
            assert abs(focus.y() - target.y()) < 0.1
        else:
            raise AssertionError(case)
        assert not errors, errors
        print(json.dumps({"case": case, "status": "passed", "qmlErrors": errors}))
    finally:
        if fixture is not None and case == "focus":
            visual(fixture, "fixtureFocus").setProperty("target", None)
        delete(engine)
        controller.close()
        application.processEvents()


if __name__ == "__main__":
    run()
