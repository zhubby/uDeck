import json
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")
os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")

from PySide6.QtCore import QCoreApplication, QEvent, QObject, QPointF, Qt, QUrl
from PySide6.QtGui import QColor, QGuiApplication, QImage
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtTest import QTest

from udeck import main
from udeck.controller import ShellController
from udeck.core import ConfigStore
from udeck.file_preview import preview
from udeck.files import file_kind
from udeck.mock import MockBackend

output = Path(sys.argv[1])
output.mkdir(parents=True, exist_ok=True)
language, theme, width, height = sys.argv[2], sys.argv[3], int(sys.argv[4]), int(sys.argv[5])
application = QGuiApplication([])
controller = ShellController(MockBackend(), config=ConfigStore(output / "settings.json"), mock=True)
controller.setLanguage(language)
controller.setTheme(theme)
for name in ("夜航 · Live.flac", "旅行纪录片.mp4", "掌机使用指南.epub", "长文件名称用于验证中文与英文混合排版 Notes.txt", "Photos.zip"):
    kind, mime, icon = file_kind(name)
    controller.data["files"].append({"id": "/home/demo/" + name, "path": "/home/demo/" + name,
                                     "name": name, "kind": kind, "mime": mime, "icon": icon,
                                     "directory": False, "size": 2400, "sizeLabel": "2.3 KiB",
                                     "modifiedLabel": "2026-11-08 20:00"})
controller.setPage("files")
controller.select(0)
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
window.setWidth(width)
window.setHeight(height)
QTest.qWait(180)
screen = window.findChild(QObject, "filesScreen")
assert screen is not None and screen.property("visible")
file_grid = window.findChild(QObject, "fileGrid")
assert file_grid is not None and file_grid.property("count") == len(controller.data["files"])
assert file_grid.property("height") >= 180
assert not file_grid.property("interactive")
assert file_grid.property("width") == screen.property("width")
columns = 5 if width == 1280 else 4
assert round(file_grid.property("width") / file_grid.property("cellWidth")) == columns
QTest.keyClick(window, Qt.Key.Key_Left)
QTest.qWait(20)
assert controller.navigation.index == 0 and controller.file_section == "list"
QTest.keyClick(window, Qt.Key.Key_Right)
assert controller.navigation.index == 1
QTest.keyClick(window, Qt.Key.Key_Down)
assert controller.navigation.index == (6 if width == 1280 else 5)
QTest.keyClick(window, Qt.Key.Key_Up)
assert controller.navigation.index == 1
QTest.keyClick(window, Qt.Key.Key_Up)
QTest.qWait(20)
assert json.loads(controller.viewSnapshotJson)["fileState"]["section"] == "breadcrumbs"
QTest.keyClick(window, Qt.Key.Key_Down)
controller.select(1)
QTest.qWait(80)
assert window.grabWindow().save(str(output / "files.png"))
controller.fileAction("selection", "")
QTest.keyClick(window, Qt.Key.Key_Return)
QTest.qWait(40)
assert json.loads(controller.viewSnapshotJson)["fileState"]["selectedCount"] == 1
selection_count = len(controller.file_marked)
assert window.grabWindow().save(str(output / "selection.png"))
selected = controller._file_current()["id"]
window.setWidth(960 if width == 1280 else 1280)
QTest.qWait(50)
QTest.keyClick(window, Qt.Key.Key_Down)
assert controller.navigation.index == (5 if width == 1280 else 6)
QTest.keyClick(window, Qt.Key.Key_Up)
assert controller._file_current()["id"] == selected
assert controller.file_marked == {selected}
window.setWidth(width)
QTest.qWait(50)
controller.select(10)
QTest.qWait(50)
last_row = (10 // columns) * file_grid.property("cellHeight")
assert file_grid.property("contentY") <= last_row
assert last_row + file_grid.property("cellHeight") <= file_grid.property("contentY") + file_grid.property("height") + 1
controller.select(1)
QTest.qWait(50)
controller.dispatch("context")
QTest.qWait(50)
panel = window.findChild(QObject, "dialogPanel")
assert panel.property("height") <= height - 60
assert window.grabWindow().save(str(output / "menu.png"))
controller.dispatch("accept")
QTest.qWait(50)
assert any(option.get("value") == "trash:///" for option in controller.modal["options"])
assert panel.property("height") <= height - 60
assert window.grabWindow().save(str(output / "locations.png"))
controller.dispatch("back")
controller.dispatch("back")
controller.network_access.update(enabled=True, state="running", networks=["home"], urls=["http://192.168.11.59:8787"])
controller.network_draft["networks"] = ["home"]
controller._network_menu()
QTest.qWait(60)
assert controller.modal["source"] == "network-access"
assert panel.property("height") <= height - 60
network_row = window.findChild(QObject, "menuList").property("currentItem")
network_icon = network_row.findChild(QObject, "settingOptionIcon")
network_label = network_row.findChild(QObject, "settingOptionLabel")
assert network_icon.property("height") > network_label.property("implicitHeight")
assert abs(network_icon.property("height") - network_label.parent().property("implicitHeight")) < 1
assert window.grabWindow().save(str(output / "network-access.png"))
controller.chooseModal(2)
QTest.qWait(30)
assert [row["value"] for row in controller.modal["options"]] == [0, 3600, 21600, 43200]
QTest.keyClick(window, Qt.Key.Key_Down)
QTest.keyClick(window, Qt.Key.Key_Return)
assert controller.network_draft["duration"] == 3600
assert controller.modal["source"] == "network-access"
controller.dispatch("back")
text_path = output / "preview.txt"
text_path.write_text("<b>Plain text, never HTML</b>\n" + "中文 English · Files preview\n" * 2500)
text_item = {"path": str(text_path), "name": text_path.name, "directory": False}

def show_preview(path, item):
    modal = {**preview(path), "item": item}
    if modal.get("previewType") == "image" and len(sys.argv) > 6 and sys.argv[6]:
        modal["previewImage"] = sys.argv[6]
    controller._push(modal)
    QTest.qWait(80)
    content = window.findChild(QObject, "dialogContent")
    assert content.property("height") + 40 <= panel.property("height") + 1
    details = window.findChild(QObject, "filePreviewDetails")
    metadata = [item for item in details.childItems() if item.objectName() == "filePreviewMetadata"]
    assert metadata
    assert all(label.property("paintedWidth") <= label.property("width") + 1 for label in metadata)

show_preview(text_path, text_item)
controller.dispatch("down")
QTest.qWait(30)
preview_content = window.findChild(QObject, "filePreviewContent")
assert preview_content.property("contentY") > 0
assert window.grabWindow().save(str(output / "preview-text.png"))
controller.dispatch("back")
show_preview(text_path, text_item)
assert preview_content.property("contentY") == 0
controller.dispatch("back")
image_path = output / "preview.png"
image = QImage(640, 320, QImage.Format.Format_RGB32)
image.fill(QColor("#EDB866"))
assert image.save(str(image_path))
show_preview(image_path, {"path": str(image_path), "name": image_path.name, "directory": False})
preview_image = window.findChild(QObject, "filePreviewImage")
deadline = time.monotonic() + 5
while preview_image.property("implicitWidth") <= 0 and time.monotonic() < deadline:
    QTest.qWait(10)
assert preview_image.property("implicitWidth") > 0, "Image preview did not load within 5 seconds"
assert preview_image.property("implicitHeight") > 0
hints = window.findChild(QObject, "modalFooter").property("hints").toVariant()
assert controller.translate(controller.messageKeys["SCROLL"], language) not in [hint["label"] for hint in hints]
assert window.grabWindow().save(str(output / "preview-image.png"))
controller.dispatch("back")
controller.file_task = {"id": "preview-task", "action": "copy", "state": "running", "phase": "working",
                        "sources": [str(text_path)], "directory": "/media/USB Drive/Backup", "current": str(text_path),
                        "doneBytes": 4194304, "totalBytes": 16777216, "doneFiles": 2, "totalFiles": 8,
                        "completedItems": 2, "skippedItems": 0, "speed": 1048576, "eta": 12}
controller._file_show_task()
QTest.qWait(80)
assert window.findChild(QObject, "fileTaskDetails").property("visible")
progress_fill = window.findChild(QObject, "fileProgressFill")
assert progress_fill is not None
assert abs(progress_fill.property("width") / progress_fill.parent().property("width") - 0.25) < 0.01
assert window.findChild(QObject, "dialogContent").property("height") + 40 <= panel.property("height") + 1
assert window.grabWindow().save(str(output / "transfer.png"))
controller.dispatch("back")
assert controller.file_task["state"] == "cancelling"
controller.dispatch("accept")
assert not controller.modal
controller.file_task = {}
controller._publish()
error_subtitle = "Permission denied; the source file is unchanged. " * 3
controller._menu("File task errors", [{"label": "unavailable.txt", "subtitle": error_subtitle, "wrapSubtitle": True, "action": "none"}])
QTest.qWait(30)
error_menu = window.findChild(QObject, "menuList")
error_row = error_menu.property("currentItem")
assert error_row is not None

def text_items(item):
    result = [item] if item.property("text") is not None else []
    for child in item.childItems():
        result.extend(text_items(child))
    return result

error_labels = text_items(error_row)
error_detail = next(label for label in error_labels if label.property("text") == error_subtitle)
assert error_detail.property("lineCount") == 2
for label in error_labels:
    top = label.mapToItem(error_menu, QPointF(0, 0)).y()
    assert top >= -1
    assert top + label.property("paintedHeight") <= error_menu.property("height") + 1
controller.dispatch("back")
QTest.qWait(30)
QTest.keyClick(window, Qt.Key.Key_F, Qt.KeyboardModifier.ControlModifier)
QTest.qWait(30)
assert controller.modal["purpose"] == "file-search"
QTest.keyClick(window, Qt.Key.Key_Escape)
QTest.qWait(30)
QTest.keyClick(window, Qt.Key.Key_L, Qt.KeyboardModifier.ControlModifier)
QTest.qWait(30)
assert controller.modal["purpose"] == "file-location"
QTest.keyClick(window, Qt.Key.Key_Escape)
QTest.qWait(30)
QTest.keyClick(window, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
assert len(controller.file_marked) == len(controller.data["files"])
QTest.keyClick(window, Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier)
assert len(controller.clipboard["paths"]) == len(controller.data["files"])
position = controller.navigation.index
QTest.keyClick(window, Qt.Key.Key_J)
assert controller.navigation.index == position
for confirm_key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
    controller.file_selection = False
    controller.file_marked.clear()
    controller._publish()
    QTest.keyClick(window, Qt.Key.Key_L, Qt.KeyboardModifier.ControlModifier)
    QTest.qWait(40)
    assert controller.modal.get("purpose") == "file-location"
    destination = "/TMP/ENTERED-FOLDER"
    QTest.keyClick(window, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
    for character in destination:
        QTest.keyClick(window, ord(character))
    assert controller.modal["text"] == destination, repr(controller.modal["text"])
    activated = []
    original_activate = controller._activate_file
    controller._activate_file = lambda item, activations=activated: activations.append(item["id"])
    QTest.keyClick(window, confirm_key)
    QTest.qWait(60)
    controller._activate_file = original_activate
    assert not controller.modal
    assert controller.data["directory"] == destination
    assert not activated, "The confirmation key also activated the underlying file"
assert not errors, errors
print(json.dumps({"theme": theme, "language": language, "size": [width, height],
                  "count": len(controller.data["files"]), "gridHeight": file_grid.property("height"),
                  "columns": columns,
                  "selectionCount": selection_count, "qmlErrors": errors}))
controller.close()
window.setVisible(False)
engine.deleteLater()
QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
