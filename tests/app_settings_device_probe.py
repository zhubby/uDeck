"""Exercise application settings on a real Wayland display with isolated state.

Usage: python3 tests/app_settings_device_probe.py APP OUTPUT LANGUAGE THEME WIDTH HEIGHT
Requires the installed native terminal plugin; never registers desktop IPC/input.
"""

import json
import os
import sys
import tempfile
import time
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from types import SimpleNamespace

from PySide6.QtCore import Q_RETURN_ARG, QMetaObject, QPoint, Qt, QUrl
from PySide6.QtQml import QQmlApplicationEngine, QQmlEngine, QQmlExpression
from PySide6.QtQuick import QQuickWindow
from PySide6.QtTest import QTest
from PySide6.QtWebEngineQuick import QtWebEngineQuick
from PySide6.QtWidgets import QApplication
from shiboken6 import delete

import udeck
from udeck.apps.emulator.catalog import probe_core
from udeck.apps.main import make_controller
from udeck.apps.media.engine import FrameImages
from udeck.apps.reader.controller import PdfImages
from udeck.core import ConfigStore
from udeck.icons import IconProvider
from udeck.terminal.core import LaunchRequest, TerminalPreferences
from udeck.terminal.runtime import Coordinator


def wait(predicate, seconds=20):
    deadline = time.monotonic() + seconds
    while not predicate() and time.monotonic() < deadline:
        QTest.qWait(25)
    assert predicate(), "Device settings probe timed out"


def web_values(window):
    # Traverse in QML: wrapping Chromium's private visual children in Python can
    # crash the installed PySide 6.8 bindings on arm64.
    expression = QQmlExpression(QQmlEngine.contextForObject(window), window, """
        JSON.stringify((function() {
            const found = []
            function visit(item) {
                if (typeof item.zoomFactor === 'number' && item.identifier)
                    found.push({id: item.identifier, url: item.url.toString(), zoom: item.zoomFactor})
                for (const child of item.children) visit(child)
            }
            visit(contentItem)
            return found
        })())
    """)
    value, undefined = expression.evaluate()
    assert not undefined and not expression.hasError(), expression.error().toString()
    return json.loads(value)


def rows(window):
    expression = QQmlExpression(QQmlEngine.contextForObject(window), window, """
        JSON.stringify((function() {
            const found = []
            function visit(item) {
                if (!item.visible) return
                if (item.objectName === 'settingOptionRow') {
                    let clipped = false
                    for (let p = item.parent; p; p = p.parent) {
                        const point = item.mapToItem(p, 0, 0)
                        if (p.clip && (point.y < -0.5 || point.y + item.height > p.height + 0.5)) clipped = true
                    }
                    if (!clipped) {
                        const pos = item.mapToItem(contentItem, 0, 0)
                        const entry = {title: item.option.title, checked: item.option.checked,
                            current: !!item.option.current, selected: item.selected,
                            x: pos.x, y: pos.y, width: item.width, height: item.height, parts: []}
                        function parts(parent) {
                            for (const child of parent.children) {
                                if (!child.visible) continue
                                if (['settingOptionIcon', 'settingOptionLabel', 'settingOptionStatus',
                                     'settingOptionSwitch', 'settingOptionChevron'].indexOf(child.objectName) >= 0) {
                                    const p = child.mapToItem(item, 0, 0)
                                    entry.parts.push({name: child.objectName, x: p.x, y: p.y,
                                        width: child.width, height: child.height, text: child.text || '',
                                        lines: child.lineCount || 1, status: child.status})
                                } else parts(child)
                            }
                        }
                        parts(item)
                        found.push(entry)
                    }
                }
                for (const child of item.children) visit(child)
            }
            visit(contentItem)
            return found
        })())
    """)
    value, undefined = expression.evaluate()
    assert not undefined and not expression.hasError(), expression.error().toString()
    result = json.loads(value)
    assert result, "No visible single-line setting rows"
    for row in result:
        parts = sorted(row["parts"], key=lambda part: part["x"])
        icon = next(part for part in parts if part["name"] == "settingOptionIcon")
        label = next(part for part in parts if part["name"] == "settingOptionLabel")
        assert icon["status"] == 1 and abs(icon["height"] - label["height"]) < 0.5, row
        assert all(part["lines"] == 1 and part["width"] > 0 for part in parts), row
        assert all(left["x"] + left["width"] <= right["x"] + 0.5
                   for left, right in zip(parts, parts[1:], strict=False)), row
        assert all(abs(part["y"] + part["height"] / 2 - row["height"] / 2) <= 0.5
                   for part in parts), row
    assert sum(row["selected"] for row in result) == 1, result
    return result


def run(name, output, language, theme, width, height):
    QtWebEngineQuick.initialize()
    qt = QApplication([])
    qt.setQuitOnLastWindowClosed(False)
    assert qt.platformName() == "wayland", qt.platformName()
    output.mkdir(parents=True, exist_ok=True)
    report = {"app": name, "language": language, "theme": theme,
              "platform": qt.platformName(), "viewport": [width, height],
              "source": str(Path(udeck.__file__).parent), "isolatedState": True,
              "mock": False, "checks": [], "captures": {}}
    with tempfile.TemporaryDirectory(prefix="udeck-settings-device-") as temporary:
        root = Path(temporary)
        config = ConfigStore(root / "settings.json")
        config.data["preferences"].update(language=language, theme=theme)
        config.save()
        coordinator, server = None, None
        if name == "terminal":
            coordinator = Coordinator(qt, SimpleNamespace(mock=False, no_input=True, windowed=True),
                                      TerminalPreferences(root / "terminal.json"), time.monotonic())
            coordinator.open(LaunchRequest(str(root), [sys.executable, "-u", "-c",
                "print('SETTINGS_PTY_READY'); import signal; signal.pause()"],
                "Settings device probe", dict(os.environ), True))
            controller, window = coordinator.recent["controller"], coordinator.recent["window"]
            engine, errors = coordinator.engine, coordinator.errors
            wait(lambda: bool(controller.native_sessions))
            session = next(iter(controller.native_sessions.values()))
            wait(lambda: "SETTINGS_PTY_READY" in session.property("history"))
            pid = QMetaObject.invokeMethod(session, "getShellPID", Q_RETURN_ARG(int))
            assert pid > 0
            controller.command("settings")
        else:
            controller = make_controller(name, root / "state", root / "settings.json")
            controller.isolated = True
            controller.poller.stop()
            engine, errors = QQmlApplicationEngine(), []
            engine.warnings.connect(lambda warnings: errors.extend(item.toString() for item in warnings))
            engine.addImageProvider("desktop", IconProvider())
            if name == "reader":
                engine.addImageProvider("pdf", PdfImages(controller))
            elif name in ("music", "video"):
                engine.addImageProvider("video", FrameImages(controller))
            engine.rootContext().setContextProperty("controller", controller)
            engine.rootContext().setContextProperty("windowed", True)
            controller.settings()
            engine.load(QUrl.fromLocalFile(str(Path(udeck.__file__).parent / "apps/common/qml/Main.qml")))
            assert engine.rootObjects(), errors
            window = engine.rootObjects()[0]
            controller.window = window
        assert isinstance(window, QQuickWindow)
        window.setWidth(width)
        window.setHeight(height)
        window.show()
        window.requestActivate()
        wait(window.isActive)
        QTest.qWait(500)

        def capture(label):
            QTest.qWait(150)
            assert window.grabWindow().save(str(output / (label + ".png")))
            report["captures"][label] = rows(window)

        def key(key):
            QTest.keyClick(window, key)
            QTest.qWait(120)

        def select(index):
            for _ in range(index - controller.menus[-1]["index"]):
                key(Qt.Key_Down)
            assert controller.menus[-1]["index"] == index

        def click_selected():
            selected = next(row for row in rows(window) if row["selected"])
            QTest.mouseClick(window, Qt.LeftButton, pos=QPoint(
                round(selected["x"] + selected["width"] / 2),
                round(selected["y"] + selected["height"] / 2)))
            QTest.qWait(180)

        try:
            capture("settings")
            report["checks"].append("single-line-icons-status-alignment")
            if name == "terminal":
                before = controller.preferences.font_size
                key(Qt.Key_Down)
                key(Qt.Key_Return)
                assert controller.preferences.font_size == before + 2
                capture("font-increased")
                key(Qt.Key_Up)
                key(Qt.Key_Return)
                assert controller.preferences.font_size == before
                key(Qt.Key_Escape)
                assert controller.mode == "input"
                assert next(iter(controller.native_sessions.values())) is session
                assert QMetaObject.invokeMethod(session, "getShellPID", Q_RETURN_ARG(int)) == pid
                assert "SETTINGS_PTY_READY" in session.property("history")
                report["ptyPid"] = pid
                report["checks"].append("native-pty-preserved-across-settings-and-font-changes")
            else:
                parent = controller.menus[-1]
                identifiers = [row["id"] for row in parent["options"]]
                if name in ("video", "reader"):
                    index = 1 if name == "video" else 0
                    select(index)
                    before = parent["options"][index]["checked"]
                    click_selected()
                    assert parent["options"][index]["checked"] is not before
                    assert controller.menus[-1] is parent and parent["index"] == index
                    capture("toggle-changed")
                    key(Qt.Key_Return)
                    assert parent["options"][index]["checked"] is before
                    assert [row["id"] for row in parent["options"]] == identifiers
                    report["checks"].append("mouse-and-enter-toggle-retain-menu-and-selection")
                if name in ("music", "video"):
                    parent["index"] = 0
                    controller.publish()
                    QTest.qWait(120)
                    key(Qt.Key_Return)
                    capture("audio-output")
                    key(Qt.Key_Return)
                    assert controller.menus[-1] is parent
                    assert parent["options"][0]["subtitle"] == controller.media.snapshot()["output"]
                    report["checks"].append("real-audio-output-selection-and-parent-value")
                elif name == "browser":
                    controller.clear_menus()
                    (root / "index.html").write_text("<title>Settings device page</title><p>Original device fixture</p>")
                    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(SimpleHTTPRequestHandler, directory=str(root)))
                    Thread(target=server.serve_forever, daemon=True).start()
                    controller.navigate(f"http://127.0.0.1:{server.server_port}/index.html")
                    wait(lambda: controller.active_tab().title == "Settings device page")
                    views = web_values(window)
                    assert views
                    tab = controller.active_tab()
                    controller.settings()
                    parent = controller.menus[-1]
                    key(Qt.Key_Return)
                    key(Qt.Key_Down)
                    key(Qt.Key_Down)
                    key(Qt.Key_Return)
                    assert parent["options"][0]["subtitle"] == "125%"
                    assert web_values(window)[0]["zoom"] == 1.25
                    capture("zoom-parent")
                    controller.clear_menus()
                    key(Qt.Key_F2)
                    select(5)
                    key(Qt.Key_Return)
                    capture("context-mode")
                    assert any(row["current"] for row in report["captures"]["context-mode"])
                    assert controller.active_tab() is tab
                    assert web_values(window)[0]["url"] == views[0]["url"]
                    report["checks"].append("native-webengine-zoom-and-context-mode-marker")
                elif name == "reader":
                    controller.clear_menus()
                    content = root / "books"
                    content.mkdir()
                    (content / "Original book.txt").write_text("Original device book\n\n" + "Reading layout 中文文本。\n\n" * 80)
                    controller.library.add(content)
                    wait(lambda: not controller.library.pending)
                    controller.open_item(controller.library.items[0]["id"])
                    wait(lambda: controller.reader_ready)
                    book = controller.book
                    key(Qt.Key_F2)
                    select(1)
                    key(Qt.Key_Return)
                    capture("context-layout")
                    key(Qt.Key_Return)
                    for _ in range(3):
                        key(Qt.Key_Down)
                    key(Qt.Key_Return)
                    assert controller.line_height == 1.8
                    assert controller.menus[-1]["options"][0]["subtitle"] == "1.8×"
                    assert controller.book is book and not book.closed and controller.reader_ready
                    capture("layout-parent")
                    report["checks"].append("real-book-context-layout-values-and-content-preserved")
                elif name == "emulator":
                    controller.clear_menus()
                    core = next(core for core in controller.catalog.cores.values() if core.id == "gambatte")
                    result = probe_core(core.path, timeout=20)
                    assert result["status"] == "available", result
                    controller.catalog.apply_probe(core.id, result)
                    controller.command("core-management")
                    controller.platform_cores_menu("gb")
                    controller.core_details(core.id, "gb")
                    capture("shortcut-core")
                    original = controller.menus[-1]["options"][0]["checked"]
                    click_selected()
                    assert controller.menus[-1]["options"][0]["checked"] is not original
                    capture("core-toggled")
                    key(Qt.Key_Return)
                    assert controller.menus[-1]["options"][0]["checked"] is original
                    report["checks"].append("installed-native-core-shortcut-switch-round-trip")
                controller.clear_menus()
                controller.settings()
                controller.publish()
                QTest.qWait(150)
                for _ in range(len(controller.menus[-1]["options"]) - 1):
                    key(Qt.Key_Down)
                capture("last-setting")
                key(Qt.Key_Escape)
                assert not controller.menus and not controller._callbacks
                report["checks"].append("last-row-visible-keyboard-back-and-callback-cleanup")
            assert not errors, errors
            report["qmlErrors"], report["passed"] = errors, True
        except BaseException as error:
            window.grabWindow().save(str(output / "failure.png"))
            report.update(passed=False, error=repr(error), qmlErrors=errors)
            raise
        finally:
            (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
            if server:
                server.shutdown()
                server.server_close()
            coordinator.close() if coordinator else controller.close()
            delete(engine)
    print(json.dumps({key: value for key, value in report.items() if key != "captures"}), flush=True)


if __name__ == "__main__":
    run(sys.argv[1], Path(sys.argv[2]), *sys.argv[3:5], *map(int, sys.argv[5:7]))
