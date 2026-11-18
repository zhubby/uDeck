"""
[INPUT]: 依赖离线 PCM 资源、Qt 音频设备与播放线程事件循环。
[OUTPUT]: 提供单条复用音频流、空闲暂停和前台取消。
[POS]: 音效传输层；播放时供数，安静后暂停流和计时器。
[PROTOCOL]: Update this header on change, then check AGENTS.md
"""

import time
import wave
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtMultimedia import QAudio, QAudioFormat, QAudioSink, QMediaDevices

SAMPLE_RATE = 48000
FRAME_BYTES = 2
BYTES_PER_SECOND = SAMPLE_RATE * FRAME_BYTES
BUFFER_MILLISECONDS = 80
SUPPLY_INTERVAL_MILLISECONDS = 10
IDLE_SECONDS = 0.5


class PcmOutput(QObject):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._samples = {}
        for path in (Path(__file__).parent / "assets/interface-sounds").glob("*.wav"):
            try:
                with wave.open(str(path)) as source:
                    if (source.getnchannels(), source.getsampwidth(), source.getframerate()) == (1, FRAME_BYTES, SAMPLE_RATE):
                        self._samples[path.name] = source.readframes(source.getnframes())
            except (OSError, EOFError, wave.Error):
                continue
        self._sink = None
        self._stream = None
        self._pending = b""
        self._offset = 0
        self._current = ""
        self._ends = 0.0
        self._idle_at = 0.0
        self._suspended = False
        self._timer = QTimer(self)
        self._timer.setInterval(SUPPLY_INTERVAL_MILLISECONDS)
        self._timer.timeout.connect(self._feed)
        self._devices = QMediaDevices(self)
        self._devices.audioOutputsChanged.connect(self._configure)
        self._configure()

    def _configure(self):
        self.cancel()
        if self._sink is not None:
            self._sink.deleteLater()
            self._sink = None
        device = QMediaDevices.defaultAudioOutput()
        format = QAudioFormat()
        format.setSampleRate(SAMPLE_RATE)
        format.setChannelCount(1)
        format.setSampleFormat(QAudioFormat.SampleFormat.Int16)
        if not device.isNull() and device.isFormatSupported(format):
            self._sink = QAudioSink(device, format, self)
            self._sink.setBufferSize(BYTES_PER_SECOND * BUFFER_MILLISECONDS // 1000)
        self.changed.emit()

    def ready(self, filename):
        return self._sink is not None and bool(self._samples.get(filename))

    def warm(self):
        if self._sink is None or not self._samples:
            return False
        if self._stream is None:
            self._stream = self._sink.start()
            if self._stream is None or self._sink.error() in (QAudio.Error.OpenError, QAudio.Error.IOError, QAudio.Error.FatalError):
                self.cancel()
                return False
            self._idle_at = time.monotonic() + IDLE_SECONDS
            self._feed()
            self._timer.start()
        elif self._suspended:
            self._sink.resume()
            self._suspended = False
            self._idle_at = time.monotonic() + IDLE_SECONDS
            self._timer.start()
        return True

    def play(self, filename):
        if not self.ready(filename) or not self.warm():
            return
        self._pending = self._samples[filename]
        self._offset = 0
        self._current = filename
        queued = max(0, self._sink.bufferSize() - self._sink.bytesFree())
        self._ends = time.monotonic() + (queued + len(self._pending)) / BYTES_PER_SECOND
        self._idle_at = self._ends + IDLE_SECONDS
        self._feed()

    def is_playing(self, filename):
        return self._current == filename and time.monotonic() < self._ends

    def stop(self):
        self._pending = b""
        self._offset = 0
        self._current = ""
        self._ends = 0.0

    def cancel(self):
        self.stop()
        self._timer.stop()
        self._suspended = False
        if self._stream is not None:
            self._stream = None
            self._sink.reset()

    def _feed(self):
        if self._stream is None:
            return
        if self._offset >= len(self._pending) and time.monotonic() >= self._idle_at:
            self._sink.suspend()
            self._suspended = True
            self._timer.stop()
            return
        size = max(0, min(self._sink.bytesFree(), self._sink.bufferSize()))
        size -= size % FRAME_BYTES
        if not size:
            return
        sample = self._pending[self._offset:self._offset + size]
        written = self._stream.write(sample + bytes(size - len(sample)))
        if written < 0:
            self.cancel()
        else:
            self._offset += min(written, len(sample))

    def close(self):
        self.cancel()
