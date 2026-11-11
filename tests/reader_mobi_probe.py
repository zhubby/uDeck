"""Exercise an original MOBI in the real installed/local Reader and retain evidence.

Usage: python tests/reader_mobi_probe.py /path/to/book.mobi /path/to/evidence
Uses independent state; never modifies the book or the user's Reader settings.
"""

import hashlib
import json
import os
import sys
import time
from pathlib import Path

from PySide6.QtCore import QObject, QUrl, qVersion
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtTest import QTest
from PySide6.QtWebEngineQuick import QtWebEngineQuick
from PySide6.QtWidgets import QApplication
from shiboken6 import delete

import udeck
from udeck.apps.common.library import Source, fingerprint
from udeck.apps.main import make_controller
from udeck.apps.reader.controller import PdfImages
from udeck.icons import IconProvider


def run(path, output):
    output.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")
    QtWebEngineQuick.initialize()
    qt = QApplication([])
    controller = make_controller("reader", output / "state", output / "settings.json")
    controller.isolated = True
    controller.set_language("zh_CN")
    engine = QQmlApplicationEngine()
    engine.addImageProvider("desktop", IconProvider())
    errors = []
    engine.warnings.connect(lambda values: errors.extend(x.toString() for x in values))
    engine.rootContext().setContextProperty("controller", controller)
    engine.rootContext().setContextProperty("windowed", True)
    engine.addImageProvider("pdf", PdfImages(controller))
    qml = Path(udeck.__file__).parent / "apps/common/qml/Main.qml"
    engine.load(QUrl.fromLocalFile(str(qml)))
    assert engine.rootObjects(), errors
    window = engine.rootObjects()[0]
    window.setWidth(1280)
    window.setHeight(720)
    controller.window = window
    window.show()

    def wait(condition, seconds=90):
        deadline = time.monotonic() + seconds
        while not condition() and time.monotonic() < deadline:
            qt.processEvents()
            QTest.qWait(20)
        assert condition(), {"state": controller.snapshotJson, "qml": errors,
                             "log": controller.reader_log}

    def capture(name):
        qt.processEvents()
        QTest.qWait(150)
        assert window.grabWindow().save(str(output / (name + ".png")))

    sequence = 0

    def inspect():
        nonlocal sequence
        sequence += 1
        prefix = f"UDECK_MOBI_PROBE_{sequence}:"
        views = [x for x in window.findChildren(QObject) if x.inherits("QQuickWebEngineView")]
        view = next(x for x in views if controller.book.token in str(x.property("url")))
        engine.globalObject().setProperty("probeWeb", engine.newQObject(view))
        script = '''(() => {
            const view = document.querySelector('foliate-view');
            const contents = view.renderer.getContents();
            const doc = contents[0].doc;
            const p = doc.querySelector('p') || doc.body;
            const css = doc.defaultView.getComputedStyle(p);
            const body = doc.defaultView.getComputedStyle(doc.body);
            console.log(PREFIX + JSON.stringify({
                title: view.book.metadata.title, sections: view.book.sections.length,
                section: contents[0].index, text: doc.body.textContent.slice(0, 200),
                font: css.fontFamily, size: css.fontSize, lineHeight: css.lineHeight,
                background: body.backgroundColor, width: view.renderer.getAttribute('max-inline-size'),
                images: [...doc.images].map(x => ({src: x.src.slice(0, 40), complete: x.complete,
                    width: x.naturalWidth})),
            }));
        })()'''.replace("PREFIX", json.dumps(prefix))
        result = engine.evaluate("probeWeb.runJavaScript(" + json.dumps(script) + ")")
        assert not result.isError(), result.toString()
        wait(lambda: any(line.startswith(prefix) for line in controller.reader_log))
        return json.loads(next(line[len(prefix):] for line in controller.reader_log if line.startswith(prefix)))

    report = {"path": str(path), "bytes": path.stat().st_size, "qtVersion": qVersion(),
              "platform": qt.platformName(), "package": str(Path(udeck.__file__).parent), "checks": []}
    try:
        # Index only the selected book, so this probe does not hash an entire
        # documents/cloud directory. Library discovery has separate scan tests.
        source = Source.create(path.parent)
        digest = fingerprint(path)
        stamp = path.stat()
        identifier = hashlib.sha256(f"{source.id}/{path.name}/{digest}".encode()).hexdigest()
        item = {"id": identifier, "sourceId": source.id, "path": str(path), "relative": path.name,
                "fingerprint": digest, "stamp": [stamp.st_size, stamp.st_mtime_ns], "metadata": {},
                "title": path.stem, "format": "MOBI", "album": path.parent.name,
                "folder": str(path.parent), "cover": "", "duration": 0, "artist": "", "platform": ""}
        controller.library.sources = [source]
        controller.library.items = [item]
        report["sha256"] = digest
        assert item["format"] == "MOBI"
        controller.open_item(item["id"])
        wait(lambda: controller.reader_ready and bool(controller.position.get("cfi")))
        assert not controller.error
        report["initial"] = inspect()
        assert report["initial"]["sections"] > 1
        report["tocCount"] = len(controller.contents)
        assert controller.contents
        capture("mobi-open")
        report["checks"].append("original-mobi-opens-with-toc")

        # Navigate through a real table-of-contents entry before turning pages.
        target = controller.contents[min(3, len(controller.contents) - 1)]
        before = dict(controller.position)
        controller.send_reader("goto", target["href"])
        wait(lambda: controller.position != before)
        wait(lambda: bool(inspect()["text"].strip()))
        first = controller.position["cfi"]
        controller.dispatch("next-tab")
        wait(lambda: controller.position.get("cfi") != first)
        report["checks"].append("toc-navigation-and-page-turn")

        controller.set_font(28)
        controller.set_font_family("serif")
        controller.set_line_height(2.0)
        controller.set_content_width(720)
        controller.set_background("warm")
        wait(lambda: inspect()["size"] == "28px" and inspect()["lineHeight"] == "56px")
        report["styled"] = inspect()
        assert "serif" in report["styled"]["font"]
        assert report["styled"]["background"] == "rgb(242, 229, 199)"
        assert report["styled"]["width"] == "720px"
        capture("mobi-reading")
        report["checks"].append("rendered-font-size-family-line-height-width-background")

        controller.add_bookmark()
        assert controller.store.data["bookmarks"][item["id"]]
        query = "荷鲁斯" if "战锤" in path.name else "journey"
        controller.search_book(query)
        wait(lambda: bool(controller.search_results))
        report["searchResults"] = len(controller.search_results)
        report["searchQuery"] = query
        capture("mobi-search")
        controller.clear_menus()
        controller.goto_position(controller.search_results[min(1, len(controller.search_results) - 1)])
        QTest.qWait(250)
        qt.processEvents()
        report["checks"].append("bookmark-and-full-text-search")

        # Store the expected anchor independently: the next open must recover it.
        saved = dict(controller.position)
        controller.back()
        assert controller.store.data["positions"][item["id"]] == saved
        controller.open_item(item["id"])
        wait(lambda: controller.reader_ready and bool(controller.position.get("cfi")))
        assert controller.position["cfi"] == saved["cfi"], (saved, controller.position)
        report["savedPosition"] = saved
        report["reopened"] = inspect()
        report["checks"].append("original-file-position-restores-on-reopen")
        assert not controller.error and not errors
        capture("mobi-reopened")
        report["qmlErrors"] = errors
        (output / "verification.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps(report, ensure_ascii=False), flush=True)
    finally:
        controller.close()
        window.setProperty("allowClose", True)
        window.close()
        delete(engine)


if __name__ == "__main__":
    run(Path(sys.argv[1]).expanduser().resolve(), Path(sys.argv[2]).expanduser().resolve())
