"""
[INPUT]: 依赖真实桌面 QML 与隔离的 Console 预览模型。
[OUTPUT]: 输出行密度、实时详情、鼠标与按键交互和 QML 错误。
[POS]: Console 视图的独立进程验收探针。
[PROTOCOL]: Update this header on change, then check AGENTS.md
"""

import json
import sys
from pathlib import Path

from PySide6.QtCore import QObject, QPointF, Qt, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtTest import QTest
from shiboken6 import delete

from udeck import main
from udeck.controller import ShellController
from udeck.core import ConfigStore
from udeck.mock import MockBackend

application = QGuiApplication([])
controller = ShellController(MockBackend(), config=ConfigStore(Path(sys.argv[1])), mock=True)
controller.setLanguage(sys.argv[2])
controller.setTheme(sys.argv[3])
names = ["Terminal", "Music", "Video", "Browser", "Reader", "Emulator", "Editor", "Monitor", "Long application name " * 5]
controller._windows_changed([{"id": str(i), "appId": "io.github.zhubby.uDeck." + str(i),
                              "name": name, "icon": "utilities-terminal", "active": False} for i, name in enumerate(names)])
controller.setPage("windows")
# 固定预览采样时钟；探针显式提交指标，避免定时样例覆盖断言。
controller.runtime_console.timer.stop()
engine = QQmlApplicationEngine()
errors = []
engine.warnings.connect(lambda warnings: errors.extend(warning.toString() for warning in warnings))
engine.addImageProvider("desktop", main.IconProvider())
context = engine.rootContext()
context.setContextProperty("controller", controller)
context.setContextProperty("appFont", application.font().family())
context.setContextProperty("windowedPreview", True)
context.setContextProperty("headlessPreview", True)
engine.load(QUrl.fromLocalFile(str(Path(main.__file__).parent / "qml/Main.qml")))
assert engine.rootObjects(), errors
window = engine.rootObjects()[0]
window.setWidth(int(sys.argv[4]))
window.setHeight(int(sys.argv[5]))
QTest.qWait(100)
screen = window.findChild(QObject, "consoleScreen")
view = window.findChild(QObject, "consoleList")
def visual_items(item):
    yield item
    for child in item.childItems():
        yield from visual_items(child)

rows = [item for item in visual_items(window.contentItem()) if item.objectName().startswith("consoleRow-")]
heights = [row.property("height") for row in rows]
controller.select(8)
QTest.qWait(80)
before = view.property("contentY")
data = [dict(row, cpuPercent=42.3) for row in controller.runtime_console.model.rows]
controller.runtime_console.model.update(data)
QTest.qWait(80)
after = view.property("contentY")
if len(sys.argv) > 6:
    window.grabWindow().save(sys.argv[6])
report = {"qmlErrors": errors, "heights": heights, "capacity": int(view.property("height") // 48),
          "scrollStable": before == after, "index": controller.navigation.index,
          "screenWidth": screen.property("width"), "title": json.loads(controller.snapshotJson)["title"]}


def visual(name):
    return next(item for item in visual_items(window.contentItem()) if item.objectName() == name)


def click(item, position=None):
    point = position or QPointF(item.width() / 2, item.height() / 2)
    QTest.mouseClick(window, Qt.LeftButton, pos=item.mapToScene(point).toPoint())
    QTest.qWait(30)


controller.select(0)
QTest.qWait(40)
exit_button = visual("consoleExit-io.github.zhubby.uDeck.0")
pointer_position = exit_button.mapToScene(QPointF(exit_button.width() / 2, exit_button.height() / 2))
QTest.mouseMove(window, pointer_position.toPoint())
QTest.qWait(40)
assert exit_button.property("hovered")
controller.select(8)
QTest.qWait(40)
old_button = next((item for item in visual_items(window.contentItem())
                   if item.objectName() == "consoleExit-io.github.zhubby.uDeck.0"), None)
assert old_button is None or not old_button.property("hovered"), "scrolled-out exit icon retains stale hover"
for item in visual_items(window.contentItem()):
    if item.objectName().startswith("consoleExit-"):
        position = item.mapFromScene(pointer_position)
        expected = 0 <= position.x() < item.width() and 0 <= position.y() < item.height()
        assert item.property("hovered") == expected, "stationary hover does not match the visible icon"
QTest.mouseMove(window, view.mapToScene(QPointF(view.width() - 52, -8)).toPoint())
QTest.qWait(40)
assert not any(item.property("hovered") for item in visual_items(window.contentItem())
               if item.objectName().startswith("consoleExit-")), "clipped exit icon hovers over the header"
report["hoverTracksScroll"] = True


controller.select(0)
QTest.qWait(40)
click(visual("consoleRow-io.github.zhubby.uDeck.0"), QPointF(80, 24))
assert controller.modal.get("kind") == "console-details", controller.modal
assert controller.runtime_console.details["applicationKey"] == "io.github.zhubby.uDeck.0"
QTest.keyClick(window, Qt.Key_Down)
QTest.qWait(30)
assert controller.modal["index"] == 2
controller.runtime_console.model.update([dict(row, cpuPercent=87.6, memoryBytes=912 * 1048576, uptimeSeconds=5432)
                                       if row["applicationKey"] == "io.github.zhubby.uDeck.0" else row
                                       for row in controller.runtime_console.model.rows])
controller.runtime_console.summaryChanged.emit()
QTest.qWait(30)
assert visual("consoleDetailsCpu").property("text") == "87.6%"
assert visual("consoleDetailsMemory").property("text") == "912 MiB"
assert visual("consoleDetailsUptime").property("text") == "01:30:32"
assert controller.modal["index"] == 2
panel = visual("dialogPanel")
content = visual("dialogContent")
assert content.y() + content.height() <= panel.height(), (content.height(), panel.height())
if len(sys.argv) > 7:
    assert window.grabWindow().save(sys.argv[7])
click(visual("consoleRow-io.github.zhubby.uDeck.1"), QPointF(2, 24))
assert controller.modal["kind"] == "console-details"
assert controller.runtime_console.details["applicationKey"] == "io.github.zhubby.uDeck.0"
QTest.keyClick(window, Qt.Key_Escape)
QTest.qWait(30)
assert not controller.modal and controller.navigation.index == 0
QTest.keyClick(window, Qt.Key_Return)
QTest.qWait(30)
assert controller.modal["kind"] == "console-details"
click(visual("consoleDetailsAction-2"))
assert controller.modal["kind"] == "confirm" and controller.modal["index"] == 0
click(visual("modalConfirm-0"))
assert controller.modal["kind"] == "console-details"
assert len(controller._items()) == 9
click(visual("consoleDetailsAction-3"))
assert not controller.modal
click(visual("consoleExit-io.github.zhubby.uDeck.1"))
assert len(controller._items()) == 8 and not controller.modal
assert controller.runtime_console.row("io.github.zhubby.uDeck.0")
assert not controller.runtime_console.row("io.github.zhubby.uDeck.1")
report["detailsMouseAndKeyboard"] = True
report["detailsLiveMetrics"] = True
report["detailsContained"] = True
report["scrimBlocksRows"] = True
window.close()
delete(engine)
controller.close()
print(json.dumps(report))
