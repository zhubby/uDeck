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
from udeck.sounds import SOUND_FILES, InterfaceSounds


def run():
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--width", type=int, default=960)
    parser.add_argument("--height", type=int, default=600)
    parser.add_argument("--language", default="en")
    parser.add_argument("--theme", default="classic")
    options = parser.parse_args()
    options.output.mkdir(parents=True, exist_ok=True)
    application = QGuiApplication([])
    temporary = tempfile.TemporaryDirectory(prefix="udeck-sound-probe-")
    controller = ShellController(MockBackend(), config=ConfigStore(Path(temporary.name) / "settings.json"), mock=True)
    controller.setLanguage(options.language)
    controller.setTheme(options.theme)
    controller.setPage("settings")
    position = next(index for index, item in enumerate(controller._settings()) if item["id"] == "ui-sounds")
    controller.select(position)
    errors, events, captures = [], [], []
    controller.soundRequested.connect(events.append)
    engine = QQmlApplicationEngine()
    engine.warnings.connect(lambda warnings: errors.extend(warning.toString() for warning in warnings))
    engine.addImageProvider("desktop", main.IconProvider())
    for name, value in (("controller", controller), ("windowedPreview", True), ("headlessPreview", True)):
        engine.rootContext().setContextProperty(name, value)
    engine.load(QUrl.fromLocalFile(str(Path(main.__file__).parent / "qml/Main.qml")))
    assert engine.rootObjects(), errors
    window = engine.rootObjects()[0]
    window.setWidth(options.width)
    window.setHeight(options.height)
    sounds = InterfaceSounds(controller.config.path, window, silent=True)
    controller.soundRequested.connect(sounds.request)

    def capture(name):
        QTest.qWait(120)
        expression = QQmlExpression(QQmlEngine.contextForObject(window), window, """
            JSON.stringify((function() {
                const result = [];
                function visit(item) {
                    if (!item.visible) return;
                    const point = item.mapToItem(contentItem, 0, 0);
                    if (item.text && point.y >= 265 && point.y + item.height <= height - 85)
                        result.push({text: item.text, x: point.x, y: point.y,
                                     width: item.width, truncated: item.truncated === true});
                    for (const child of item.children) visit(child);
                }
                visit(contentItem);
                return result;
            })())
        """)
        value, undefined = expression.evaluate()
        assert not undefined and not expression.hasError(), expression.error().toString()
        labels = json.loads(value)
        title = "交互音效" if options.language == "zh_CN" else "Interface sounds"
        assert any(label["text"] == title and not label["truncated"] for label in labels), labels
        path = options.output / (name + ".png")
        assert window.grabWindow().save(str(path))
        captures.append(str(path))

    try:
        QTest.qWait(180)
        events.clear()
        capture("interface-sounds-on")
        QTest.keyClick(window, Qt.Key_Return)
        QTest.qWait(40)
        assert ConfigStore(controller.config.path).data["preferences"]["uiSounds"] is False
        assert events == ["toggle-off"], events
        capture("interface-sounds-off")
        QTest.keyClick(window, Qt.Key_Return)
        QTest.qWait(40)
        assert events[-1] == "toggle-on" and not controller.backend.actions
        controller.dispatch("quick-settings")
        controller.chooseModal(next(index for index, option in enumerate(controller.modal["options"])
                                    if option.get("id") == "ui-sounds"))
        assert controller.modal.get("source") == "quick-settings"
        assert not ConfigStore(controller.config.path).data["preferences"]["uiSounds"]
        assert not sounds._effects and not sounds._pending
        assert not errors, errors
        print(json.dumps({"captures": captures, "qmlErrors": errors, "events": events,
                          "playback": "silent headless preview", "samples": len(SOUND_FILES)}))
    finally:
        sounds.close()
        window.close()
        delete(engine)
        controller.close()
        application.processEvents()
        temporary.cleanup()


if __name__ == "__main__":
    run()
