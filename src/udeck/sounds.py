"""
[INPUT]: 依赖前台窗口、音效偏好与持续 PCM 输出。
[OUTPUT]: 提供语义反馈、事件合并和独立线程调度。
[POS]: 界面线程只决定播放意图；音频对象只在播放线程访问。
[PROTOCOL]: Update this header on change, then check AGENTS.md
"""

import threading
import time
from functools import wraps

from PySide6.QtCore import QObject, Qt, QThread, QTimer, Signal, Slot

from .core import ConfigStore
from .interface_audio import PcmOutput

SOUND_FILES = {
    "navigate": "tick_001.wav", "accept": "select_001.wav",
    "open": "open_001.wav", "back": "back_001.wav",
    "toggle-on": "toggle_001.wav", "toggle-off": "toggle_002.wav",
    "success": "confirmation_003.wav", "error": "error_008.wav",
}
PRIORITY = {"navigate": 1, "accept": 2, "open": 3, "back": 4,
            "toggle-on": 5, "toggle-off": 5, "success": 6, "error": 7}
NAVIGATION_INTERVAL = 0.09
MAX_PENDING_AGE = 0.25


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


class _SoundMailbox:
    def __init__(self):
        self.lock = threading.Lock()
        self.enabled = False
        self.generation = 0
        self.pending = None
        self.scheduled = False

    def submit(self, event=""):
        with self.lock:
            self.enabled = True
            if event and (not self.pending or PRIORITY[event] >= PRIORITY[self.pending[0]]):
                self.pending = (event, time.monotonic())
            return self._schedule()

    def cancel(self, *, keep_enabled=False):
        with self.lock:
            self.enabled = self.enabled and keep_enabled
            self.generation += 1
            self.pending = None
            return self._schedule()

    def _schedule(self):
        wake = not self.scheduled
        self.scheduled = True
        return wake

    def take(self):
        with self.lock:
            self.scheduled = False
            pending, self.pending = self.pending, None
            return self.enabled, self.generation, pending

    def valid(self, generation):
        with self.lock:
            return self.enabled and self.generation == generation

    def invalidate(self):
        with self.lock:
            self.generation += 1
            self.pending = None


class _SoundPlayer(QObject):
    stopped = Signal()

    def __init__(self, mailbox):
        super().__init__()
        self.mailbox = mailbox
        self._output = None
        self._current = ""
        self._generation = 0
        self._last_navigation = float("-inf")

    def _warm(self):
        if self._output is None:
            self._output = PcmOutput(self)
            self._output.changed.connect(self._output_changed)
        return self._output.warm()

    def _cancel(self):
        self._current = ""
        if self._output is not None:
            self._output.cancel()

    @Slot()
    def flush(self):
        enabled, generation, pending = self.mailbox.take()
        if generation != self._generation:
            self._cancel()
            self._generation = generation
        if not enabled:
            self._cancel()
            return
        if not self._warm():
            self._cancel()
            return
        if not self.mailbox.valid(generation):
            self._cancel()
            return
        if not pending:
            return
        event, submitted = pending
        now = time.monotonic()
        if now - submitted > MAX_PENDING_AGE:
            return
        if event == "navigate":
            if now - self._last_navigation < NAVIGATION_INTERVAL:
                return
            if self._current != "navigate" and self._output.is_playing(SOUND_FILES.get(self._current, "")):
                return
        if not self._output.ready(SOUND_FILES[event]):
            return
        self._current = event
        self._output.play(SOUND_FILES[event])
        if not self.mailbox.valid(generation):
            self._cancel()
        if event == "navigate":
            self._last_navigation = now

    @Slot()
    def _output_changed(self):
        self.mailbox.invalidate()
        self._cancel()

    @Slot()
    def close(self):
        if self._output is not None:
            self._output.close()
        self.stopped.emit()


class InterfaceSounds(QObject):
    _wake = Signal()
    _shutdown = Signal()

    def __init__(self, config_path, window, *, silent=False):
        super().__init__(window)
        self.config_path = config_path
        self.window = window
        self.silent = silent
        self._closed = False
        self._pending = ""
        self._mailbox = _SoundMailbox()
        self._thread = None
        self._player = None
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._flush)
        window.activeChanged.connect(self._foreground_changed)
        self._warm()

    def _enabled(self):
        return (not self._closed and not self.silent and self.window.isActive()
                and ConfigStore(self.config_path).data["preferences"]["uiSounds"])

    def _warm(self):
        if not self._enabled():
            return
        wake = self._mailbox.submit()
        if self._thread is None:
            self._thread = QThread(self)
            self._thread.setObjectName("udeck-ui-audio")
            self._player = _SoundPlayer(self._mailbox)
            self._player.moveToThread(self._thread)
            self._wake.connect(self._player.flush, Qt.ConnectionType.QueuedConnection)
            self._shutdown.connect(self._player.close, Qt.ConnectionType.QueuedConnection)
            self._player.stopped.connect(self._thread.quit, Qt.ConnectionType.DirectConnection)
            self._thread.finished.connect(self._player.deleteLater)
            self._thread.started.connect(self._player.flush)
            self._thread.start()
        if wake:
            self._wake.emit()

    @Slot(str)
    def request(self, event):
        if event not in SOUND_FILES:
            return
        if not self._enabled():
            self._stop()
            return
        if self._thread is None:
            self._warm()
        if PRIORITY[event] >= PRIORITY.get(self._pending, 0):
            self._pending = event
        self._timer.start(0)

    def _flush(self):
        event, self._pending = self._pending, ""
        if not event or not self._enabled():
            self._stop()
            return
        if self._mailbox.submit(event):
            self._wake.emit()

    def _stop(self):
        self._timer.stop()
        self._pending = ""
        if self._mailbox.cancel() and self._thread is not None:
            self._wake.emit()

    def _foreground_changed(self):
        if self.window.isActive():
            self._warm()
        else:
            self._stop()

    def close(self):
        if self._closed:
            return
        self._closed = True
        self._stop()
        if self._thread is not None:
            self._shutdown.emit()
            self._thread.wait()
            self._player = None
            self._thread = None
