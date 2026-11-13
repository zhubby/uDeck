import argparse
import json
import os
import time
from pathlib import Path

from PySide6.QtCore import QEventLoop, QObject, Qt, QTimer, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtTest import QTest
from shiboken6 import delete

from udeck import main
from udeck.controller import ShellController
from udeck.core import ConfigStore
from udeck.mock import MockBackend


def wait_until(predicate):
    deadline = time.monotonic() + 3
    while not predicate() and time.monotonic() < deadline:
        loop = QEventLoop()
        QTimer.singleShot(10, loop.quit)
        loop.exec()
    assert predicate()


def run():
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--language", default="en")
    parser.add_argument("--theme", default="classic")
    parser.add_argument("--reduced-motion", action="store_true")
    options = parser.parse_args()
    os.environ["UDECK_REDUCED_MOTION"] = "1" if options.reduced_motion else "0"
    application = QGuiApplication([])
    options.output.mkdir(parents=True, exist_ok=True)
    config = ConfigStore(options.output / "settings.json")
    config.data["preferences"].update(language=options.language, theme=options.theme)
    controller = ShellController(MockBackend(), config=config, mock=True, defer_startup=True)
    engine = QQmlApplicationEngine()
    errors, captures = [], []
    engine.warnings.connect(lambda warnings: errors.extend(warning.toString() for warning in warnings))
    engine.addImageProvider("desktop", main.IconProvider())
    engine.rootContext().setContextProperty("controller", controller)
    engine.rootContext().setContextProperty("windowedPreview", True)
    engine.rootContext().setContextProperty("headlessPreview", True)
    engine.load(QUrl.fromLocalFile(str(Path(main.__file__).parent / "qml/Main.qml")))
    assert engine.rootObjects(), errors
    window = engine.rootObjects()[0]
    window.setWidth(options.width)
    window.setHeight(options.height)

    def item(name):
        result = window.findChild(QObject, name)
        assert result is not None, name
        return result

    def capture(name):
        image = window.grabWindow()
        assert not image.isNull()
        assert image.width() == options.width and image.height() == options.height
        assert image.save(str(options.output / (name + ".png")))
        captures.append(name)

    try:
        QTest.qWait(200)
        startup = item("startupOverlay")
        overlay = item("appLaunchOverlay")
        assert startup.property("shown")
        assert startup.property("brand")
        assert startup.property("animationRunning") != options.reduced_motion
        assert not overlay.property("shown")
        capture("startup")
        controller.startupFrameSwapped()
        for _attempt in range(100):
            QTest.qWait(10)
            if controller.startup["phase"] == "ready":
                break
        assert controller.startup["active"]
        controller.startupFrameSwapped()
        wait_until(lambda: not startup.property("visible"))
        assert not startup.property("visible")
        assert not startup.property("animationRunning")

        controller.setPage("home")
        controller.select(1)
        selected = controller._items()[1]
        now = [0.0]
        controller.launches.clock = lambda: now[0]
        token, _created = controller.launches.begin(selected, observable=True)
        controller._refresh_launch()
        controller._publish()
        QTest.qWait(30)
        assert not overlay.property("shown")
        now[0] = 0.3
        controller._advance_launches()
        QTest.qWait(190)
        assert overlay.property("shown")
        assert overlay.property("animationRunning") != options.reduced_motion
        assert item("appLaunchOverlay").property("applicationName") == controller.translate(selected["name"], options.language)
        panel = overlay.findChild(QObject, "loadingPanel")
        assert panel.width() == 392
        assert panel.height() == 280
        capture("launch")
        segment = overlay.findChild(QObject, "loadingSegment")
        before = segment.x()
        QTest.qWait(140)
        after = segment.x()
        assert (abs(before - after) < 0.1) if options.reduced_motion else (abs(before - after) > 0.1)
        now[0] = 8.1
        controller._advance_launches()
        QTest.qWait(30)
        expected = "仍在等待应用窗口…" if options.language == "zh_CN" else "Still waiting for the application window…"
        assert overlay.property("message") == expected
        capture("launch-slow")

        QTest.keyClick(window, Qt.Key.Key_Right)
        assert controller.navigation.index == 1
        QTest.keyClick(window, Qt.Key.Key_Escape)
        wait_until(lambda: not overlay.property("visible"))
        assert not overlay.property("visible")
        assert not overlay.property("animationRunning")
        assert controller.navigation.index == 1
        assert controller.navigation.page == "home"
        controller.launches.finish(token)
        QTest.keyClick(window, Qt.Key.Key_Right)
        assert controller.navigation.index == 2
        capture("returned")
        assert not errors, errors
        print(json.dumps({"qmlErrors": errors, "captures": captures, "focusRestored": True}))
    finally:
        delete(engine)
        controller.close()
        application.processEvents()


if __name__ == "__main__":
    run()
