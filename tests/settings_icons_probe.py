"""Capture settings and verify loaded, unclipped icons through actual Qt views."""

import argparse
import json
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PySide6.QtCore import QEvent, QUrl
from PySide6.QtQml import QQmlApplicationEngine, QQmlEngine, QQmlExpression
from PySide6.QtTest import QTest
from PySide6.QtWebEngineQuick import QtWebEngineQuick
from PySide6.QtWidgets import QApplication
from shiboken6 import delete

import udeck
from udeck.apps.runtime import make_controller
from udeck.controller import ShellController
from udeck.core import ConfigStore
from udeck.icons import IconProvider
from udeck.mock import MockBackend
from udeck.terminal.core import LaunchRequest, TerminalPreferences
from udeck.terminal.runtime import Coordinator


def run():
    parser = argparse.ArgumentParser()
    parser.add_argument("surface", choices=("system", "music", "video", "browser", "reader", "emulator", "terminal"))
    parser.add_argument("output", type=Path)
    parser.add_argument("--language", default="en")
    parser.add_argument("--theme", default="classic")
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    QtWebEngineQuick.initialize()
    application = QApplication([])
    errors, captures = [], []
    with tempfile.TemporaryDirectory(prefix="udeck-setting-icons-") as temporary:
        root = Path(temporary)
        config = ConfigStore(root / "settings.json")
        config.data["preferences"].update(language=args.language, theme=args.theme)
        config.save()
        coordinator = None
        if args.surface == "terminal":
            coordinator = Coordinator(application, SimpleNamespace(mock=True, no_input=True, windowed=True),
                                      TerminalPreferences(root / "terminal.json"), time.monotonic())
            coordinator.open(LaunchRequest(temporary, [], "", {}, True))
            engine = coordinator.engine
            window, controller = coordinator.recent["window"], coordinator.recent["controller"]
        else:
            with patch("pathlib.Path.home", return_value=root):
                controller = (ShellController(MockBackend(), config=config, mock=True) if args.surface == "system"
                              else make_controller(args.surface, root / "state", config.path))
            if args.surface != "system":
                controller.isolated = True
            engine = QQmlApplicationEngine()
            engine.addImageProvider("desktop", IconProvider())
            engine.warnings.connect(lambda warnings: errors.extend(w.toString() for w in warnings))
            context = engine.rootContext()
            context.setContextProperty("controller", controller)
            if args.surface == "system":
                context.setContextProperty("windowedPreview", True)
                context.setContextProperty("headlessPreview", True)
                qml = "qml/Main.qml"
            else:
                context.setContextProperty("windowed", True)
                qml = "apps/common/qml/Main.qml"
            engine.load(QUrl.fromLocalFile(str(Path(udeck.__file__).parent / qml)))
            assert engine.rootObjects(), errors
            window = engine.rootObjects()[0]
        window.setWidth(args.width)
        window.setHeight(args.height)
        window.show()

        def capture(name):
            QTest.qWait(120)
            expression = QQmlExpression(QQmlEngine.contextForObject(window), window, """
                JSON.stringify((function() {
                    const icons = []
                    function visit(item) {
                        if (!item.visible) return
                        if (item.objectName === 'settingOptionIcon' || item.objectName === 'systemSettingIcon') {
                            const p = item.mapToItem(contentItem, 0, 0)
                            let shown = true
                            for (let parent = item.parent; parent && parent !== contentItem; parent = parent.parent) {
                                if (parent.clip) {
                                    const r = item.mapToItem(parent, 0, 0)
                                    if (r.y < 0 || r.y + item.height > parent.height) shown = false
                                }
                            }
                            if (shown) {
                                const labels = []
                                function textBounds(parent) {
                                    for (const child of parent.children) {
                                        if (!child.visible) continue
                                        if (typeof child.text === 'string' && child.text && child.text !== '›') {
                                            const point = child.mapToItem(contentItem, 0, 0)
                                            labels.push({text: child.text, y: point.y, height: child.height,
                                                         lines: child.lineCount || 1})
                                        } else textBounds(child)
                                    }
                                }
                                textBounds(item.parent)
                                icons.push({source: item.source.toString(), status: item.status,
                                    x: p.x, y: p.y, width: item.width, height: item.height,
                                    labels: labels,
                                    textTop: Math.min(...labels.map(label => label.y)),
                                    textBottom: Math.max(...labels.map(label => label.y + label.height))})
                            }
                        }
                        for (const child of item.children) visit(child)
                    }
                    visit(contentItem)
                    return icons
                })())
            """)
            value, undefined = expression.evaluate()
            assert not undefined and not expression.hasError(), expression.error().toString()
            icons = json.loads(value)
            assert icons, name
            for icon in icons:
                assert icon["status"] == 1, (name, icon)
                assert icon["source"].startswith("image://desktop/"), icon
                assert 0 <= icon["x"] <= window.width() - icon["width"], icon
                assert 0 <= icon["y"] <= window.height() - icon["height"], icon
                assert icon["labels"], (name, "Missing option text", icon)
                assert abs(icon["height"] - (icon["textBottom"] - icon["textTop"])) <= 0.5, (name, icon)
                assert abs(icon["y"] - icon["textTop"]) <= 0.5, (name, icon)
                assert abs(icon["width"] - icon["height"]) <= 0.5, (name, icon)
            assert not errors, errors
            assert window.grabWindow().save(str(args.output / (name + ".png")))
            captures.append({"name": name, "icons": icons})

        def app_settings():
            controller.clear_menus()
            controller.command("settings")

        def open_app_option(label):
            controller.choose(next(i for i, row in enumerate(controller.menus[-1]["options"]) if row["title"] == label))

        try:
            if args.surface == "system":
                controller.setPage("settings")
                capture("settings")
                for item in ("language", "theme", "timezone", "wifi", "hotspot", "output", "microphone", "bluetooth", "volume"):
                    while controller.modal:
                        controller.dispatch("back")
                    controller.select(next(i for i, row in enumerate(controller._items()) if row["id"] == item))
                    controller.dispatch("accept")
                    capture(item)
                    if item in ("timezone", "wifi", "hotspot"):
                        if item != "timezone":
                            position = next(i for i, row in enumerate(controller.modal["options"]) if row.get("action") == item + "-device")
                            controller.modal["index"] = position
                        controller.dispatch("accept")
                        capture(item + "-detail")
                        if item == "wifi":
                            controller.data["wifi"]["devices"][0]["scanning"] = True
                            controller._refresh_open_menu()
                            controller._publish()
                            capture("wifi-refreshed")
                while controller.modal:
                    controller.dispatch("back")
                controller.dispatch("quick-settings")
                capture("quick-settings")
            elif args.surface == "terminal":
                controller.command("settings")
                capture("settings")
                old_size = controller.preferences.font_size
                controller.dispatch("down")
                controller.dispatch("accept")
                assert controller.preferences.font_size > old_size
            else:
                app_settings()
                capture("settings")
                if args.surface == "reader":
                    open_app_option("Reading layout")
                    capture("layout")
                    for label in ("Line spacing", "Font", "Content width", "Background"):
                        open_app_option(label)
                        capture(label.lower().replace(" ", "-"))
                        controller.dispatch("back")
                elif args.surface == "browser":
                    open_app_option("Page zoom: 100%")
                    capture("zoom")
                    controller.choose(3)
                    assert controller.zoom == 1.5
                    app_settings()
                    open_app_option("Interaction mode")
                    capture("interaction")
                elif args.surface == "emulator":
                    for label in ("ROM root", "Core management", "Create platform folders"):
                        app_settings()
                        open_app_option(label)
                        capture(label.lower().replace(" ", "-"))
                else:
                    open_app_option("Audio output")
                    capture("output")
                app_settings()
                # Scroll to the last settings item using the actual navigation path.
                for _ in range(len(controller.menus[-1]["options"]) - 1):
                    controller.dispatch("down")
                capture("settings-last")
            if coordinator:
                errors.extend(coordinator.errors)
            assert not errors, errors
            report = {"surface": args.surface, "language": args.language, "theme": args.theme,
                      "viewport": [args.width, args.height], "captures": captures, "qmlErrors": errors}
            (args.output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
            print(json.dumps({"surface": args.surface, "captures": len(captures), "qmlErrors": errors}))
        finally:
            if coordinator:
                coordinator.close()
                application.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            else:
                window.close()
                controller.close()
            delete(engine)
            application.processEvents()


if __name__ == "__main__":
    run()
