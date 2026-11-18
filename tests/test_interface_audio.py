"""
[INPUT]: 依赖真实 PCM 输出器、离线音效与隔离 Qt 音频设备。
[OUTPUT]: 验证持续输出、空闲暂停、短写保留和设备变更。
[POS]: 音频传输回归；语义优先级由音效调度测试覆盖。
[PROTOCOL]: Update this header on change, then check AGENTS.md
"""

import wave
from pathlib import Path
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QObject, Signal
from PySide6.QtMultimedia import QAudio

from udeck import interface_audio as module


@pytest.fixture
def output(monkeypatch):
    queries, sinks = [], []
    device = SimpleNamespace(missing=False, supported=True)
    device.isNull = lambda: device.missing
    device.isFormatSupported = lambda format: device.supported

    class Devices(QObject):
        audioOutputsChanged = Signal()

        @staticmethod
        def defaultAudioOutput():
            queries.append(True)
            return device

    class Stream:
        def __init__(self, sink):
            self.sink = sink
            self.written = bytearray()
            self.limit = None

        def write(self, data):
            count = len(data) if self.limit is None else min(len(data), self.limit)
            self.written.extend(data[:count])
            self.sink.free -= count
            return count

    class Sink(QObject):
        def __init__(self, device, format, parent):
            super().__init__(parent)
            self.starts = self.resets = 0
            self.suspends = self.resumes = 0
            self.free = 0
            sinks.append(self)

        def setBufferSize(self, size):
            self.size = size

        def bufferSize(self):
            return self.size

        def bytesFree(self):
            return self.free

        def start(self):
            self.starts += 1
            self.stream = Stream(self)
            self.free = self.size
            return self.stream

        def reset(self):
            self.resets += 1

        def suspend(self):
            self.suspends += 1

        def resume(self):
            self.resumes += 1

        def error(self):
            return QAudio.Error.NoError

    monkeypatch.setattr(module, "QMediaDevices", Devices)
    monkeypatch.setattr(module, "QAudioSink", Sink)
    driver = module.PcmOutput()
    yield SimpleNamespace(driver=driver, sinks=sinks, queries=queries, device=device)
    driver.close()


def clip(name):
    path = Path(module.__file__).parent / "assets/interface-sounds" / name
    with wave.open(str(path)) as source:
        return source.readframes(source.getnframes())


def test_navigation_reuses_one_audio_stream_and_one_device_query(output):
    driver = output.driver
    assert driver.warm()
    sink = output.sinks[0]
    for _ in range(4):
        sink.free = sink.size
        driver.play("tick_001.wav")
        driver._feed()
        assert driver.warm()
    assert sink.starts == 1 and sink.resets == 0
    assert output.queries == [True]
    assert clip("tick_001.wav") in sink.stream.written


def test_partial_writes_preserve_the_entire_pcm_sample(output):
    driver = output.driver
    assert driver.warm()
    sink = output.sinks[0]
    sink.stream.written.clear()
    sink.stream.limit = 102
    driver.play("confirmation_003.wav")
    sample = clip("confirmation_003.wav")
    while len(sink.stream.written) < len(sample):
        sink.free = sink.size
        driver._feed()
    assert sink.stream.written[:len(sample)] == sample
    assert sink.starts == 1


def test_cancel_flushes_old_audio_before_another_foreground_stream(output):
    driver = output.driver
    driver.warm()
    sink = output.sinks[0]
    driver.play("confirmation_003.wav")
    driver.cancel()
    assert sink.resets == 1
    assert not driver.is_playing("confirmation_003.wav")
    assert driver.warm()
    driver.play("error_008.wav")
    for _ in range(3):
        sink.free = sink.size
        driver._feed()
    assert sink.starts == 2
    assert clip("confirmation_003.wav") not in sink.stream.written
    assert clip("error_008.wav") in sink.stream.written


def test_device_notifications_stop_missing_output_and_recover_without_per_key_queries(output):
    driver = output.driver
    changes = []
    driver.changed.connect(lambda: changes.append(True))
    assert driver.warm()
    output.device.missing = True
    driver._devices.audioOutputsChanged.emit()
    assert not driver.warm()
    assert changes == [True]
    output.device.missing = False
    driver._devices.audioOutputsChanged.emit()
    assert driver.warm()
    assert len(output.queries) == 3
    assert changes == [True, True]
    assert output.sinks[0].resets == 1


def test_unsupported_output_and_unknown_samples_do_not_open_a_stream(output):
    driver = output.driver
    output.device.supported = False
    driver._devices.audioOutputsChanged.emit()
    assert not driver.warm()
    driver.play("unknown.wav")
    assert not any(sink.starts for sink in output.sinks)


def test_idle_audio_suspends_timer_and_reuses_stream_for_the_next_sound(output, monkeypatch):
    clock = [10.0]
    monkeypatch.setattr(module.time, 'monotonic', lambda: clock[0])
    driver = output.driver
    assert driver.warm()
    sink = output.sinks[0]
    clock[0] += 2
    sink.free = sink.size
    driver._feed()
    assert not driver._timer.isActive() and sink.suspends == 1
    written = len(sink.stream.written)
    clock[0] += 20
    driver.play('tick_001.wav')
    sink.free = sink.size
    driver._feed()
    assert driver._timer.isActive() and sink.resumes == 1
    assert sink.starts == 1 and sink.resets == 0
    assert clip('tick_001.wav') in sink.stream.written[written:]


def test_audio_does_not_suspend_before_a_long_sample_finishes(output, monkeypatch):
    clock = [10.0]
    monkeypatch.setattr(module.time, 'monotonic', lambda: clock[0])
    driver = output.driver
    driver.play('confirmation_003.wav')
    sink = output.sinks[0]
    clock[0] += .3
    sink.free = sink.size
    driver._feed()
    assert sink.suspends == 0 and driver._timer.isActive()
    clock[0] += 5
    while driver._offset < len(driver._pending):
        sink.free = sink.size
        driver._feed()
    driver._feed()
    assert sink.suspends == 1 and not driver._timer.isActive()


def test_cancelled_suspended_stream_starts_fresh_without_resuming_old_audio(output, monkeypatch):
    clock = [10.0]
    monkeypatch.setattr(module.time, 'monotonic', lambda: clock[0])
    driver = output.driver
    driver.warm()
    clock[0] += 5
    driver._feed()
    sink = output.sinks[0]
    assert sink.suspends == 1
    driver.cancel()
    driver.play('error_008.wav')
    assert sink.starts == 2 and sink.resets == 1 and sink.resumes == 0
