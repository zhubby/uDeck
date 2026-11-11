"""Shared desktop theme icons and uDeck's native fallback artwork."""

import hashlib
import math
from urllib.parse import unquote

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QImage, QImageReader, QPainter, QPainterPath, QPen
from PySide6.QtQuick import QQuickImageProvider

from .file_icons import FILE_ICON_PREFIX, FILE_ICON_ROOT, ICON_PALETTES, ICON_SPECS


class IconProvider(QQuickImageProvider):
    def __init__(self):
        super().__init__(QQuickImageProvider.ImageType.Image)

    def requestImage(self, identifier, size, requested_size):
        name = unquote(identifier)
        dimension = max(48, min(160, requested_size.width() if requested_size.width() > 0 else 80))
        if name.startswith(FILE_ICON_PREFIX):
            image = self._draw_file(name, dimension)
        else:
            icon = QIcon(name) if name.startswith("/") else QIcon.fromTheme(name)
            image = icon.pixmap(QSize(dimension, dimension)).toImage() if not icon.isNull() else self._draw(name, dimension)
        size.setWidth(image.width())
        size.setHeight(image.height())
        return image

    def _draw_file(self, name, dimension):
        asset, palette = ICON_SPECS.get(name.removeprefix(FILE_ICON_PREFIX), ICON_SPECS["unknown"])
        background, foreground = ICON_PALETTES[palette]
        try:
            data = (FILE_ICON_ROOT / (asset + ".svg")).read_bytes().replace(b"currentColor", foreground.encode())
        except OSError:
            return self._draw("text-x-generic", dimension)
        buffer = QBuffer()
        buffer.setData(QByteArray(data))
        buffer.open(QIODevice.OpenModeFlag.ReadOnly)
        reader = QImageReader(buffer, b"svg")
        glyph_size = round(dimension * 0.7)
        reader.setScaledSize(QSize(glyph_size, glyph_size))
        glyph = reader.read()
        if glyph.isNull():
            return self._draw("text-x-generic", dimension)
        image = QImage(dimension, dimension, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(background))
        inset = dimension / 64
        painter.drawRoundedRect(QRectF(inset, inset, dimension - 2 * inset, dimension - 2 * inset),
                                dimension * 0.2, dimension * 0.2)
        margin = (dimension - glyph_size) / 2
        painter.drawImage(QRectF(margin, margin, glyph_size, glyph_size), glyph)
        painter.end()
        return image

    def _draw(self, name, dimension):
        image = QImage(dimension, dimension, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.scale(dimension / 64, dimension / 64)
        painter.setPen(Qt.PenStyle.NoPen)
        shades = ["#394b4d", "#4e4233", "#3d4658", "#4b4351", "#3e4d41"]
        painter.setBrush(QColor(shades[hashlib.sha256(name.encode()).digest()[0] % len(shades)]))
        painter.drawRoundedRect(1, 1, 62, 62, 13, 13)
        painter.setPen(QPen(QColor("#ead7b2"), 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        if self._draw_setting(painter, name):
            pass
        elif "folder" in name or "file-manager" in name:
            painter.drawLine(14, 22, 14, 46)
            painter.drawLine(14, 46, 50, 46)
            painter.drawLine(50, 46, 50, 25)
            painter.drawLine(50, 25, 32, 25)
            painter.drawLine(32, 25, 27, 19)
            painter.drawLine(27, 19, 14, 19)
            painter.drawLine(14, 19, 14, 22)
            if name == "folder-new":
                painter.drawLine(32, 30, 32, 40)
                painter.drawLine(27, 35, 37, 35)
        elif "terminal" in name:
            painter.drawLine(16, 21, 27, 31)
            painter.drawLine(27, 31, 16, 41)
            painter.drawLine(34, 43, 48, 43)
        elif "code" in name or "geany" in name:
            painter.drawLine(24, 21, 14, 32)
            painter.drawLine(14, 32, 24, 43)
            painter.drawLine(40, 21, 50, 32)
            painter.drawLine(50, 32, 40, 43)
            painter.drawLine(36, 17, 28, 47)
        elif any(term in name for term in ("game", "retro", "libretro")):
            painter.drawRoundedRect(11, 20, 42, 27, 9, 9)
            painter.drawLine(18, 33, 30, 33)
            painter.drawLine(24, 27, 24, 39)
            painter.drawEllipse(40, 28, 3, 3)
            painter.drawEllipse(46, 35, 3, 3)
        elif "grid" in name:
            for horizontal in (16, 36):
                for vertical in (16, 36):
                    painter.drawRoundedRect(horizontal, vertical, 13, 13, 2, 2)
        elif name == "audio-x-generic":
            painter.drawLine(27, 20, 47, 15)
            painter.drawLine(27, 20, 27, 43)
            painter.drawLine(47, 15, 47, 38)
            painter.drawEllipse(15, 39, 12, 9)
            painter.drawEllipse(35, 34, 12, 9)
        elif name == "video-x-generic":
            painter.drawRoundedRect(12, 16, 40, 32, 4, 4)
            painter.drawLine(28, 24, 40, 32)
            painter.drawLine(40, 32, 28, 40)
            painter.drawLine(28, 40, 28, 24)
        elif name == "image-x-generic":
            painter.drawRoundedRect(12, 15, 40, 34, 4, 4)
            painter.drawEllipse(20, 22, 6, 6)
            painter.drawLine(14, 44, 29, 31)
            painter.drawLine(29, 31, 38, 39)
            painter.drawLine(38, 39, 44, 33)
            painter.drawLine(44, 33, 51, 42)
        elif name in ("application-pdf", "accessories-ebook-reader"):
            painter.drawRoundedRect(13, 16, 38, 34, 3, 3)
            painter.drawLine(32, 17, 32, 49)
            painter.drawLine(19, 25, 26, 25)
            painter.drawLine(38, 25, 45, 25)
            painter.drawLine(19, 34, 26, 34)
            painter.drawLine(38, 34, 45, 34)
        elif name == "package-x-generic":
            painter.drawRoundedRect(16, 13, 32, 38, 3, 3)
            for vertical in (20, 27, 34):
                painter.drawLine(29, vertical, 35, vertical)
            painter.drawRect(29, 41, 6, 5)
        elif name == "user-trash":
            painter.drawLine(15, 20, 49, 20)
            painter.drawLine(25, 13, 39, 13)
            painter.drawLine(19, 22, 22, 49)
            painter.drawLine(22, 49, 42, 49)
            painter.drawLine(42, 49, 45, 22)
            painter.drawLine(28, 28, 29, 42)
            painter.drawLine(36, 28, 35, 42)
        elif name in ("drive-harddisk", "drive-removable-media"):
            painter.drawRoundedRect(14, 14, 36, 36, 5, 5)
            painter.drawLine(15, 38, 49, 38)
            painter.drawEllipse(38, 43, 3, 3)
        elif any(term in name for term in ("preferences", "brightness", "audio")):
            for horizontal, vertical in ((20, 24), (32, 39), (44, 28)):
                painter.drawLine(horizontal, 15, horizontal, 49)
                painter.fillRect(horizontal - 4, vertical - 4, 8, 8, QColor("#ead7b2"))
        elif "wireless" in name or "firefox" in name:
            painter.drawEllipse(15, 15, 34, 34)
            painter.drawLine(32, 18, 32, 46)
            painter.drawLine(18, 32, 46, 32)
            painter.drawEllipse(24, 15, 16, 34)
        elif "go-home" in name or name == "user-home":
            painter.drawLine(13, 29, 32, 14)
            painter.drawLine(32, 14, 51, 29)
            painter.drawLine(19, 25, 19, 49)
            painter.drawLine(19, 49, 45, 49)
            painter.drawLine(45, 49, 45, 25)
            painter.drawRect(28, 36, 9, 13)
        else:
            painter.drawRoundedRect(17, 13, 30, 38, 3, 3)
            painter.drawLine(24, 25, 40, 25)
            painter.drawLine(24, 33, 40, 33)
            painter.drawLine(24, 41, 34, 41)
        painter.end()
        return image

    @staticmethod
    def _draw_setting(painter, name):
        """Use the same rounded tile, warm ink and line weight as the shell."""
        def line(*points):
            path = QPainterPath()
            path.moveTo(*points[0])
            for point in points[1:]:
                path.lineTo(*point)
            painter.drawPath(path)

        if name in ("zoom-in", "zoom-out"):
            painter.drawEllipse(14, 12, 28, 28)
            line((38, 36), (51, 49))
            line((21, 26), (35, 26))
            if name == "zoom-in":
                line((28, 19), (28, 33))
        elif name in ("preferences-desktop-font", "format-text-size"):
            line((15, 19), (43, 19))
            line((29, 19), (29, 47))
            line((22, 47), (36, 47))
            if name == "format-text-size":
                line((47, 28), (47, 47))
                line((43, 32), (47, 28), (51, 32))
        elif name == "format-line-spacing":
            for y in (21, 32, 43):
                line((29, y), (50, y))
            line((17, 18), (17, 46))
            line((12, 23), (17, 18), (22, 23))
            line((12, 41), (17, 46), (22, 41))
        elif name in ("zoom-fit-width", "view-fullscreen"):
            line((14, 20), (14, 44))
            line((50, 20), (50, 44))
            line((21, 32), (43, 32))
            line((26, 27), (21, 32), (26, 37))
            line((38, 27), (43, 32), (38, 37))
        elif name == "document-page-setup":
            painter.drawRoundedRect(16, 12, 32, 40, 3, 3)
            for y in (23, 32, 41):
                line((23, y), (41, y))
        elif name == "weather-clear-night":
            moon = QPainterPath()
            moon.addEllipse(14, 13, 36, 38)
            cutout = QPainterPath()
            cutout.addEllipse(27, 6, 32, 34)
            painter.drawPath(moon.subtracted(cutout))
        elif name in ("weather-clear", "display-brightness"):
            painter.drawEllipse(23, 23, 18, 18)
            for angle in range(0, 360, 45):
                a = math.radians(angle)
                line((32 + 16 * math.cos(a), 32 + 16 * math.sin(a)),
                     (32 + 22 * math.cos(a), 32 + 22 * math.sin(a)))
        elif name in ("preferences-desktop-wallpaper", "preferences-desktop-theme"):
            painter.drawRoundedRect(12, 14, 40, 35, 4, 4)
            painter.drawEllipse(20, 21, 7, 7)
            line((14, 44), (28, 32), (37, 40), (44, 33), (51, 40))
        elif name in ("audio-card", "audio-headphones"):
            painter.drawArc(15, 14, 34, 38, 0, 180 * 16)
            painter.drawRoundedRect(14, 31, 9, 18, 3, 3)
            painter.drawRoundedRect(41, 31, 9, 18, 3, 3)
        elif name in ("audio-volume-high", "audio-volume-muted"):
            line((14, 26), (22, 26), (33, 17), (33, 47), (22, 38), (14, 38), (14, 26))
            if name == "audio-volume-muted":
                line((41, 27), (51, 37))
                line((51, 27), (41, 37))
            else:
                painter.drawArc(30, 23, 16, 18, -60 * 16, 120 * 16)
                painter.drawArc(28, 16, 28, 32, -60 * 16, 120 * 16)
        elif name in ("audio-input-microphone", "microphone-sensitivity-muted"):
            painter.drawRoundedRect(26, 12, 12, 27, 6, 6)
            painter.drawArc(19, 24, 26, 23, 180 * 16, 180 * 16)
            line((32, 47), (32, 53))
            line((24, 53), (40, 53))
            if name == "microphone-sensitivity-muted":
                line((14, 15), (50, 51))
        elif name in ("input-keyboard", "preferences-desktop-keyboard"):
            painter.drawRoundedRect(11, 19, 42, 29, 4, 4)
            for y in (26, 33):
                for x in (19, 28, 37, 46):
                    line((x, y), (x + 1, y))
            line((22, 41), (42, 41))
        elif name == "input-mouse":
            painter.drawRoundedRect(21, 12, 22, 40, 10, 10)
            line((21, 28), (43, 28))
            line((32, 13), (32, 28))
        elif name == "insert-link":
            painter.save()
            painter.translate(32, 32)
            painter.rotate(-40)
            painter.drawRoundedRect(-21, -7, 26, 14, 7, 7)
            painter.drawRoundedRect(-5, -7, 26, 14, 7, 7)
            painter.restore()
        elif name in ("network-wireless", "network-connect", "network-disconnect"):
            for x, y, w, h in ((12, 15, 40, 40), (20, 24, 24, 24)):
                painter.drawArc(x, y, w, h, 45 * 16, 90 * 16)
            painter.drawEllipse(30, 40, 4, 4)
            if name == "network-disconnect":
                line((17, 17), (49, 49))
            elif name == "network-connect":
                line((40, 41), (45, 46), (53, 36))
        elif name == "bluetooth":
            line((31, 12), (44, 23), (21, 43))
            line((21, 21), (44, 41), (31, 52), (31, 12))
        elif name == "battery":
            painter.drawRoundedRect(13, 22, 36, 23, 3, 3)
            line((53, 28), (53, 38))
            line((20, 29), (20, 38))
            line((27, 29), (27, 38))
            line((34, 29), (34, 38))
        elif name == "preferences-system-time":
            painter.drawEllipse(13, 13, 38, 38)
            line((32, 20), (32, 32), (41, 37))
        elif name == "preferences-desktop-locale":
            painter.drawEllipse(13, 13, 38, 38)
            painter.drawEllipse(24, 13, 16, 38)
            line((15, 25), (49, 25))
            line((15, 39), (49, 39))
        elif name in ("system-lock-screen", "dialog-password"):
            painter.drawArc(23, 11, 18, 27, 0, 180 * 16)
            painter.drawRoundedRect(17, 27, 30, 25, 4, 4)
            line((32, 36), (32, 43))
        elif name in ("video-display", "preferences-system-windows"):
            painter.drawRoundedRect(12, 15, 40, 29, 3, 3)
            line((32, 44), (32, 51))
            line((23, 51), (41, 51))
        elif name == "system-shutdown":
            painter.drawArc(14, 14, 36, 38, 135 * 16, 270 * 16)
            line((32, 11), (32, 32))
        elif name in ("view-refresh", "system-reboot", "media-playlist-repeat"):
            painter.drawArc(14, 14, 36, 36, 45 * 16, 290 * 16)
            line((40, 14), (47, 14), (47, 23))
        elif name == "system-log-out":
            line((27, 14), (15, 14), (15, 50), (27, 50))
            line((27, 32), (51, 32))
            line((43, 24), (51, 32), (43, 40))
        elif name in ("window-close", "process-stop"):
            line((20, 20), (44, 44))
            line((44, 20), (20, 44))
        elif name in ("go-previous", "go-up"):
            if name == "go-up":
                line((19, 31), (32, 18), (45, 31))
                line((32, 18), (32, 48))
            else:
                line((31, 19), (18, 32), (31, 45))
                line((18, 32), (48, 32))
        elif name == "emblem-default":
            line((17, 33), (27, 43), (48, 21))
        elif name == "list-add":
            line((17, 32), (47, 32))
            line((32, 17), (32, 47))
        elif name == "media-playback-start":
            line((23, 16), (48, 32), (23, 48), (23, 16))
        elif name == "media-playback-stop":
            painter.drawRoundedRect(20, 20, 24, 24, 2, 2)
        elif name == "applications-system":
            painter.drawRoundedRect(21, 21, 22, 22, 3, 3)
            for n in (26, 37):
                line((n, 14), (n, 21))
                line((n, 43), (n, 50))
                line((14, n), (21, n))
                line((43, n), (50, n))
        elif name == "document-edit":
            line((18, 39), (39, 18), (46, 25), (25, 46), (16, 48), (18, 39), (25, 46))
        elif name == "edit-delete":
            line((17, 21), (47, 21))
            line((26, 15), (38, 15))
            line((21, 23), (24, 49), (40, 49), (43, 23))
            line((28, 29), (29, 42))
            line((36, 29), (35, 42))
        elif name == "edit-find":
            painter.drawEllipse(14, 12, 28, 28)
            line((38, 36), (51, 49))
        elif name in ("dialog-information", "dialog-warning"):
            painter.drawEllipse(13, 13, 38, 38)
            if name == "dialog-information":
                line((32, 28), (32, 43))
                painter.drawEllipse(31, 20, 2, 2)
            else:
                line((32, 21), (32, 35))
                painter.drawEllipse(31, 41, 2, 2)
        else:
            return False
        return True
