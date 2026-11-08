"""Native PDF rendering and isolated EPUB/TXT reading sessions."""

import json
import math
import re

from PySide6.QtCore import QModelIndex, QSize, QTimer, Signal, Slot
from PySide6.QtGui import QImage
from PySide6.QtPdf import QPdfBookmarkModel, QPdfDocument
from PySide6.QtQuick import QQuickImageProvider

from ..i18n import tr
from ..sounds import interaction
from .books import BookServer
from .controller import AppController
from .reader_style import (
    READER_BACKGROUNDS,
    READER_CONTENT_WIDTHS,
    READER_FONT_FAMILIES,
    READER_FONT_SIZES,
    READER_LINE_HEIGHTS,
    normalize_reader_preferences,
)


class PdfImages(QQuickImageProvider):
    def __init__(self, controller):
        super().__init__(QQuickImageProvider.ImageType.Image)
        self.controller = controller

    def requestImage(self, identifier, size, requested_size):
        controller = self.controller
        if controller.pdf.status() != QPdfDocument.Status.Ready:
            return QImage()
        page = controller.pdf_page
        points = controller.pdf.pagePointSize(page)
        width = max(100, min(2800, requested_size.width() if requested_size.width() > 0 else 1200))
        height = max(100, min(5000, round(width * points.height() / max(1, points.width()))))
        image = controller.pdf.render(page, QSize(width, height))
        size.setWidth(image.width())
        size.setHeight(image.height())
        return image


class ReaderController(AppController):
    pdfMoved = Signal()

    def __init__(self, directory=None, language_path=None):
        super().__init__("reader", directory, language_path)
        self.pdf = QPdfDocument(self)
        self.pdf.passwordRequired.connect(self.password_required)
        self.pdf_page, self.pdf_zoom, self.pdf_x, self.pdf_y = 0, 1.0, 0.0, 0.0
        self.pdf_fit = True
        self.pdf_revision = 0
        self.pdf_highlights = []
        self.pdf_toc = QPdfBookmarkModel(self)
        self.pdf_toc.setDocument(self.pdf)
        self.book = None
        self.reader_log = []
        self.reader_url, self.reader_ready, self.reader_label = "", False, ""
        self.position, self.contents = {}, []
        self.search_generation = 0
        self.search_results = []
        self.search_query = ""
        self.ticks = 0
        preferences = normalize_reader_preferences(self.store.data["preferences"])
        self.store.data["preferences"].update(preferences)
        self.font_size = preferences["fontSize"]
        self.line_height = preferences["lineHeight"]
        self.font_family = preferences["fontFamily"]
        self.background = preferences["background"]
        self.content_width = preferences["contentWidth"]
        self.dark = preferences["dark"]

    def tabs(self):
        return [tr("Recent books"), tr("Bookshelf"), tr("Folders")]

    def rows(self):
        rows = super().rows()
        if self.tab == 0:
            order = self.store.data["recent"]
            rows = [row for row in rows if row["id"] in order]
            rows.sort(key=lambda row: order.index(row["id"]))
        for row in rows:
            position = self.store.data["positions"].get(row["id"], {})
            row["progress"] = position.get("fraction", 0) if isinstance(position, dict) else 0
        return rows

    def open_item(self, identifier):
        item = self.library.require(identifier)
        self.save_position()
        self.persist()
        self.clear_menus()
        self.close_document()
        if self.page == "document":
            super().back()
        self.current = item
        self.position = dict(self.store.data["positions"].get(identifier, {}))
        self.reader_ready, self.reader_label, self.contents = False, "", []
        if item["format"] == "PDF":
            error = self.pdf.load(item["path"])
            if error not in (QPdfDocument.Error.None_, QPdfDocument.Error.IncorrectPassword):
                raise OSError(tr("Cannot open PDF: {error}", error=error.name))
            self.pdf_page = max(0, min(self.pdf.pageCount() - 1, self.position.get("page", 0)))
            self.pdf_zoom = max(0.8, min(2.0, self.position.get("zoom", 1.0)))
            self.pdf_fit = self.position.get("fit", True)
            self.pdf_x, self.pdf_y = self.position.get("x", 0), self.position.get("y", 0)
            self.pdf_revision += 1
            self.reader_ready = self.pdf.status() == QPdfDocument.Status.Ready
        else:
            self.book = BookServer(item, self.position, self.style_preferences())
            self.reader_url = self.book.url
        self.enter("document")
        self.store.remember(identifier)
        self.persist()
        self.pdfMoved.emit()
        self.publish()

    def password_required(self):
        self.prompt(tr("PDF password"), self.unlock_pdf, body=(self.current or {}).get("title", ""))

    def unlock_pdf(self, text):
        self.library.require(self.current["id"])
        self.pdf.setPassword(text)
        error = self.pdf.load(self.current["path"])
        if error != QPdfDocument.Error.None_:
            raise ValueError(tr("Incorrect PDF password"))
        self.reader_ready = True
        self.pdf_revision += 1

    def extra_state(self):
        return {"readerUrl": self.reader_url, "readerReady": self.reader_ready,
                "readerLabel": self.reader_label, "position": self.position,
                "fontSize": self.font_size, "lineHeight": self.line_height,
                "fontFamily": self.font_family, "background": self.background,
                "backgroundColor": READER_BACKGROUNDS[self.background]["background"],
                "contentWidth": self.content_width, "dark": self.dark,
                "pdfPage": self.pdf_page, "pdfPages": self.pdf.pageCount(),
                "pdfZoom": self.pdf_zoom, "pdfFit": self.pdf_fit,
                "pdfX": self.pdf_x, "pdfY": self.pdf_y, "pdfRevision": self.pdf_revision,
                "pdfHighlights": self.pdf_highlights,
                "pdfRatio": self.pdf_ratio()}

    def pdf_ratio(self):
        if self.pdf.status() != QPdfDocument.Status.Ready:
            return 1.4
        size = self.pdf.pagePointSize(self.pdf_page)
        return size.height() / max(1, size.width())

    @Slot(str)
    def readerConsole(self, message):
        self.reader_log = (self.reader_log + [message])[-50:]

    @Slot(str)
    def readerEvent(self, payload):
        try:
            data = json.loads(payload)
            if not self.book or data.get("session") != self.book.token or self.page != "document":
                return
            event = data.get("type")
            if event == "ready":
                self.contents = data.get("toc", [])
                self.reader_ready = True
            elif event == "position":
                self.position = {"cfi": data["cfi"], "fraction": data.get("fraction", 0)}
                self.reader_label = data.get("label", "")
                self.save_position()
            elif event == "search":
                self.search_results = data.get("results", [])
                self.show_results()
            elif event == "error":
                self.error = tr("Reading failed: {error}", error=data.get("error", ""))
            elif event == "external":
                url = data.get("url", "")
                self.menu(tr("External link"), [(tr("Open in browser"), lambda: self.open_external(url)),
                                                  (tr("Cancel"), self.pop_menu)], url)
            self.publish()
        except (ValueError, KeyError, TypeError):
            return

    def open_external(self, url):
        import subprocess
        import sys

        from .web import address_url

        subprocess.Popen([sys.executable, "-m", "udeck.apps.main", "browser", address_url(url)], start_new_session=True)
        self.pop_menu()

    def send_reader(self, action, value=None):
        if self.book and self.reader_ready:
            self.webAction.emit(action, json.dumps({"value": value, "session": self.book.token}))

    def style_preferences(self):
        return {"fontSize": self.font_size, "lineHeight": self.line_height,
                "fontFamily": self.font_family, "background": self.background,
                "contentWidth": self.content_width, "dark": self.dark}

    def save_position(self):
        if not self.current:
            return
        if self.current["format"] == "PDF" and self.pdf.status() == QPdfDocument.Status.Ready:
            self.position = {"page": self.pdf_page, "zoom": self.pdf_zoom, "fit": self.pdf_fit,
                             "x": self.pdf_x, "y": self.pdf_y,
                             "fraction": (self.pdf_page + 1) / max(1, self.pdf.pageCount())}
        self.store.data["positions"][self.current["id"]] = dict(self.position)

    @Slot(float, float)
    def pdfPan(self, x, y):
        if math.isfinite(x) and math.isfinite(y):
            self.pdf_x, self.pdf_y = max(0, x), max(0, y)

    def poll(self):
        super().poll()
        self.ticks += 1
        if self.ticks % 5 == 0:
            self.save_position()
            self.attempt(self.persist)

    @Slot(str)
    @interaction
    def dispatch(self, action):
        if self.menus or self.page != "document" or action in ("context", "quick-settings", "back"):
            return super().dispatch(action)
        if action == "accept":
            self.contents_menu()
        elif self.current and self.current["format"] == "PDF":
            if action in ("previous-tab", "next-tab"):
                self.turn_pdf(self.pdf_page + (-1 if action == "previous-tab" else 1))
            elif action in ("left", "right", "up", "down"):
                self.webAction.emit("pan", json.dumps({"direction": action}))
        elif action in ("left", "previous-tab", "right", "next-tab"):
            self.send_reader("previous" if action in ("left", "previous-tab") else "next")
        elif action in ("up", "down"):
            self.send_reader("scroll", -120 if action == "up" else 120)
        self.publish()

    def turn_pdf(self, index):
        if 0 <= index < self.pdf.pageCount():
            self.pdf_page, self.pdf_x, self.pdf_y = index, 0, 0
            self.pdf_highlights = []
            self.pdf_revision += 1
            self.save_position()
            self.pdfMoved.emit()
            self.publish()

    def back(self):
        if self.page == "document":
            self.save_position()
            self.persist()
            self.close_document()
        super().back()

    def context(self):
        if self.page != "document":
            return super().context()
        self.menu(tr("Reading actions"), [
            (tr("Contents"), self.contents_menu),
            (tr("Reading layout"), self.layout_menu),
            (tr("Bookmark this position"), self.add_bookmark),
            (tr("Bookmarks"), self.bookmarks_menu),
            (tr("Go to page / percentage"), lambda: self.prompt(tr("Go to page / percentage"), self.jump,
                body=tr("PDF: page number. EPUB / TXT: 0–100 percent."))),
            (tr("Find in book"), lambda: self.prompt(tr("Find in book"), self.search_book, self.search_query)),
            (tr("Clear search"), self.clear_search)])

    def contents_menu(self):
        if self.current and self.current["format"] == "PDF":
            entries = []
            def walk(parent=None, depth=0):
                parent = parent or QModelIndex()
                for i in range(self.pdf_toc.rowCount(parent)):
                    index = self.pdf_toc.index(i, 0, parent)
                    title = self.pdf_toc.data(index, QPdfBookmarkModel.Role.Title)
                    page = self.pdf_toc.data(index, QPdfBookmarkModel.Role.Page)
                    entries.append(("  " * depth + str(title), lambda p=page: self.goto_position({"page": p})))
                    walk(index, depth + 1)
            walk()
        else:
            entries = [("  " * e.get("depth", 0) + e["title"],
                        lambda href=e["href"]: self.goto_position({"cfi": href})) for e in self.contents]
        self.menu(tr("Contents"), entries)

    def goto_position(self, position):
        self.library.require(self.current["id"])
        if self.current["format"] == "PDF":
            self.turn_pdf(position["page"])
            self.pdf_highlights = position.get("highlights", [])
        else:
            self.send_reader("goto", position["cfi"])
        self.clear_menus()
        self.publish()

    def add_bookmark(self):
        self.save_position()
        if self.current["format"] != "PDF" and not self.position.get("cfi"):
            raise ValueError(tr("Wait until the document is ready"))
        bookmarks = self.store.data["bookmarks"].setdefault(self.current["id"], [])
        label = (tr("Page {page}", page=self.pdf_page + 1) if self.current["format"] == "PDF"
                 else self.reader_label or f"{self.position.get('fraction', 0):.0%}")
        bookmarks.append({"label": str(label), "position": dict(self.position)})
        self.persist()
        self.pop_menu()

    def bookmarks_menu(self):
        entries = self.store.data["bookmarks"].get(self.current["id"], [])
        self.menu(tr("Bookmarks"), [(e["label"], lambda e=e: self.bookmark_actions(e)) for e in entries])

    def bookmark_actions(self, entry):
        self.menu(entry["label"], [(tr("Open"), lambda: self.goto_position(entry["position"])),
                                    (tr("Remove"), lambda: self.remove_bookmark(entry))])

    def remove_bookmark(self, entry):
        self.store.data["bookmarks"][self.current["id"]].remove(entry)
        self.persist()
        self.pop_menu()
        self.pop_menu()
        self.bookmarks_menu()

    def jump(self, text):
        number = float(text)
        if not math.isfinite(number):
            raise ValueError(tr("Enter a finite number"))
        if self.current["format"] == "PDF":
            if number != int(number) or not 1 <= number <= self.pdf.pageCount():
                raise ValueError(tr("Enter a page between 1 and {pages}", pages=self.pdf.pageCount()))
            self.turn_pdf(int(number) - 1)
        else:
            if not 0 <= number <= 100:
                raise ValueError(tr("Enter a percentage between 0 and 100"))
            self.send_reader("fraction", number / 100)
        self.clear_menus()

    def search_book(self, text):
        if not text.strip():
            raise ValueError(tr("Enter search text"))
        self.search_query, self.search_results = text, []
        self.search_generation += 1
        self.notice = tr("Searching…")
        if self.current["format"] != "PDF":
            self.send_reader("search", text)
            return
        generation = self.search_generation
        def chunk(page=0):
            if generation != self.search_generation or self.page != "document":
                return
            if page >= self.pdf.pageCount() or len(self.search_results) >= 200:
                self.show_results()
                return
            content = self.pdf.getAllText(page).text()
            points = self.pdf.pagePointSize(page)
            for match in re.finditer(re.escape(text), content, re.I):
                selection = self.pdf.getSelectionAtIndex(page, match.start(), len(match.group()))
                boxes = [{"x": box.x() / points.width(), "y": box.y() / points.height(),
                          "width": box.width() / points.width(), "height": box.height() / points.height()}
                         for polygon in selection.bounds() for box in [polygon.boundingRect()]]
                self.search_results.append({"page": page, "title": content[max(0, match.start()-40):match.end()+70],
                                            "highlights": boxes})
                if len(self.search_results) >= 200:
                    break
            QTimer.singleShot(0, lambda: chunk(page + 1))
        QTimer.singleShot(0, chunk)

    def clear_search(self):
        self.search_generation += 1
        self.search_results, self.pdf_highlights = [], []
        self.send_reader("clear")
        self.pop_menu()

    def show_results(self):
        self.notice = ""
        if not self.search_results:
            self.prompt(tr("No matches. Try another search"), self.search_book, self.search_query)
        else:
            self.menu(tr("Search results"), [(e["title"], lambda e=e: self.goto_position(e))
                                               for e in self.search_results])
        self.publish()

    def settings_options(self):
        options = [(tr("Night colors"), self.toggle_dark),
                   (tr("Reading layout"), self.layout_menu)]
        if self.current and self.current["format"] == "PDF" and self.page == "document":
            options.append((tr("PDF zoom"), self.zoom_menu))
        else:
            options.append((tr("Text size: {size}", size=self.font_size), self.font_menu))
        return options

    def toggle_dark(self):
        self.set_background("paper" if self.dark else "night")

    def font_menu(self):
        self.menu(tr("Text size"), [(str(size), lambda size=size: self.set_font(size))
                                     for size in READER_FONT_SIZES])

    def set_font(self, size):
        self.font_size = size
        self.send_style()
        self.pop_menu()

    def layout_menu(self):
        options = []
        pdf_document = self.page == "document" and self.current and self.current.get("format") == "PDF"
        if not pdf_document:
            options.extend([(tr("Line spacing"), self.line_height_menu),
                            (tr("Font"), self.font_family_menu),
                            (tr("Content width"), self.content_width_menu)])
        options.append((tr("Background"), self.background_menu))
        self.menu(tr("Reading layout"), options)

    def line_height_menu(self):
        self.menu(tr("Line spacing"), [(f"{value:.1f}×", lambda value=value: self.set_line_height(value))
                                       for value in READER_LINE_HEIGHTS])

    def set_line_height(self, value):
        if value not in READER_LINE_HEIGHTS:
            return
        self.line_height = value
        self.send_style()
        self.pop_menu()

    def font_family_menu(self):
        self.menu(tr("Font"), [(tr("Sans-serif"), lambda: self.set_font_family("sans")),
                                (tr("Serif"), lambda: self.set_font_family("serif")),
                                (tr("Monospace"), lambda: self.set_font_family("mono"))])

    def set_font_family(self, family):
        if family not in READER_FONT_FAMILIES:
            return
        self.font_family = family
        self.send_style()
        self.pop_menu()

    def content_width_menu(self):
        labels = {720: "Narrow ({width}px)", 1000: "Standard ({width}px)", 1200: "Wide ({width}px)"}
        self.menu(tr("Content width"), [(tr(labels[width], width=width),
                                         lambda width=width: self.set_content_width(width))
                                        for width in READER_CONTENT_WIDTHS])

    def set_content_width(self, width):
        if width not in READER_CONTENT_WIDTHS:
            return
        self.content_width = width
        self.send_style()
        self.pop_menu()

    def background_menu(self):
        self.menu(tr("Background"), [(tr("Paper"), lambda: self.set_background("paper")),
                                     (tr("Warm paper"), lambda: self.set_background("warm")),
                                     (tr("Gray"), lambda: self.set_background("gray")),
                                     (tr("Night"), lambda: self.set_background("night"))])

    def set_background(self, background):
        if background not in READER_BACKGROUNDS:
            return
        self.background = background
        self.dark = READER_BACKGROUNDS[background]["dark"]
        self.send_style()
        self.pop_menu()

    def send_style(self):
        preferences = self.style_preferences()
        self.store.data["preferences"].update(preferences)
        self.send_reader("style", preferences)
        self.persist()

    def zoom_menu(self):
        self.menu(tr("PDF zoom"), [(tr("Fit width"), lambda: self.set_zoom(1, True))] + [
            (f"{z:.0%}", lambda z=z: self.set_zoom(z, False)) for z in (0.8, 1, 1.25, 1.5, 2)])

    def set_zoom(self, zoom, fit):
        self.pdf_zoom, self.pdf_fit = zoom, fit
        self.pdf_revision += 1
        self.pop_menu()

    def persist(self):
        self.store.data["preferences"].update(self.style_preferences())
        super().persist()

    def close_document(self):
        self.search_generation += 1
        if self.book:
            self.book.close()
            self.book = None
        self.reader_url = ""
        self.reader_ready = False
        self.search_query, self.search_results = "", []
        self.notice = ""
        self.pdf_highlights = []
        self.pdf.close()

    def stop_source(self):
        self.save_position()
        self.attempt(self.persist)
        self.close_document()

    def close(self):
        self.save_position()
        super().close()
        self.close_document()
