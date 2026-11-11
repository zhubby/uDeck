"""Real Qt engines and QML workflows, run in a separate graphical process."""

import json
import math
import os
import struct
import subprocess
import sys
import threading
import time
import wave
import zipfile
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QObject, Qt, QTimer, QUrl
from PySide6.QtGui import QPageSize, QPainter, QPdfWriter
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtTest import QTest
from PySide6.QtWebEngineQuick import QtWebEngineQuick
from PySide6.QtWidgets import QApplication

from udeck.apps.main import AppControl, make_controller
from udeck.apps.media.engine import FrameImages
from udeck.apps.reader.controller import PdfImages
from udeck.core import ConfigStore
from udeck.i18n import render, tr
from udeck.icons import IconProvider


def fixtures(root):
    root.mkdir(parents=True, exist_ok=True)
    wav = root / "Original tone.wav"
    if not wav.exists():
        with wave.open(str(wav), "wb") as stream:
            stream.setnchannels(1)
            stream.setsampwidth(2)
            stream.setframerate(16000)
            stream.writeframes(b"".join(struct.pack("<h", int(1500 * math.sin(2*math.pi*220*i/16000)))
                                       for i in range(16000 * 12)))
        for extension in ("flac", "mp3", "m4a"):
            subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(wav),
                            "-metadata", "album=uDeck Originals", "-metadata", "artist=uDeck", str(wav.with_suffix("."+extension))], check=True)
        (root / "captions.srt").write_text("1\n00:00:00,000 --> 00:00:09,000\nOriginal uDeck subtitle 中文\n")
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                        "testsrc2=duration=12:size=640x360:rate=24", "-i", str(wav), "-i", str(root/"captions.srt"),
                        "-map", "0:v", "-map", "1:a", "-map", "2:s", "-c:v", "mpeg4", "-c:a", "aac", "-c:s", "srt",
                        "-metadata:s:s:0", "language=eng", str(root / "Original moving picture.mkv")], check=True)
        (root / "Original long book.txt").write_text("Original uDeck book\n\n" + "\n\n".join(
            f"Paragraph {i}. A steady journey through the meadow. 中文阅读测试。" * 4 for i in range(260)))
        with zipfile.ZipFile(root / "Original chapters.epub", "w") as archive:
            archive.writestr("mimetype", "application/epub+zip")
            archive.writestr("META-INF/container.xml", '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="OPS/book.opf" media-type="application/oebps-package+xml"/></rootfiles></container>')
            archive.writestr("OPS/book.opf", '''<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="id"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:identifier id="id">udeck-original-test</dc:identifier><dc:title>Original Chapters</dc:title><dc:language>en</dc:language></metadata><manifest><item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/><item id="one" href="one.xhtml" media-type="application/xhtml+xml"/><item id="two" href="two.xhtml" media-type="application/xhtml+xml"/></manifest><spine><itemref idref="one"/><itemref idref="two"/></spine></package>''')
            archive.writestr("OPS/nav.xhtml", '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops"><head><title>Contents</title></head><body><nav epub:type="toc"><ol><li><a href="one.xhtml">First meadow</a></li><li><a href="two.xhtml">Second harbor</a></li></ol></nav></body></html>')
            for name, title in (("one", "Meadow"), ("two", "Harbor")):
                archive.writestr(f"OPS/{name}.xhtml", '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>'+title+'</title><script>console.log("UDECK_BOOK_SCRIPT_RAN");fetch("https://example.com/leak")</script></head><body><h1>'+title+'</h1>' + "".join(f"<p>{i}. Original {title} paragraph and a steady journey. 中文文本。</p>" for i in range(130)) + '</body></html>')
        writer = QPdfWriter(str(root / "Original pages.pdf"))
        writer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
        painter = QPainter(writer)
        for i in range(3):
            if i:
                writer.newPage()
            painter.drawText(200, 400, f"Original uDeck page {i+1} — Meadow")
            painter.drawRect(100, 600, 5000, 5000)
        painter.end()
    return root


def run(app, root, language="en", width=1280, height=720):
    os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")
    QtWebEngineQuick.initialize()
    qt = QApplication([])
    content = fixtures(root / "source")
    controller = make_controller(app, root / "state", root / "settings.json")
    controller.isolated = True
    controller.set_language(language)
    engine = QQmlApplicationEngine()
    engine.addImageProvider("desktop", IconProvider())
    errors = []
    engine.warnings.connect(lambda values: errors.extend(x.toString() for x in values))
    engine.rootContext().setContextProperty("controller", controller)
    engine.rootContext().setContextProperty("windowed", True)
    if app == "reader":
        engine.addImageProvider("pdf", PdfImages(controller))
    elif app in ("music", "video"):
        engine.addImageProvider("video", FrameImages(controller))
    engine.load(QUrl.fromLocalFile(str(Path(__file__).parents[1] / "src/udeck/apps/common/qml/Main.qml")))
    assert engine.rootObjects(), errors
    window = engine.rootObjects()[0]
    window.setWidth(width)
    window.setHeight(height)
    controller.window = window
    window.show()
    window.requestActivate()
    def wait(condition, seconds=15):
        deadline = time.monotonic()+seconds
        while not condition() and time.monotonic()<deadline:
            qt.processEvents()
            QTest.qWait(15)
        assert condition(), {"timeout": str(condition), "state": controller.snapshotJson, "qml": errors, "readerLog": getattr(controller,"reader_log",[]), "click":getattr(controller,"last_click",{}), "views": [{"url":str(v.property("url")),"canGoBack":v.property("canGoBack")} for v in window.findChildren(QObject) if v.inherits("QQuickWebEngineView")]}
    def capture(name):
        qt.processEvents()
        QTest.qWait(120)
        path = root / (name + ".png")
        assert window.grabWindow().save(str(path))
    completed = []

    def theme_cycle():
        current = deepcopy(controller.current)
        page = controller.page
        views = [v for v in window.findChildren(QObject) if v.inherits("QQuickWebEngineView")]
        urls = [v.property("url") for v in views]
        player = controller.media.player if app in ("music", "video") else None
        book = controller.book if app == "reader" else None
        reader_url = controller.reader_url if app == "reader" else None
        for theme in ("dark", "classic"):
            configuration = ConfigStore(root / "settings.json")
            configuration.data["preferences"]["theme"] = theme
            configuration.save()
            wait(lambda theme=theme: controller.theme == theme)
            assert controller.current == current and controller.page == page
            assert [v for v in window.findChildren(QObject) if v.inherits("QQuickWebEngineView")] == views
            assert [v.property("url") for v in views] == urls
            if player:
                assert controller.media.player is player
            if book:
                assert controller.book is book and not book.closed
                assert controller.reader_url == reader_url
            capture("theme-" + theme)
        completed.append("global-theme-preserves-native-content")
    if controller.library:
        controller.library.add(content)
        wait(lambda: not controller.library.pending)
        controller.setTab(1 if app in ("reader", "emulator", "video") else 0)
        assert controller.library.items
        capture("library")
    if app == "music":
        first = next(i for i in controller.library.items if i["format"] == "FLAC")
        controller.open_item(first["id"])
        wait(lambda: controller.media.player.position()>300)
        assert controller.media.player.duration()>10000
        capture("playing")
        controller.media.player.pause()
        control = AppControl(controller, lambda: None, errors, time.monotonic())
        controller.media.player.play()
        assert control.PauseForVideo("video-one")
        assert not control.IsPlaying()
        control.ResumeAfterVideo("stale-token")
        assert not control.IsPlaying()
        control.ResumeAfterVideo("video-one")
        wait(control.IsPlaying)
        assert control.PauseForVideo("video-two")
        controller.command("play-pause")
        controller.media.player.pause()
        control.ResumeAfterVideo("video-two")
        assert not control.IsPlaying()
        completed.append("music-video-pause-ownership")
        controller.seek(4)
        wait(lambda: controller.media.player.position()>=3900)
        position = controller.media.player.position()
        controller.back()
        assert controller.page=="library" and controller.media.player.position()==position
        controller.media.player.play()
        controller.library.refresh()
        wait(lambda: not controller.library.pending)
        assert controller.current["id"]==first["id"] and controller.media.player.position()>=position
        controller.command("now-playing")
        controller.queue_view()
        assert controller.page == "library" and controller.tab == 2
        controller.back()
        assert controller.page == "player" and controller.current["id"] == first["id"]
        completed.extend(["real-flac-playback", "seek", "background-browsing", "refresh-keeps-session"])
        for extension in ("MP3", "M4A", "WAV"):
            item = next(i for i in controller.library.items if i["format"]==extension)
            controller.play(item)
            wait(lambda: not controller.media.loading and controller.media.player.position()>150)
            assert not controller.media.player.errorString()
        controller.media.player.pause()
        controller.open_item(first["id"])
        wait(lambda: controller.media.player.position()>300)
        controller.settings()
        controller.prompt("Search", lambda text: None, "abxy 中文")
        controller.set_language("zh_CN")
        assert controller.menus[-1]["draft"]=="abxy 中文" and controller.current["id"]==first["id"]
        controller.clear_menus()
        capture("settings")
        outputs = controller.media.devices.audioOutputs()
        if outputs:
            controller.change_output(bytes(outputs[0].id()).hex())
            assert controller.media.output.device().id() == outputs[0].id()
            completed.append("observed-audio-device-selection")
        other = next(i for i in controller.library.items if i["format"] == "WAV")
        controller.queue.replace([other["id"], first["id"]], other["id"])
        controller.play(other, queued=True)
        wait(lambda: controller.media.player.duration() > 10000 and not controller.media.loading)
        controller.media.seek(11.6)
        wait(lambda: controller.current["id"] == first["id"] and controller.media.player.position() > 0)
        completed.append("real-end-of-file-queue-transition")
        completed.extend(["real-mp3-aac-wav-playback", "language-preserves-playback-and-draft"])
        theme_cycle()
    elif app == "video":
        item=controller.library.items[0]
        controller.open_item(item["id"])
        wait(lambda: controller.media.player.position()>300)
        assert controller.media.player.videoSink().videoSize().width()==640
        assert controller.media.player.videoSink().videoFrame().isValid()
        assert len(controller.media.player.subtitleTracks())==1
        controller.set_track(True,0)
        wait(lambda: "Original uDeck subtitle" in controller.media.player.videoSink().subtitleText())
        assert "Original uDeck subtitle" in controller.subtitle_text(), "Software video lost embedded captions"
        wait(lambda: any("Original uDeck subtitle" in str(obj.property("text"))
                         for obj in window.findChildren(QObject) if obj.inherits("QQuickText")))
        capture("embedded-captions")
        completed.append("embedded-captions-visible-in-software-scenegraph")
        controller.media.player.pause()
        controller.seek(4)
        wait(lambda: controller.media.player.position()>=3900)
        capture("playing")
        frame = window.grabWindow()
        colored = sum(frame.pixelColor(x, y).saturation() > 80 and frame.pixelColor(x, y).value() > 80
                      for x in range(40, width-40, 40) for y in range(100, height-170, 30))
        assert colored > 50, "The decoded video frame was not composed into the visible window"
        controller.back()
        assert controller.store.data["positions"][item["id"]]>=3.9
        controller.open_item(item["id"])
        assert controller.menus
        capture("resume")
        controller.choose(0)
        wait(lambda: not controller.media.loading and controller.media.player.position()>3900)
        controller.context()
        controller.choose(0)
        capture("subtitles")
        controller.clear_menus()
        controller.load_subtitles(content / "captions.srt")
        controller.media.player.pause()
        controller.seek(4)
        wait(lambda: "中文" in controller.subtitle_text())
        controller.command("hide-controls")
        assert not controller.controls_visible and controller.subtitle_text()
        capture("external-captions")
        completed.append("external-srt-survives-hidden-controls")
        completed.extend(["real-video-frames", "embedded-subtitle-track", "seek", "pause-and-save", "confirmed-resume"])
        theme_cycle()
    elif app == "reader":
        pdf_item = next(i for i in controller.library.items if i["format"] == "PDF")
        txt_item = next(i for i in controller.library.items if i["format"] == "TXT")
        controller.open_item(pdf_item["id"])
        wait(lambda: controller.reader_ready)
        controller.turn_pdf(1)
        controller.set_zoom(1.5, False)
        controller.pdfPan(75, 160)
        controller.context()
        controller.contents_menu()
        controller.open_item(txt_item["id"])
        assert not controller.menus, "The new book kept callbacks belonging to the previous document"
        saved_pdf = controller.store.data["positions"][pdf_item["id"]]
        assert saved_pdf["page"] == 1 and saved_pdf["zoom"] == 1.5
        assert saved_pdf["x"] == 75 and saved_pdf["y"] == 160, saved_pdf
        controller.back()
        assert controller.page == "library" and not controller.history
        completed.append("direct-open-keeps-last-pdf-position-and-closes-old-menus")
        for extension in ("TXT", "EPUB", "PDF"):
            item=next(i for i in controller.library.items if i["format"]==extension)
            controller.open_item(item["id"])
            wait(lambda: controller.reader_ready, 20)
            if extension=="PDF":
                assert controller.pdf.pageCount()==3
                controller.turn_pdf(1)
                controller.set_zoom(1.5,False)
                capture("pdf-zoom")
                controller.dispatch("down")
                controller.dispatch("right")
                assert controller.pdf_page==1
                controller.search_book("Meadow")
                wait(lambda: len(controller.search_results)==3)
                controller.goto_position(controller.search_results[1])
                assert controller.pdf_page == 1 and controller.extra_state()["pdfHighlights"]
                capture("pdf-search-highlight")
                controller.clear_menus()
            else:
                wait(lambda: bool(controller.position.get("cfi")))
                original=controller.position["cfi"]
                controller.dispatch("next-tab")
                wait(lambda original=original: controller.position.get("cfi")!=original)
                controller.set_font(28)
                controller.set_line_height(2.0)
                controller.set_font_family("serif")
                controller.set_content_width(720)
                controller.set_background("warm")
                style = controller.extra_state()
                assert style["fontSize"] == 28
                assert style["lineHeight"] == 2.0
                assert style["fontFamily"] == "serif"
                assert style["contentWidth"] == 720
                assert style["background"] == "warm" and not style["dark"]
                QTest.qWait(100)
                controller.add_bookmark()
                assert controller.store.data["bookmarks"][item["id"]]
                if extension=="EPUB":
                    assert len(controller.contents)==2
                    assert not any("UDECK_BOOK_SCRIPT_RAN" in line for line in controller.reader_log)
                    assert any("Content Security Policy" in line for line in controller.reader_log)
                capture(extension.lower()+"-reading")
                controller.search_book("journey")
                wait(lambda: bool(controller.search_results), 25)
                assert all(not result["title"].startswith('{"pre"') for result in controller.search_results)
                controller.clear_menus()
                capture(extension.lower()+"-search")
                controller.back()
                controller.open_item(item["id"])
                wait(lambda: controller.reader_ready and bool(controller.position.get("cfi")))
                assert controller.position["cfi"]==controller.store.data["positions"][item["id"]]["cfi"]
            controller.back()
            completed.append("real-"+extension.lower()+"-read-search-position")
        item=next(i for i in controller.library.items if i["format"]=="TXT")
        controller.open_item(item["id"])
        wait(lambda: controller.reader_ready)
        controller.context()
        previous_book = controller.book
        (content / "Z malformed.epub").write_bytes(b"Not an EPUB archive")
        controller.library.refresh()
        wait(lambda: not controller.library.pending)
        broken = next(i for i in controller.library.items if i["title"] == "Z malformed")
        # Pagination can update the fraction while the library scan processes events.
        # Compare the last valid position immediately before the failing open.
        previous_position = dict(controller.position)
        controller.attempt(lambda: controller.open_item(broken["id"]))
        assert "Invalid EPUB" in render(controller.error, "en")
        assert previous_book.closed and not controller.menus and controller.page == "library"
        assert controller.store.data["positions"][item["id"]] == previous_position, (
            previous_position, controller.store.data["positions"][item["id"]])
        completed.append("malformed-epub-is-recoverable-and-preserves-last-position")
        controller.error = ""
        controller.open_item(item["id"])
        wait(lambda: controller.reader_ready)
        theme_cycle()
        controller.context()
        old_book=controller.book
        content.rename(root/"detached")
        controller.library.check_sources()
        assert controller.page=="library" and not controller.menus and old_book.closed
        completed.append("source-removal-closes-document-and-owned-menu")
    elif app == "browser":
        requests = []
        class Page(BaseHTTPRequestHandler):
            def log_message(self,*args):
                pass
            def do_GET(self):
                requests.append(self.path)
                if self.path == "/download":
                    data = b"Original uDeck download fixture\n"
                    self.send_response(200)
                    self.send_header("Content-Type", "application/octet-stream")
                    self.send_header("Content-Disposition", 'attachment; filename="original-udeck.txt"')
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    try:
                        self.wfile.write(data)
                    except (BrokenPipeError, ConnectionResetError):
                        pass
                    return
                data=(b'<title>Original web test</title><main><h1>Original page</h1><a href="/second">Next page</a><form action="/submit"><input id="draft" name="draft"/></form><p>Meadow reading text.</p></main>'
                      if self.path!="/second" else b'<title>Second original page</title><main><p>Second page reached</p></main>')
                self.send_response(200)
                self.send_header("Content-Type","text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(data)
        server=ThreadingHTTPServer(("127.0.0.1",0),Page)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        controller.navigate(f"http://127.0.0.1:{server.server_port}/")
        wait(lambda: controller.active_tab().title=="Original web test" and not controller.active_tab().loading)
        capture("page")
        first_tab=controller.current_tab
        controller.bookmark()
        controller.dispatch("down")
        controller.dispatch("accept")
        wait(lambda: controller.active_tab().url.endswith("/second") and controller.active_tab().can_back and not controller.active_tab().loading)
        assert controller.active_tab().can_back
        controller.new_tab()
        assert len(controller.web_tabs)==2
        controller.setTab(0)
        assert controller.current_tab==first_tab and controller.active_tab().can_back
        controller.command("back")
        wait(lambda: controller.active_tab().title=="Original web test" and not controller.active_tab().loading)
        controller.set_mode("reading")
        wait(lambda: controller.web_mode=="reading")
        assert "Meadow reading text" in controller.reading_text
        capture("reading")
        controller.set_mode("pointer")
        controller.dispatch("right")
        capture("pointer")
        controller.set_mode("navigation")
        QTest.qWait(100)
        controller.dispatch("down")
        QTest.qWait(60)
        controller.dispatch("down")
        QTest.qWait(60)
        controller.dispatch("accept")
        wait(lambda: controller.web_mode == "text")
        QTest.qWait(100)
        for key in (Qt.Key.Key_A, Qt.Key.Key_B, Qt.Key.Key_X, Qt.Key.Key_Y):
            QTest.keyClick(window, key)
        QTest.keyClick(window, Qt.Key.Key_Return)
        wait(lambda: any("/submit?draft=abxy" in path for path in requests))
        completed.append("real-form-text-keeps-ordinary-abxy-letters")
        controller.set_mode("navigation")
        with patch("PySide6.QtCore.QStandardPaths.writableLocation", return_value=str(root / "downloads")):
            decisions = []
            def download(confirm):
                timer = QTimer()
                def decide():
                    if controller.menus and controller.menus[-1]["title"] == tr("Download this file?"):
                        timer.stop()
                        decisions.append(list((root / "downloads").glob("*")))
                        capture("download-confirm" if confirm else "download-cancel")
                        controller.choose(0) if confirm else controller.dispatch("back")
                timer.timeout.connect(decide)
                timer.start(20)
                before = len(decisions)
                controller.navigate(f"http://127.0.0.1:{server.server_port}/download")
                wait(lambda: len(decisions) > before)
                timer.stop()
            download(False)
            QTest.qWait(150)
            assert decisions == [[]] and not (root / "downloads").exists()
            download(True)
            downloaded = root / "downloads/original-udeck.txt"
            wait(lambda: downloaded.exists() and not controller.downloads)
            assert downloaded.read_bytes() == b"Original uDeck download fixture\n"
            assert decisions == [[], []]
            download(True)
            wait(lambda: len(list((root / "downloads").glob("*"))) == 2 and not controller.downloads)
            assert decisions[-1] == [downloaded]
            assert all(path.read_bytes() == downloaded.read_bytes() for path in (root / "downloads").glob("*"))
            controller.clear_menus()
        completed.extend(["real-download-cancel-writes-nothing", "real-download-consent-and-original-bytes",
                          "repeated-download-preserves-existing-file"])
        theme_cycle()
        controller.closeTab(controller.web_tabs[1].identifier)
        controller.closeTab(controller.current_tab)
        assert len(controller.web_tabs)==1
        assert controller.store.data["history"] and controller.store.data["bookmarks"]
        server.shutdown()
        completed.extend(["real-http-page", "link-navigation", "tabs-retain-history", "reading-extraction", "virtual-pointer", "last-tab-replacement", "history-bookmarks"])
    assert not errors, errors
    capture("final")
    print(json.dumps({"app":app,"checks":completed,"qmlErrors":errors}),flush=True)
    controller.close()
    window.setProperty("allowClose",True)
    window.close()
    del engine


if __name__=="__main__":
    run(sys.argv[1], Path(sys.argv[2]), sys.argv[3] if len(sys.argv)>3 else "en",
        int(sys.argv[4]) if len(sys.argv)>4 else 1280, int(sys.argv[5]) if len(sys.argv)>5 else 720)
