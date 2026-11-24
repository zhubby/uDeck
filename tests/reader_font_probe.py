"""
[INPUT]: 依赖真实 Reader、WebEngine 与原创三格式文档。
[OUTPUT]: 验证正文实际加载文楷、翻页及保存后的字体选择。
[POS]: 阅读字体的独立进程探针；状态和文档均在指定目录。
[PROTOCOL]: Update this header on change, then check AGENTS.md
"""

import json
import os
import sys
import time
import zipfile
from pathlib import Path

from mobi_fixture import mobi_bytes
from PySide6.QtCore import QEventLoop, QObject, QTimer, QUrl
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtWebEngineQuick import QtWebEngineQuick
from PySide6.QtWidgets import QApplication
from shiboken6 import delete

import udeck
from udeck.apps.common.library import Source, scan
from udeck.apps.main import make_controller
from udeck.apps.reader.controller import PdfImages, ReaderController
from udeck.icons import IconProvider


def fixtures(directory):
    directory.mkdir(parents=True)
    text = "霞鹜文楷屏幕阅读版：山川湖海，书页之间。Reading with LXGW WenKai Screen."
    (directory / "original.txt").write_text((text + "\n\n") * 100)
    (directory / "original.mobi").write_bytes(mobi_bytes())
    with zipfile.ZipFile(directory / "original.epub", "w") as archive:
        archive.writestr("mimetype", "application/epub+zip")
        archive.writestr("META-INF/container.xml", '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="book.opf" media-type="application/oebps-package+xml"/></rootfiles></container>')
        archive.writestr("book.opf", '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="id"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:identifier id="id">udeck-font-test</dc:identifier><dc:title>文楷阅读测试</dc:title><dc:language>zh-CN</dc:language></metadata><manifest><item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/><item id="body" href="body.xhtml" media-type="application/xhtml+xml"/></manifest><spine><itemref idref="body"/></spine></package>')
        archive.writestr("nav.xhtml", '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops"><head><title>目录</title></head><body><nav epub:type="toc"><ol><li><a href="body.xhtml">文楷</a></li></ol></nav></body></html>')
        archive.writestr("body.xhtml", '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>文楷</title></head><body>' + ("<p>" + text + "</p>") * 100 + "</body></html>")


def run(output):
    output.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")
    QtWebEngineQuick.initialize()
    application = QApplication([])
    controller = make_controller("reader", output / "state", output / "settings.json")
    controller.isolated = True
    engine = QQmlApplicationEngine()
    engine.addImageProvider("desktop", IconProvider())
    engine.addImageProvider("pdf", PdfImages(controller))
    engine.rootContext().setContextProperty("controller", controller)
    engine.rootContext().setContextProperty("windowed", True)
    errors = []
    engine.warnings.connect(lambda values: errors.extend(item.toString() for item in values))
    engine.load(QUrl.fromLocalFile(str(Path(udeck.__file__).parent / "apps/common/qml/Main.qml")))
    assert engine.rootObjects(), errors
    window = engine.rootObjects()[0]
    window.setWidth(1280)
    window.setHeight(720)
    controller.window = window
    window.show()

    def pause(milliseconds=20):
        application.processEvents()
        loop = QEventLoop()
        QTimer.singleShot(milliseconds, loop.quit)
        loop.exec()

    def wait(condition, seconds=20):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if condition():
                return
            pause()
        raise AssertionError({"state": controller.snapshotJson, "qml": errors, "reader": controller.reader_log})

    sequence = 0

    def inspect():
        nonlocal sequence
        sequence += 1
        prefix = f"FONT_PROBE_{sequence}:"
        view = next(item for item in window.findChildren(QObject)
                    if item.inherits("QQuickWebEngineView") and controller.book.token in str(item.property("url")))
        engine.globalObject().setProperty("probeWeb", engine.newQObject(view))
        script = """(() => {
            const doc = document.querySelector('foliate-view').renderer.getContents()[0].doc;
            const p = doc.querySelector('p') || doc.body;
            console.log(PREFIX + JSON.stringify({
                family: doc.defaultView.getComputedStyle(p).fontFamily,
                faces: [...doc.fonts].map(face => ({family:face.family,status:face.status})),
                text:doc.body.textContent.slice(0,120)
            }));
        })()""".replace("PREFIX", json.dumps(prefix))
        result = engine.evaluate("probeWeb.runJavaScript(" + json.dumps(script) + ")")
        assert not result.isError(), result.toString()
        wait(lambda: any(line.startswith(prefix) for line in controller.reader_log))
        return json.loads(next(line[len(prefix):] for line in controller.reader_log if line.startswith(prefix)))

    def wenkai_loaded():
        result = inspect()
        return ("LXGW WenKai Screen" in result["family"]
                and any("LXGW WenKai Screen" in face["family"] and face["status"] == "loaded"
                        for face in result["faces"]))

    report = {"checks": [], "qmlErrors": errors, "package": str(Path(udeck.__file__).parent)}
    try:
        assert controller.font_family == "wenkai"
        fixtures(output / "content")
        source = Source.create(output / "content")
        controller.library.sources = [source]
        controller.library.items = scan(source, "reader")
        for extension in ("TXT", "EPUB", "MOBI"):
            item = next(item for item in controller.library.items if item["format"] == extension)
            controller.open_item(item["id"])
            wait(lambda: controller.reader_ready and bool(controller.position.get("cfi")))
            wait(wenkai_loaded)
            initial = inspect()
            position = controller.position["cfi"]
            controller.dispatch("next-tab")
            wait(lambda position=position: controller.position.get("cfi") != position)
            wait(wenkai_loaded)
            pause(150)
            assert window.grabWindow().save(str(output / (extension.lower() + "-wenkai.png")))
            report["checks"].append({"format": extension, "initial": initial, "afterPage": inspect()})
            controller.back()
        controller.set_font_family("serif")
        controller.close()
        restored = ReaderController(output / "state", output / "settings.json")
        assert restored.font_family == "serif"
        restored.set_font_family("wenkai")
        restored.close()
        restored = ReaderController(output / "state", output / "settings.json")
        assert restored.font_family == "wenkai"
        restored.close()
        assert not errors, errors
        report.update(passed=True, savedChoicePreserved=True)
        (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps(report, ensure_ascii=False), flush=True)
    finally:
        controller.close()
        window.setProperty("allowClose", True)
        window.close()
        delete(engine)


if __name__ == "__main__":
    run(Path(sys.argv[1]).resolve())
