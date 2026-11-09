import base64
import os
import stat
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QSize, Qt
from PySide6.QtGui import QImageReader

from .files import FileOperations, file_kind
from .i18n import tr


def read_regular(path, limit):
    before = path.lstat()
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as reader:
        information = os.fstat(reader.fileno())
        if not stat.S_ISREG(information.st_mode) or (information.st_dev, information.st_ino) != (before.st_dev, before.st_ino):
            raise ValueError(tr("File changed; refresh before previewing."))
        return reader.read(limit + 1)


def preview(path, name=None):
    path = Path(path)
    information = path.lstat()
    directory = stat.S_ISDIR(information.st_mode)
    kind, mime, icon = file_kind(name or path.name, directory)
    result = {"kind": "file-preview", "title": name or path.name, "path": str(path), "previewType": "metadata",
              "mime": mime, "icon": icon, "truncated": False,
              "body": str(path) + "\n" + mime + " · " + FileOperations.format_size(information.st_size)
              + "\n" + datetime.fromtimestamp(information.st_mtime).strftime("%Y-%m-%d %H:%M")}
    if stat.S_ISLNK(information.st_mode):
        result["linkTarget"] = os.readlink(path)
        result["body"] += "\n" + tr("Link target: {path}", path=result["linkTarget"])
    elif stat.S_ISREG(information.st_mode) and kind == "text":
        data = read_regular(path, 65536)
        if b"\x00" not in data:
            result.update(previewType="text", previewText=data[:65536].decode("utf-8", errors="replace"),
                          truncated=len(data) > 65536)
    elif stat.S_ISREG(information.st_mode) and kind == "image" and mime != "image/svg+xml" and information.st_size <= 8 * 1024 * 1024:
        data = read_regular(path, 8 * 1024 * 1024)
        buffer = QBuffer()
        buffer.setData(QByteArray(data))
        buffer.open(QIODevice.OpenModeFlag.ReadOnly)
        reader = QImageReader(buffer)
        dimensions = reader.size()
        if len(data) <= 8 * 1024 * 1024 and dimensions.isValid() and dimensions.width() * dimensions.height() <= 12_000_000:
            reader.setAutoTransform(True)
            reader.setScaledSize(dimensions.scaled(QSize(840, 420), Qt.AspectRatioMode.KeepAspectRatio))
            image = reader.read()
            if not image.isNull():
                if image.width() > 840 or image.height() > 420:
                    image = image.scaled(QSize(840, 420), Qt.AspectRatioMode.KeepAspectRatio,
                                         Qt.TransformationMode.SmoothTransformation)
                encoded = QBuffer()
                encoded.open(QIODevice.OpenModeFlag.WriteOnly)
                if image.save(encoded, "PNG"):
                    result.update(previewType="image", previewImage="data:image/png;base64," + base64.b64encode(bytes(encoded.data())).decode())
    return result
