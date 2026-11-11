"""Exercise Browser input against a real WebEngine page at the selected zoom."""

import argparse
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QUrl, Slot
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow  # noqa: F401
from PySide6.QtTest import QTest
from PySide6.QtWebEngineQuick import QtWebEngineQuick
from PySide6.QtWidgets import QApplication
from shiboken6 import delete

from udeck.apps import common
from udeck.apps.browser.controller import BrowserController
from udeck.icons import IconProvider


class Results(QObject):
    value = None

    @Slot(str)
    def record(self, value):
        self.value = json.loads(value)


def run(output, zoom):
    output.mkdir(parents=True, exist_ok=True)
    requests = []

    class Page(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_GET(self):
            requests.append(self.path)
            text = """<!doctype html><meta charset="utf-8"><title>Browser input fixture</title>
                <style>body{margin:0;font:18px sans-serif}a,input{position:absolute;left:100px;
                width:160px;height:36px;box-sizing:border-box}a{top:70px}input{top:130px}</style>
                <main><a href="/reached">Open next page</a><form action="/submit">
                <input id="draft" name="draft" aria-label="Text input"></form></main>"""
            if self.path == "/reached":
                text = "<title>Destination reached</title><main>Navigation succeeded.</main>"
            data = text.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Page)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    QtWebEngineQuick.initialize()
    application = QApplication([])
    controller = BrowserController(output / "state", output / "settings.json")
    controller.isolated = True
    engine = QQmlApplicationEngine()
    engine.addImageProvider("desktop", IconProvider())
    errors = []
    engine.warnings.connect(lambda warnings: errors.extend(warning.toString() for warning in warnings))
    engine.rootContext().setContextProperty("controller", controller)
    engine.rootContext().setContextProperty("windowed", True)
    engine.load(QUrl.fromLocalFile(str(Path(common.__file__).parent / "qml/Main.qml")))
    assert engine.rootObjects(), errors
    window = engine.rootObjects()[0]
    controller.window = window
    window.show()
    window.requestActivate()
    results = Results()
    engine.globalObject().setProperty("probeResults", engine.newQObject(results))

    def wait(condition, seconds=8):
        deadline = time.monotonic() + seconds
        while not condition() and time.monotonic() < deadline:
            QTest.qWait(20)
        assert condition(), {"state": json.loads(controller.snapshotJson), "requests": requests, "qml": errors}

    def visual_item(condition):
        pending = [window.contentItem()]
        while pending:
            item = pending.pop()
            if condition(item):
                return item
            pending.extend(item.childItems())
        return None

    def evaluate(script):
        view = visual_item(lambda item: item.property("identifier") == controller.current_tab)
        assert view is not None, "Current browser view missing from the visual tree"
        results.value = None
        engine.globalObject().setProperty("probeWeb", engine.newQObject(view))
        expression = "probeWeb.runJavaScript(" + json.dumps(script) + ",function(result){probeResults.record(JSON.stringify(result))})"
        result = engine.evaluate(expression)
        assert not result.isError(), result.toString()
        wait(lambda: results.value is not None)
        return results.value

    base = f"http://127.0.0.1:{server.server_port}"
    try:
        wait(lambda: window.isActive())
        QTest.qWait(60)
        QTest.keyClick(window, Qt.Key.Key_Down)
        wait(lambda: visual_item(lambda item: item.objectName() == "browserStartBookmarks").property("selected"))
        QTest.keyClick(window, Qt.Key.Key_Return)
        wait(lambda: controller.menus and controller.menus[-1]["title"] == "Bookmarks")
        QTest.keyClick(window, Qt.Key.Key_Escape)
        QTest.qWait(40)
        QTest.keyClick(window, Qt.Key.Key_Up)
        QTest.keyClick(window, Qt.Key.Key_Return)
        wait(lambda: controller.menus and controller.menus[-1]["title"] == "Address or search")
        QTest.keyClick(window, Qt.Key.Key_Escape)
        controller.set_zoom(zoom)
        controller.navigate(base + "/")
        wait(lambda: controller.active_tab().title == "Browser input fixture" and not controller.active_tab().loading)
        wait(lambda: window.isActive())
        QTest.keyClick(window, Qt.Key.Key_Down)
        wait(lambda: evaluate("document.querySelector('[data-udeck-focus]')?.tagName || ''") == "A")
        assert window.grabWindow().save(str(output / "selected-link.png"))
        QTest.keyClick(window, Qt.Key.Key_Return)
        wait(lambda: controller.active_tab().title == "Destination reached")
        controller.command("back")
        wait(lambda: controller.active_tab().title == "Browser input fixture" and not controller.active_tab().loading)
        QTest.keyClick(window, Qt.Key.Key_Down)
        QTest.qWait(60)
        QTest.keyClick(window, Qt.Key.Key_Down)
        wait(lambda: evaluate("document.querySelector('[data-udeck-focus]')?.id || ''") == "draft")
        QTest.keyClick(window, Qt.Key.Key_Return)
        wait(lambda: controller.web_mode == "text")
        QTest.qWait(80)
        for key in (Qt.Key.Key_A, Qt.Key.Key_B, Qt.Key.Key_X, Qt.Key.Key_Y):
            QTest.keyClick(window, key)
        assert evaluate("document.getElementById('draft').value") == "abxy"
        QTest.keyClick(window, Qt.Key.Key_Return)
        wait(lambda: any(path == "/submit?draft=abxy" for path in requests))
        wait(lambda: controller.active_tab().url == base + "/submit?draft=abxy"
             and not controller.active_tab().loading
             and evaluate("location.pathname === '/submit' && document.readyState === 'complete' && !!document.body"))
        controller.set_mode("reading")
        wait(lambda: controller.web_mode == "reading" and bool(controller.reading_text))
        original = controller.current_tab
        QTest.keyClick(window, Qt.Key.Key_T, Qt.KeyboardModifier.ControlModifier)
        wait(lambda: len(controller.web_tabs) == 2)
        assert controller.web_mode == "navigation" and controller.reading_text == ""
        controller.closeTab(controller.current_tab)
        wait(lambda: controller.current_tab == original)
        assert controller.web_mode == "navigation" and controller.reading_text == ""
        assert not errors, errors
        report = {"zoom": zoom, "startButtons": True, "linkActivated": True, "formSubmitted": True,
                  "readingTabSwitch": True, "qmlErrors": errors, "platform": application.platformName()}
        (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report), flush=True)
    finally:
        controller.close()
        window.setProperty("allowClose", True)
        window.close()
        delete(engine)
        application.processEvents()
        server.shutdown()
        worker.join(timeout=2)
        server.server_close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--zoom", type=float, required=True)
    arguments = parser.parse_args()
    run(arguments.output, arguments.zoom)
