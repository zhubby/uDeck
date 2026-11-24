"""
[INPUT]: 依赖真实 Qt 播放引擎、FFmpeg 和原创长 GOP TS。
[OUTPUT]: 验证续播、暂停定位和前后跳转后的实际解码画面。
[POS]: 独立进程回归；不连接用户会话，不读写应用配置。
[PROTOCOL]: Update this header on change, then check AGENTS.md
"""

import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtMultimedia import QMediaPlayer, QVideoSink
from PySide6.QtWidgets import QApplication

from udeck.apps.media.engine import MediaEngine


def wait_for(condition, seconds=6):
    loop = QEventLoop()
    timer = QTimer()
    timer.setInterval(20)
    timer.timeout.connect(lambda: loop.quit() if condition() else None)
    deadline = QTimer()
    deadline.setSingleShot(True)
    deadline.timeout.connect(loop.quit)
    timer.start()
    deadline.start(int(seconds * 1000))
    try:
        if not condition():
            loop.exec()
        assert condition(), "No decoded frame at the requested media position"
    finally:
        timer.stop()
        deadline.stop()


def frame_hashes(path):
    result = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin",
                             "-i", str(path), "-map", "0:v:0", "-an", "-f", "framemd5", "-"],
                            capture_output=True, text=True, check=True, timeout=20)
    return [line.rsplit(",", 1)[1].strip() for line in result.stdout.splitlines()
            if line and not line.startswith("#")]


root = Path(sys.argv[1])
root.mkdir()
source = root / "Long GOP 视频.TS"
subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin",
                "-f", "lavfi", "-i", "testsrc2=size=160x90:rate=10:duration=10",
                "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=16000:duration=10",
                "-c:v", "libx264", "-preset", "ultrafast", "-g", "300",
                "-c:a", "aac", "-f", "mpegts", str(source)],
               check=True, capture_output=True, timeout=20)
original = hashlib.sha256(source.read_bytes()).hexdigest()
application = QApplication([])
engine = MediaEngine()
engine.output.setMuted(True)
sink = QVideoSink()
engine.player.setVideoSink(sink)
frames = []
errors = []
engine.failed.connect(errors.append)


def received(frame):
    if frame.isValid() and not frame.toImage().isNull():
        frames.append(frame.startTime() / 1_000_000)


sink.videoFrameChanged.connect(received)
item = {"id": "original-long-gop", "path": str(source)}
started = time.monotonic()
try:
    engine.load(item)
    wait_for(lambda: len(frames) >= 2)
    frames.clear()
    engine.load(item, 3000)
    wait_for(lambda: any(2.8 <= position <= 4.5 for position in frames))
    resumed = list(frames)

    engine.player.pause()
    frames.clear()
    engine.seek(1)
    wait_for(lambda: any(0.8 <= position <= 2 for position in frames))
    assert engine.player.playbackState() == QMediaPlayer.PlaybackState.PausedState
    backwards = list(frames)

    engine.player.play()
    frames.clear()
    engine.seek(6)
    wait_for(lambda: any(5.8 <= position <= 7.5 for position in frames))
    forwards = list(frames)
    engine.player.stop()
    prepared = Path(engine.player.source().toLocalFile())
    assert frame_hashes(prepared) == frame_hashes(source), "Decoded picture content changed"
    assert hashlib.sha256(source.read_bytes()).hexdigest() == original
    assert not errors, errors
    report = {"resumedFrames": resumed, "backwardFrames": backwards, "forwardFrames": forwards,
              "sourceUnchanged": True, "decodedPicturesUnchanged": True,
              "seconds": round(time.monotonic() - started, 3)}
finally:
    engine.close()
if prepared != source:
    assert not prepared.exists(), "Temporary media survived engine close"
print(json.dumps(report))
