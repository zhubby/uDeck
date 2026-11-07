"""Inspect battery details rendered by the real launcher using safe fixture data."""

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
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--language", default="en")
    parser.add_argument("--theme", default="classic")
    options = parser.parse_args()
    options.output.mkdir(parents=True, exist_ok=True)
    application = QGuiApplication([])
    temporary = tempfile.TemporaryDirectory(prefix="udeck-battery-")
    controller = ShellController(MockBackend(), config=ConfigStore(Path(temporary.name) / "settings.json"), mock=True)
    controller.setLanguage(options.language)
    controller.setTheme(options.theme)
    controller.setPage("settings")
    position = next(i for i, item in enumerate(controller._items()) if item["id"] == "battery")
    controller.select(position)
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
    controller.dispatch("accept")
    owner = controller.modal["key"]
    reports = []

    def inspect():
        expression = QQmlExpression(QQmlEngine.contextForObject(window), window, """
            JSON.stringify((function() {
                const result = {labels: [], values: []}
                function visit(item) {
                    if (!item.visible) return
                    const p = item.mapToItem(contentItem, 0, 0)
                    const rect = {x: p.x, y: p.y, width: item.width, height: item.height}
                    if (item.objectName === 'dialogPanel') result.panel = rect
                    if (item.objectName === 'dialogContent') result.content = rect
                    if (item.objectName === 'batteryMetricLabel' || item.objectName === 'batteryMetricValue') {
                        const field = item.objectName === 'batteryMetricLabel' ? 'labels' : 'values'
                        result[field].push(Object.assign(rect, {text: item.text, truncated: item.truncated}))
                    }
                    for (const child of item.children) visit(child)
                }
                visit(contentItem)
                return result
            })())
        """)
        value, undefined = expression.evaluate()
        assert not undefined and not expression.hasError(), expression.error().toString()
        return json.loads(value)

    def capture(name, state, expected):
        controller.backend.updated.emit({"battery": state})
        QTest.qWait(100)
        assert controller.modal["key"] == owner
        report = inspect()
        assert [item["text"] for item in report["values"]] == expected, report
        assert len(report["labels"]) == 3, report
        for label, value in zip(report["labels"], report["values"], strict=True):
            assert not label["truncated"] and not value["truncated"], report
            assert label["x"] + label["width"] + 8 <= value["x"], report
        panel, content = report["panel"], report["content"]
        assert panel["x"] >= 32 and panel["y"] >= 32, report
        assert panel["x"] + panel["width"] <= window.width() - 32, report
        assert panel["y"] + panel["height"] <= window.height() - 32, report
        assert content["y"] + content["height"] <= panel["y"] + panel["height"], report
        assert window.grabWindow().save(str(options.output / f"{name}.png"))
        reports.append({"scenario": name, **report})

    base = {"available": True, "capacity": 83, "status": "Charging", "charging": True,
            "voltage": 3.9, "current": 1.2, "power": 4.68}
    unavailable = "Not available" if options.language == "en" else "不可用"
    try:
        capture("charging", base, ["4.68 W", "3.900 V", "1.200 A"])
        capture("low-current", {**base, "capacity": 100, "voltage": 4.206, "current": 0.017, "power": 0.071502},
                ["0.07 W", "4.206 V", "0.017 A"])
        capture("discharging", {**base, "status": "Discharging", "charging": False, "current": 0.8, "power": 3.12},
                ["3.12 W", "3.900 V", "0.800 A"])
        capture("full", {**base, "status": "Full", "charging": False, "current": 0, "power": 0},
                ["0.00 W", "3.900 V", "0.000 A"])
        capture("not-charging", {**base, "status": "Not charging", "charging": False, "current": None, "power": None},
                [unavailable, "3.900 V", unavailable])
        capture("unknown", {**base, "status": "Unknown", "charging": False}, ["4.68 W", "3.900 V", "1.200 A"])
        capture("no-sensors", {**base, "voltage": None, "current": None, "power": None}, [unavailable] * 3)
        capture("no-battery", {"available": False, "capacity": 0, "charging": False}, [unavailable] * 3)
        QTest.keyClick(window, Qt.Key_Escape)
        QTest.qWait(30)
        assert not controller.modal
        assert controller.navigation.page == "settings" and controller.navigation.index == position
        assert controller.backend.actions == []
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
