"""QtMultimedia playback. UI state comes from observed player properties."""

import math
import os
import time

from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtGui import QImage
from PySide6.QtMultimedia import QAudioOutput, QMediaDevices, QMediaPlayer
from PySide6.QtQuick import QQuickImageProvider

from udeck.i18n import Msg, tr


class FrameImages(QQuickImageProvider):
    def __init__(self, controller):
        super().__init__(QQuickImageProvider.ImageType.Image)
        self.controller = controller

    def requestImage(self, identifier, size, requested_size):
        image = self.controller.media.frame_image.copy()
        if image.isNull():
            # A queued image request can arrive while the next source is loading.
            image = QImage(1, 1, QImage.Format.Format_ARGB32_Premultiplied)
            image.fill(0)
        size.setWidth(image.width())
        size.setHeight(image.height())
        return image


class MediaEngine(QObject):
    changed = Signal()
    ended = Signal()
    failed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.player = QMediaPlayer(self)
        self.output = QAudioOutput(self)
        self.devices = QMediaDevices(self)
        self.player.setAudioOutput(self.output)
        self.output.setVolume(0.8)
        self.pending_position = None
        self.identifier = ""
        self.loading = False
        self.software = os.environ.get("QT_QUICK_BACKEND") == "software"
        self.frame_image, self.frame_revision = QImage(), 0
        self.last_frame_time = 0
        self.player.mediaStatusChanged.connect(self.status_changed)
        self.player.errorOccurred.connect(lambda code, text: self.failed.emit(text))
        for signal in (self.player.positionChanged, self.player.durationChanged,
                       self.player.playbackStateChanged, self.player.tracksChanged,
                       self.player.activeTracksChanged, self.player.playbackRateChanged,
                       self.output.deviceChanged, self.devices.audioOutputsChanged):
            signal.connect(lambda *args: self.changed.emit())

    def load(self, item, position=0):
        self.frame_image, self.frame_revision, self.last_frame_time = QImage(), 0, 0
        self.player.stop()
        self.identifier, self.loading = item["id"], True
        self.pending_position = max(0, int(position))
        self.player.setSource(QUrl.fromLocalFile(item["path"]))
        self.player.play()
        self.changed.emit()

    def status_changed(self, status):
        if status in (QMediaPlayer.MediaStatus.LoadedMedia, QMediaPlayer.MediaStatus.BufferedMedia):
            self.loading = False
            if self.pending_position is not None:
                self.player.setPosition(self.pending_position)
                self.pending_position = None
        elif status == QMediaPlayer.MediaStatus.InvalidMedia:
            self.loading = False
        elif status == QMediaPlayer.MediaStatus.EndOfMedia:
            self.ended.emit()
        self.changed.emit()

    def snapshot(self):
        return {"position": self.player.position() / 1000, "duration": self.player.duration() / 1000,
                "playing": self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState,
                "loading": self.loading, "rate": self.player.playbackRate(),
                "output": self.output.device().description() or tr(Msg.SYSTEM_DEFAULT),
                "error": self.player.errorString(), "status": self.player.mediaStatus().name}

    def video_frame(self, frame):
        if not frame.isValid() or time.monotonic() - self.last_frame_time < 1 / 15:
            return
        image = frame.toImage()
        if not image.isNull():
            self.frame_image = image
            self.frame_revision += 1
            self.last_frame_time = time.monotonic()
            self.changed.emit()

    def toggle(self):
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def seek(self, seconds):
        if not math.isfinite(seconds):
            raise ValueError(tr(Msg.ENTER_A_FINITE_NUMBER))
        seconds = max(0, min(self.player.duration() / 1000, seconds))
        position = min(self.player.duration(), int(seconds * 1000))
        self.player.setPosition(position)

    def set_output(self, device_id):
        device = next((d for d in self.devices.audioOutputs() if bytes(d.id()).hex() == device_id), None)
        if device is None:
            raise OSError(tr(Msg.AUDIO_OUTPUT_DISAPPEARED))
        self.output.setDevice(device)
        if self.output.device().id() != device.id():
            raise OSError(tr(Msg.THE_AUDIO_OUTPUT_COULD_NOT_BE_CHANGED))
        self.changed.emit()

    def close(self):
        self.identifier = ""
        self.player.stop()
        self.player.setSource(QUrl())
