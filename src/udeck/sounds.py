"""Semantic, foreground-only feedback using the bundled Kenney interface sounds."""

import time
from functools import wraps
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, QUrl, Signal, Slot
from PySide6.QtMultimedia import QMediaDevices, QSoundEffect

from .core import ConfigStore

SOUND_FILES = {
    "navigate": "tick_001.wav", "accept": "select_001.wav",
    "open": "open_001.wav", "back": "back_001.wav",
    "toggle-on": "toggle_001.wav", "toggle-off": "toggle_002.wav",
    "success": "confirmation_003.wav", "error": "error_008.wav",
}
PRIORITY = {"navigate": 1, "accept": 2, "open": 3, "back": 4,
            "toggle-on": 5, "toggle-off": 5, "success": 6, "error": 7}


def interaction(method):
    @wraps(method)
    def wrapped(self, *args, **kwargs):
        self._feedback_depth += 1
        try:
            return method(self, *args, **kwargs)
        finally:
            self._feedback_depth -= 1
            if not self._feedback_depth and self._feedback_event:
                event, self._feedback_event = self._feedback_event, ""
                self.soundRequested.emit(event)
    return wrapped


class SoundFeedback(QObject):
    soundRequested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._feedback_depth = 0
        self._feedback_event = ""

    def feedback(self, event):
        if (self._feedback_depth and event in PRIORITY
                and PRIORITY[event] >= PRIORITY.get(self._feedback_event, 0)):
            self._feedback_event = event


class InterfaceSounds(QObject):
    def __init__(self, config_path, window, *, silent=False):
        super().__init__(window)
        self.config_path = config_path
        self.window = window
        self.silent = silent
        self._closed = False
        self._effects = {}
        self._current = ""
        self._pending = ""
        self._last_navigation = float("-inf")
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._flush)
        self._devices = QMediaDevices(self)
        self._devices.audioOutputsChanged.connect(self._output_changed)
        window.activeChanged.connect(self._foreground_changed)
        self._warm()

    def _enabled(self):
        return (not self._closed and not self.silent and self.window.isActive()
                and ConfigStore(self.config_path).data["preferences"]["uiSounds"]
                and not QMediaDevices.defaultAudioOutput().isNull())

    def _warm(self):
        if not self._enabled():
            return
        device = QMediaDevices.defaultAudioOutput()
        root = Path(__file__).parent / "assets/interface-sounds"
        for event, filename in SOUND_FILES.items():
            if event not in self._effects:
                effect = QSoundEffect(self)
                effect.setAudioDevice(device)
                effect.setSource(QUrl.fromLocalFile(str(root / filename)))
                self._effects[event] = effect

    @Slot(str)
    def request(self, event):
        if event not in SOUND_FILES:
            return
        if not self._enabled():
            self._stop()
            return
        self._warm()
        if PRIORITY[event] >= PRIORITY.get(self._pending, 0):
            self._pending = event
        self._timer.start(0)

    def _flush(self):
        event, self._pending = self._pending, ""
        if not event or not self._enabled():
            self._stop()
            return
        now = time.monotonic()
        if event == "navigate":
            if now - self._last_navigation < 0.09:
                return
            current = self._effects.get(self._current)
            if self._current != "navigate" and current and current.isPlaying():
                return
        effect = self._effects.get(event)
        if effect is None or effect.status() != QSoundEffect.Status.Ready:
            return
        self._stop()
        self._current = event
        effect.play()
        if event == "navigate":
            self._last_navigation = now

    def _stop(self):
        self._timer.stop()
        self._pending = ""
        self._current = ""
        for effect in self._effects.values():
            effect.stop()

    def _foreground_changed(self):
        if self.window.isActive():
            self._warm()
        else:
            self._stop()

    def _output_changed(self):
        self._stop()
        device = QMediaDevices.defaultAudioOutput()
        if not device.isNull():
            for effect in self._effects.values():
                effect.setAudioDevice(device)
            self._warm()

    def close(self):
        self._closed = True
        self._stop()
