"""
[INPUT]: 依赖真实 WebEngine、Qt 输入和本地 HTTP 页面。
[OUTPUT]: 验证页面缩放输入与外部协议零系统分发。
[POS]: 独立进程隔离浏览器渲染；URL 接收器截获系统调用。
[PROTOCOL]: Update this header on change, then check AGENTS.md
"""

import argparse
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from PySide6.QtCore import QObject, QPointF, Qt, QUrl, Slot
from PySide6.QtGui import QDesktopServices
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


class ExternalUrls(QObject):
    def __init__(self):
        super().__init__()
        self.calls = []

    @Slot(QUrl)
    def opened(self, url):
        self.calls.append(url.toString())


class DialogRequests(QObject):
    def __init__(self):
        super().__init__()
        self.calls = []

    @Slot(str, bool)
    def record(self, kind, accepted):
        self.calls.append((kind, accepted))


def run(output, zoom, protocols=False, dialogs=False):
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
            elif self.path == "/protocols":
                text = """<title>Protocol fixture</title><style>a{display:block;margin:20px}</style>
                    <a id="custom" href="udeck-test://external/click">Custom protocol</a>
                    <a id="mail" href="mailto:someone@example.org">Email</a>
                    <a id="phone" href="tel:123456">Phone</a>
                    <a id="torrent" href="magnet:?xt=urn:btih:1234">Torrent</a>
                    <a id="popup" target="_blank" href="udeck-test://external/popup">New window</a>
                    <a id="script" href="javascript:void(document.body.dataset.internalAction='clicked')">Page action</a>
                    <a id="redirect" href="/protocol-redirect">Redirect</a>"""
            elif self.path == "/protocol-redirect":
                self.send_response(302)
                self.send_header("Location", "udeck-test://external/redirect")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            elif self.path == "/dialogs":
                text = """<title>Dialog fixture</title>
                    <label>File upload<input type="file" id="upload"></label>
                    <label>Color<input type="color" id="colour"></label>"""
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
    external_urls = ExternalUrls()
    external_schemes = ("udeck-test", "mailto", "tel", "magnet")
    for scheme in external_schemes:
        QDesktopServices.setUrlHandler(scheme, external_urls, "opened")
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
    dialog_requests = DialogRequests()
    engine.globalObject().setProperty("probeDialogs", engine.newQObject(dialog_requests))

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

    def click_link(identifier):
        position = evaluate("(() => {const r=document.getElementById(" + json.dumps(identifier)
                            + ").getBoundingClientRect();return [r.x+r.width/2,r.y+r.height/2]})()")
        view = visual_item(lambda item: item.property("identifier") == controller.current_tab)
        point = view.mapToScene(QPointF(position[0] * zoom, position[1] * zoom)).toPoint()
        QTest.mouseClick(window, Qt.MouseButton.LeftButton, pos=point)

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
        wait(lambda: evaluate("document.getElementById('draft').value") == "abxy")
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
        if protocols:
            controller.navigate(base + "/protocols")
            wait(lambda: controller.active_tab().title == "Protocol fixture" and not controller.active_tab().loading)
            for identifier in ("custom", "mail", "phone", "torrent", "popup"):
                controller.error = ""
                controller.publish()
                click_link(identifier)
                wait(lambda: bool(controller.error) or bool(external_urls.calls))
                assert not external_urls.calls, external_urls.calls
                assert controller.error, identifier
            controller.error = ""
            controller.publish()
            click_link("script")
            wait(lambda: evaluate("document.body.dataset.internalAction || ''") == "clicked")
            assert not controller.error
            evaluate("(() => {const f=document.createElement('iframe');f.src='udeck-test://external/frame';"
                     "document.body.append(f);return true})()")
            QTest.qWait(200)
            assert not external_urls.calls, external_urls.calls
            click_link("redirect")
            wait(lambda: "/protocol-redirect" in requests and not controller.active_tab().loading)
            QTest.qWait(200)
            assert not external_urls.calls, external_urls.calls
            assert controller.active_tab().url.startswith(base)
        if dialogs:
            controller.navigate(base + "/dialogs")
            wait(lambda: controller.active_tab().title == "Dialog fixture" and not controller.active_tab().loading)
            view = visual_item(lambda item: item.property("identifier") == controller.current_tab)
            engine.globalObject().setProperty("probeWeb", engine.newQObject(view))
            for signal, kind in (("fileDialogRequested", "file"), ("colorDialogRequested", "color")):
                result = engine.evaluate("probeWeb." + signal + ".connect(function(request){"
                                         "probeDialogs.record(" + json.dumps(kind) + ",request.accepted);"
                                         "if(!request.accepted){request.accepted=true;request.dialogReject()}})")
                assert not result.isError(), result.toString()
            for identifier, kind in (("upload", "file"), ("colour", "color")):
                controller.error = ""
                controller.publish()
                before = len(dialog_requests.calls)
                click_link(identifier)
                wait(lambda before=before: len(dialog_requests.calls) > before)
                assert dialog_requests.calls[-1] == (kind, True), dialog_requests.calls
                assert controller.error
            assert [item for item in application.topLevelWindows() if item.isVisible()] == [window]
        assert not errors, errors
        report = {"zoom": zoom, "startButtons": True, "linkActivated": True, "formSubmitted": True,
                  "readingTabSwitch": True, "protocolsBlocked": protocols, "externalCalls": external_urls.calls,
                  "systemDialogsBlocked": dialogs, "dialogRequests": dialog_requests.calls,
                  "qmlErrors": errors, "platform": application.platformName()}
        (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report), flush=True)
    finally:
        controller.close()
        window.setProperty("allowClose", True)
        window.close()
        delete(engine)
        application.processEvents()
        for scheme in external_schemes:
            QDesktopServices.unsetUrlHandler(scheme)
        server.shutdown()
        worker.join(timeout=2)
        server.server_close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--zoom", type=float, required=True)
    parser.add_argument("--protocols", action="store_true")
    parser.add_argument("--dialogs", action="store_true")
    arguments = parser.parse_args()
    run(arguments.output, arguments.zoom, arguments.protocols, arguments.dialogs)
