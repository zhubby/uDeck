"""Exercise live radio status in the actual launcher, with safe fixture data."""

import argparse
import json
import tempfile
from copy import deepcopy
from pathlib import Path

from PySide6.QtCore import QPoint, QUrl
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
    parser.add_argument("--theme", default="dark")
    options = parser.parse_args()
    options.output.mkdir(parents=True, exist_ok=True)
    application = QGuiApplication([])
    temporary = tempfile.TemporaryDirectory(prefix="udeck-wireless-status-")
    controller = ShellController(MockBackend(), config=ConfigStore(Path(temporary.name) / "settings.json"), mock=True)
    controller.setLanguage(options.language)
    controller.setTheme(options.theme)
    controller.setPage("settings")
    controller.select(next(i for i, item in enumerate(controller._items()) if item["id"] == "theme"))
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
    base_wifi = deepcopy(controller.data["wifi"])
    reports = []
    pixel_counts = []

    def inspect():
        expression = QQmlExpression(QQmlEngine.contextForObject(window), window, """
            JSON.stringify((function() {
                const icons = [], header = [], tooltips = []
                function visit(item) {
                    if (!item.visible) return
                    const p = item.mapToItem(contentItem, 0, 0)
                    if (item.objectName === 'wirelessStatusIcon')
                        icons.push({kind: item.kind, deviceId: item.deviceId, status: item.status,
                            level: item.signalLevel, known: item.strengthKnown, description: item.description,
                            x: p.x, y: p.y, width: item.width, height: item.height})
                    if (item.text !== undefined && p.y < 80 && item.objectName !== 'wirelessStatusTooltipText') header.push(String(item.text))
                    if (item.objectName === 'wirelessStatusTooltipText')
                        tooltips.push({text: item.text, format: item.textFormat, x: p.x, y: p.y,
                                       width: item.width, height: item.height})
                    for (const child of item.children) visit(child)
                }
                visit(contentItem)
                return {icons, header, tooltips}
            })())
        """)
        result, undefined = expression.evaluate()
        assert not undefined and not expression.hasError(), expression.error().toString()
        return json.loads(result)

    def capture(name, wifi=None, bluetooth=True, bluetooth_available=True):
        controller.backend.updated.emit({"wifi": deepcopy(wifi if wifi is not None else base_wifi),
                                         "bluetooth": {"available": bluetooth_available, "powered": bluetooth}})
        QTest.qWait(120)
        report = inspect()
        if name == "long-tooltip":
            icon = report["icons"][0]
            QTest.mouseMove(window, QPoint(round(icon["x"] + 16), round(icon["y"] + 16)))
            QTest.qWait(650)
            report = inspect()
            assert len(report["tooltips"]) == 1, report
            tip = report["tooltips"][0]
            assert "<b>Workshop</b>" in tip["text"] and tip["format"] == 0, tip
            assert tip["x"] >= 0 and tip["x"] + tip["width"] <= window.width(), tip
            assert tip["y"] >= 0 and tip["y"] + tip["height"] <= window.height(), tip
        report["scenario"] = name
        expected = json.loads(controller.snapshotJson)["wifiIndicators"]
        radios = [item for item in report["icons"] if item["kind"] == "wifi" and item["deviceId"]]
        assert [item["deviceId"] for item in radios] == [item["id"] for item in expected], report
        for actual, wanted in zip(radios, expected, strict=True):
            assert actual["status"] == wanted["status"], report
            assert actual["level"] == wanted["level"], report
            assert actual["description"] == wanted["label"], report
        assert len([item for item in report["icons"] if item["kind"] == "bluetooth"]) == int(bluetooth and bluetooth_available), report
        assert not any("adapters" in text or "张网卡" in text for text in report["header"]), report
        ordered = sorted(report["icons"], key=lambda item: item["x"])
        for i, item in enumerate(ordered):
            assert item["x"] > 320 and item["y"] >= 0, report
            assert item["x"] + item["width"] <= window.width(), report
            assert item["y"] + item["height"] <= 70, report
            assert item["description"], report
            if i:
                assert item["x"] >= ordered[i - 1]["x"] + ordered[i - 1]["width"] + 8, report
        image = window.grabWindow()
        assert image.save(str(options.output / (name + ".png")))
        if name.startswith("level-"):
            icon = radios[0]
            ratio = image.width() / window.width()
            cropped = image.copy(round(icon["x"] * ratio), round(icon["y"] * ratio),
                                 round(icon["width"] * ratio), round(icon["height"] * ratio))
            # Independent pixel check: more lit segments must draw more text-color pixels.
            active = "#f5f2eb" if options.theme == "dark" else "#f1eee7"
            pixel_counts.append(sum(cropped.pixelColor(x, y).name() == active
                                    for y in range(cropped.height()) for x in range(cropped.width())))
        reports.append(report)

    try:
        capture("two-adapters")
        dual = deepcopy(base_wifi)
        dual["devices"][1].update({"deviceState": 100, "connected": "Workshop", "strength": 38})
        capture("both-connected", dual)
        for level, strength in enumerate((0, 12, 38, 63, 92)):
            wifi = deepcopy(base_wifi)
            wifi["devices"][0]["strength"] = strength
            capture(f"level-{level}", wifi)
        assert all(b > a for a, b in zip(pixel_counts, pixel_counts[1:], strict=False)), pixel_counts
        for name, update in (
            ("unknown-signal", {"strength": None}),
            ("connecting", {"deviceState": 60, "connected": "", "connecting": "Guest"}),
            ("unmanaged", {"managed": False}),
            ("read-error", {"available": False, "error": "Read failed"}),
        ):
            wifi = deepcopy(base_wifi)
            wifi["devices"][0].update(update)
            capture(name, wifi)
        wifi = deepcopy(base_wifi)
        wifi["enabled"] = False
        capture("all-wifi-off", wifi)
        wifi["devices"] = wifi["devices"][:1]
        capture("single-adapter", wifi)
        wifi["devices"] = []
        capture("no-adapters", wifi)
        capture("bluetooth-off", bluetooth=False)
        capture("bluetooth-unavailable", bluetooth_available=False)
        controller.busy = True
        controller.busy_label = "Long task status " * 30
        capture("busy")
        controller.busy = False
        wifi = deepcopy(base_wifi)
        wifi["devices"][0]["connected"] = "<b>Workshop</b> " + "longwifi-" * 30
        capture("long-tooltip", wifi)
        controller.dispatch("search")
        controller.editText("keep my input")
        key = controller.modal["key"]
        capture("live-update-with-input", dual)
        assert controller.modal["key"] == key
        assert controller.modal["text"] == "keep my input"
        assert controller.backend.actions == []
        assert not errors, errors
        print(json.dumps({"qmlErrors": errors, "scenarios": reports, "signalPixels": pixel_counts}))
    finally:
        window.close()
        delete(engine)
        controller.close()
        application.processEvents()
        temporary.cleanup()


if __name__ == "__main__":
    run()
