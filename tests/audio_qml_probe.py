"""Exercise Bluetooth audio routing menus without changing real audio devices."""

import argparse
import json
import tempfile
from copy import deepcopy
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
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--language", default="en")
    parser.add_argument("--theme", default="classic")
    options = parser.parse_args()
    options.output.mkdir(parents=True, exist_ok=True)
    application = QGuiApplication([])
    temporary = tempfile.TemporaryDirectory(prefix="udeck-audio-")
    controller = ShellController(MockBackend(), config=ConfigStore(Path(temporary.name) / "settings.json"), mock=True)
    controller.setLanguage(options.language)
    controller.setTheme(options.theme)
    controller.setPage("settings")
    controller.select(next(i for i, item in enumerate(controller._items()) if item["id"] == "microphone"))
    engine = QQmlApplicationEngine()
    errors = []
    engine.warnings.connect(lambda warnings: errors.extend(w.toString() for w in warnings))
    engine.addImageProvider("desktop", main.IconProvider())
    context = engine.rootContext()
    for name, value in (("controller", controller), ("windowedPreview", True), ("headlessPreview", True)):
        context.setContextProperty(name, value)
    engine.load(QUrl.fromLocalFile(str(Path(main.__file__).parent / "qml/Main.qml")))
    assert engine.rootObjects(), errors
    window = engine.rootObjects()[0]
    window.setWidth(options.width)
    window.setHeight(options.height)
    reports = []

    def choose(identifier):
        controller.chooseModal(next(i for i, option in enumerate(controller.modal["options"]) if option.get("id") == identifier))

    def capture(name):
        QTest.qWait(100)
        expression = QQmlExpression(QQmlEngine.contextForObject(window), window, """
            JSON.stringify((function() {
                const result = {texts: []}
                function visit(item) {
                    if (!item.visible) return
                    const p = item.mapToItem(contentItem, 0, 0)
                    const rect = {x: p.x, y: p.y, width: item.width, height: item.height}
                    if (item.objectName === 'dialogPanel') result.panel = rect
                    if (item.objectName === 'dialogContent') result.content = rect
                    if (item.text !== undefined) result.texts.push(String(item.text))
                    for (const child of item.children) visit(child)
                }
                visit(contentItem)
                return result
            })())
        """)
        value, undefined = expression.evaluate()
        assert not undefined and not expression.hasError(), expression.error().toString()
        report = json.loads(value)
        panel, content = report["panel"], report["content"]
        assert panel["x"] >= 32 and panel["y"] >= 32, report
        assert panel["x"] + panel["width"] <= window.width() - 32, report
        assert panel["y"] + panel["height"] <= window.height() - 32, report
        assert content["y"] + content["height"] <= panel["y"] + panel["height"], report
        assert window.grabWindow().save(str(options.output / f"{name}.png"))
        reports.append({"scenario": name, **report})

    try:
        controller.activateSetting("output")
        key = controller.modal["key"]
        choose("headphones")
        assert controller.modal["key"] == key
        assert next(output for output in controller.data["audio"]["outputs"] if output["active"])["id"] == "headphones"
        capture("bluetooth-output")
        QTest.keyClick(window, Qt.Key_Escape)
        controller.dispatch("accept")
        assert controller.modal["source"] == "audio-input"
        key = controller.modal["key"]
        choose("headphones-microphone")
        assert controller.modal["key"] == key
        choose("input-mute")
        assert next(source for source in controller.data["audio"]["inputs"] if source["active"])["muted"]
        capture("bluetooth-microphone")
        choose("input-level")
        capture("microphone-level")
        QTest.keyClick(window, Qt.Key_Escape)
        assert controller.modal["source"] == "audio-input"
        choose("audio-modes")
        cards_key = controller.modal["key"]
        choose("headphones-card")
        capture("bluetooth-modes")
        choose("a2dp-sink")
        assert controller.modal["kind"] == "confirm" and controller.modal["index"] == 0
        capture("mode-confirmation")
        controller.backend.request("bluetooth_disconnect", {"id": "headphones"})
        assert controller.modal["key"] == cards_key
        capture("headset-disconnected")
        controller.dispatch("back")
        assert controller.modal["key"] == key
        audio = deepcopy(controller.backend.state["audio"])
        audio["inputs"] = []
        controller.backend.updated.emit({"audio": audio})
        capture("no-microphone")
        QTest.keyClick(window, Qt.Key_Escape)
        assert not controller.modal
        assert controller.navigation.page == "settings"
        assert controller._items()[controller.navigation.index]["id"] == "microphone"
        assert "audio_profile" not in controller.backend.actions
        assert not errors, errors
        print(json.dumps({"qmlErrors": errors, "scenarios": reports}))
    finally:
        window.close()
        delete(engine)
        controller.close()
        application.processEvents()
        temporary.cleanup()


if __name__ == "__main__":
    run()
