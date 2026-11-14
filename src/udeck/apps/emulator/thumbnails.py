"""Libretro thumbnail lookup and cancellable, non-overwriting HTTP downloads."""

import os
import re
import tempfile
from collections import deque
from pathlib import Path
from urllib.parse import quote

from PySide6.QtCore import QObject, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QImage
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

from udeck.i18n import Msg, tr

from .playlists import database_name

KINDS = ("Named_Boxarts", "Named_Snaps", "Named_Titles")


def thumbnail_names(item):
    filename = item.get("basename") or Path(item.get("archiveMember") or item.get("path", "")).stem
    title = str(item.get("title") or filename)
    names = []
    for name in (filename, title, title.split("(", 1)[0].rstrip()):
        name = re.sub(r'[&*/:`<>?\\|]', "_", name).replace("\x00", "_")
        if name and name not in {".", ".."} and name not in names:
            names.append(name)
    return names


def thumbnail_folder(root, database, kind):
    database = database_name(database)
    if not database or kind not in KINDS:
        return None
    root = Path(root)
    directory = root / database / kind
    if any(p.is_symlink() for p in (root, root / database, directory)):
        return None
    return directory


def find_thumbnails(item, root):
    images = {}
    for kind in KINDS:
        directory = thumbnail_folder(root, item.get("dbName"), kind)
        if directory is None:
            continue
        for name in thumbnail_names(item):
            found = next((directory / (name + suffix) for suffix in (".png", ".jpg", ".jpeg", ".bmp", ".tga")
                          if (directory / (name + suffix)).is_file()
                          and not (directory / (name + suffix)).is_symlink()), None)
            if found:
                images[kind] = found.absolute().as_uri()
                break
    return images


def apply_thumbnails(item, root, preferred="Named_Boxarts"):
    images = find_thumbnails(item, root)
    item["thumbnails"] = images
    item["cover"] = next((images[k] for k in (preferred, *KINDS) if k in images), "")


class ThumbnailDownloader(QObject):
    changed = Signal()
    finished = Signal()

    def __init__(self, parent=None, *, base_url="https://thumbnails.libretro.com/", timeout=15000):
        super().__init__(parent)
        self.network = QNetworkAccessManager(self)
        self.base_url, self.timeout = base_url.rstrip("/") + "/", timeout
        self.active, self.queue = {}, deque()
        self.running = False
        self.status = {}

    def start(self, items, root):
        self.cancel()
        self.status = {"total": 0, "done": 0, "saved": 0, "missing": 0, "failed": 0,
                       "cancelled": False, "errors": []}
        seen = set()
        for item in items:
            existing = find_thumbnails(item, root)
            for kind in KINDS:
                directory = thumbnail_folder(root, item.get("dbName"), kind)
                names = thumbnail_names(item)
                if directory is None or not names or kind in existing:
                    continue
                key = (str(directory), tuple(names))
                if key in seen:
                    continue
                seen.add(key)
                self.queue.append({"item": dict(item), "root": Path(root), "kind": kind,
                                   "directory": directory, "names": deque(names)})
        self.status["total"] = len(self.queue)
        self.running = True
        self.changed.emit()
        QTimer.singleShot(0, self._pump)

    def cancel(self):
        was_running = self.running
        self.running = False
        self.queue.clear()
        if self.status and was_running:
            self.status["cancelled"] = True
        for reply in list(self.active):
            reply.abort()
        self.active.clear()
        if was_running:
            self.finished.emit()
        self.changed.emit()

    def _pump(self):
        if not self.running:
            return
        while self.queue and len(self.active) < 2:
            job = self.queue.popleft()
            if job["kind"] in find_thumbnails(job["item"], job["root"]):
                self.status["done"] += 1
                continue
            name = job["names"].popleft()
            job["target"] = job["directory"] / (name + ".png")
            relative = "/".join(quote(part, safe="") for part in
                                (job["item"]["dbName"], job["kind"], name + ".png"))
            request = QNetworkRequest(QUrl(self.base_url + relative))
            request.setTransferTimeout(self.timeout)
            request.setRawHeader(b"User-Agent", b"uDeck thumbnail downloader")
            reply = self.network.get(request)
            self.active[reply] = job
            reply.finished.connect(self._received)
            reply.readyRead.connect(self._read)
        self.changed.emit()
        if not self.queue and not self.active:
            self.running = False
            self.finished.emit()
            self.changed.emit()

    @Slot()
    def _read(self, reply=None):
        reply = reply if reply is not None else self.sender()
        job = self.active.get(reply)
        if job is not None:
            job.setdefault("data", bytearray()).extend(bytes(reply.readAll()))
            if len(job["data"]) > 16 * 1024 * 1024:
                reply.abort()

    @Slot()
    def _received(self):
        reply = self.sender()
        self._read(reply)
        job = self.active.pop(reply, None)
        if job is None or not self.running:
            reply.deleteLater()
            return
        status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
        error = reply.error()
        message = reply.errorString()
        reply.deleteLater()
        if status == 404 and job["names"]:
            job.pop("data", None)
            self.queue.appendleft(job)
        else:
            self.status["done"] += 1
            if status == 404:
                self.status["missing"] += 1
            elif status == 200 and error == QNetworkReply.NetworkError.NoError:
                try:
                    data = bytes(job.get("data", b""))
                    if len(data) > 16 * 1024 * 1024 or QImage.fromData(data).isNull():
                        raise ValueError(tr(Msg.EMU_IMAGE_INVALID))
                    if self._publish(job, data):
                        self.status["saved"] += 1
                except (OSError, ValueError) as failure:
                    self._failure(job, str(failure))
            else:
                self._failure(job, message)
        self._pump()

    def _failure(self, job, error):
        self.status["failed"] += 1
        if len(self.status["errors"]) < 20:
            self.status["errors"].append(str(job["target"]) + ": " + error)

    @staticmethod
    def _publish(job, data):
        directory = thumbnail_folder(job["root"], job["item"]["dbName"], job["kind"])
        if directory is None:
            raise ValueError("Thumbnail directory changed")
        directory.mkdir(parents=True, exist_ok=True)
        if job["kind"] in find_thumbnails(job["item"], job["root"]):
            return False
        descriptor, temporary = tempfile.mkstemp(prefix=".thumbnail-", dir=directory)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                # Exclusive publication preserves images created while the request ran.
                os.link(temporary, job["target"])
            except FileExistsError:
                return False
            return True
        finally:
            Path(temporary).unlink(missing_ok=True)
