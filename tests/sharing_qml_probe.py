"""Exercise Sharing menus through a real QQuickWindow with isolated settings."""

import argparse
import json
import tempfile
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine, QQmlEngine, QQmlExpression
from PySide6.QtTest import QTest
from shiboken6 import delete

from udeck import main
from udeck.controller import ShellController
from udeck.core import ConfigStore
from udeck.mock import MockBackend


def run():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--language", default="zh_CN")
    parser.add_argument("--theme", default="classic")
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    app = QGuiApplication([])
    temporary = tempfile.TemporaryDirectory(prefix="udeck-sharing-ui-")
    controller = ShellController(MockBackend(), config=ConfigStore(Path(temporary.name) / "settings.json"), mock=True)
    controller.setLanguage(args.language)
    controller.setTheme(args.theme)
    controller.setPage("settings")
    candidates = [{"key": f"test-{i}", "name": "家庭网络 Home network " + str(i), "addresses": ["192.0.2." + str(i + 1)]} for i in range(12)]
    for protocol in ("web", "smb"):
        state = {**controller._shares[protocol]["state"], "candidates": candidates}
        controller._sharing_result((protocol, "status", state, ""))
    errors, captures = [], []
    engine = QQmlApplicationEngine()
    engine.warnings.connect(lambda messages: errors.extend(item.toString() for item in messages))
    engine.addImageProvider("desktop", main.IconProvider())
    for name, value in (("controller", controller), ("windowedPreview", True), ("headlessPreview", True)):
        engine.rootContext().setContextProperty(name, value)
    engine.load(QUrl.fromLocalFile(str(Path(main.__file__).parent / "qml/Main.qml")))
    assert engine.rootObjects(), errors
    window = engine.rootObjects()[0]
    window.setWidth(args.width)
    window.setHeight(args.height)
    window.requestActivate()
    QTest.qWait(150)

    def capture(name):
        QTest.qWait(150)
        expression = QQmlExpression(QQmlEngine.contextForObject(window), window, """
            JSON.stringify((function() {
                const out = {rows: [], icons: [], selected: null}
                function rect(item) {
                    const p = item.mapToItem(contentItem, 0, 0)
                    return {x:p.x, y:p.y, w:item.width, h:item.height}
                }
                function visit(item) {
                    if (!item.visible) return
                    if (item.objectName === 'dialogPanel') out.panel = rect(item)
                    if (item.objectName === 'menuList') out.list = Object.assign(rect(item), {offset:item.contentY})
                    if (item.objectName === 'settingOptionRow') {
                        const row = Object.assign(rect(item), {index:item.index, single:item.singleLine, toggle:item.toggle})
                        out.rows.push(row)
                        if (item.index === viewState.modal.index) out.selected = row
                    }
                    if (item.objectName === 'settingOptionIcon') out.icons.push(item.status)
                    for (const child of item.children) visit(child)
                }
                visit(contentItem)
                return out
            })())
        """)
        value, undefined = expression.evaluate()
        assert not undefined and not expression.hasError(), expression.error().toString()
        data = json.loads(value)
        panel, listing, selected = data["panel"], data["list"], data["selected"]
        assert panel["x"] >= 32 and panel["y"] >= 31, data
        assert panel["x"] + panel["w"] <= window.width() - 31, data
        assert panel["y"] + panel["h"] <= window.height() - 31, data
        assert listing["h"] >= 60 and listing["y"] + listing["h"] <= panel["y"] + panel["h"], data
        assert selected is not None and selected["y"] >= listing["y"] - 1, data
        assert selected["y"] + selected["h"] <= listing["y"] + listing["h"] + 1, data
        assert all(row["single"] for row in data["rows"]), data
        assert all(status == 1 for status in data["icons"]), data
        assert window.grabWindow().save(str(args.output / (name + ".png")))
        captures.append({"name": name, "source": controller.modal["source"], "index": controller.modal["index"], **data})

    try:
        controller.activateSetting("sharing")
        capture("sharing")
        controller.chooseModal(0)
        capture("web-off")
        controller.dispatch("back")
        controller.chooseModal(1)
        capture("smb-off")
        controller.chooseModal(2)
        key = controller.modal["key"]
        controller.chooseModal(0)
        assert controller.modal["key"] == key and controller.modal["index"] == 0
        for _ in range(12):
            QTest.keyClick(window, Qt.Key_Down)
        assert controller.modal["index"] == 12
        capture("networks-scroll-end")
        QTest.keyClick(window, Qt.Key_Return)
        assert controller.modal["source"] == "sharing-smb" and controller.modal["index"] == 2
        controller.smb_draft["root"] = temporary.name
        controller._sharing_refresh()
        controller.chooseModal(0)
        assert controller.smb_access["enabled"] and not controller.network_access["enabled"]
        capture("smb-on")
        key = controller.modal["key"]
        controller._shares["smb"].update(pending=True, busy=True)
        controller._sharing_refresh()
        controller._publish()
        capture("smb-applying")
        controller._sharing_result(("smb", "start", {**controller.smb_access, "state": "waiting", "urls": []}, "TCP port 445 is already in use"))
        assert controller.modal["key"] == key and controller.modal["index"] == 0
        capture("smb-error")
        controller.chooseModal(0)
        assert not controller.smb_access["enabled"]
        controller.dispatch("back")
        assert controller.modal["source"] == "sharing" and controller.modal["index"] == 1
        capture("sharing-return")
        assert not errors, errors
        report = {"passed": True, "language": args.language, "theme": args.theme, "size": [args.width, args.height], "captures": captures, "warnings": errors}
        (args.output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    finally:
        window.close()
        delete(engine)
        controller.close()
        app.processEvents()
        temporary.cleanup()


if __name__ == "__main__":
    run()
