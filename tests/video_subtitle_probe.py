"""Real embedded subtitle selection, seeking and QML composition."""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

from PySide6.QtCore import QEventLoop, QObject, QTimer, QUrl
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtWebEngineQuick import QtWebEngineQuick
from PySide6.QtWidgets import QApplication
from shiboken6 import delete

import udeck
from udeck.apps.media.engine import FrameImages
from udeck.apps.video.controller import VideoController
from udeck.core import ConfigStore
from udeck.icons import IconProvider


def events(milliseconds):
    loop = QEventLoop()
    QTimer.singleShot(milliseconds, loop.quit)
    loop.exec()


def fixtures(root):
    root.mkdir(parents=True, exist_ok=True)
    (root / "english.srt").write_text(
        "1\n00:00:00,000 --> 00:00:06,000\nFirst long embedded caption\n\n"
        "2\n00:00:07,000 --> 00:00:10,000\nSecond embedded caption\n", encoding="utf-8")
    (root / "chinese.srt").write_text(
        "1\n00:00:00,000 --> 00:00:06,000\n第一段内嵌中文字幕\n\n"
        "2\n00:00:07,000 --> 00:00:10,000\n第二段内嵌中文字幕\n", encoding="utf-8")
    target = root / "Embedded captions.mkv"
    if not target.exists():
        subprocess.run([
            "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "testsrc2=duration=12:size=640x360:rate=15",
            "-i", str(root / "english.srt"), "-i", str(root / "chinese.srt"),
            "-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono", "-t", "12",
            "-map", "0:v", "-map", "3:a", "-map", "1:s", "-map", "2:s",
            "-c:v", "mpeg4", "-c:a", "aac", "-c:s", "srt",
            "-metadata:s:s:0", "language=eng", "-metadata:s:s:1", "language=zho", str(target)],
            check=True, capture_output=True, timeout=30)
    return target


def run(root):
    os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")
    QtWebEngineQuick.initialize()
    qt = QApplication([])
    root.mkdir(parents=True, exist_ok=True)
    path = fixtures(root / "source")
    controller = VideoController(root / "state", root / "settings.json")
    controller.isolated = True
    controller.set_language(os.environ.get("UDECK_PROBE_LANGUAGE", "zh_CN"))
    config = ConfigStore(root / "settings.json")
    config.data["preferences"]["theme"] = os.environ.get("UDECK_PROBE_THEME", "classic")
    config.save()
    controller.theme = config.data["preferences"]["theme"]
    engine = QQmlApplicationEngine()
    engine.addImageProvider("desktop", IconProvider())
    engine.addImageProvider("video", FrameImages(controller))
    engine.rootContext().setContextProperty("controller", controller)
    engine.rootContext().setContextProperty("windowed", True)
    errors = []
    engine.warnings.connect(lambda values: errors.extend(value.toString() for value in values))
    engine.load(QUrl.fromLocalFile(str(Path(udeck.__file__).parent / "apps/common/qml/Main.qml")))
    assert engine.rootObjects(), errors
    window = engine.rootObjects()[0]
    # Attaching a sink to an already decoding FFmpeg player can deadlock in
    # QObject destruction while the PySide binding retains the Python GIL.
    sink = controller.media.player.videoSink()
    window.setWidth(int(os.environ.get("UDECK_PROBE_WIDTH", "960")))
    window.setHeight(int(os.environ.get("UDECK_PROBE_HEIGHT", "600")))
    controller.window = window
    window.show()
    window.requestActivate()
    controller.media.output.setVolume(0)
    checks = []

    def wait(condition, seconds=10):
        deadline = time.monotonic() + seconds
        while not condition() and time.monotonic() < deadline:
            qt.processEvents()
            events(20)
        assert condition(), {"state": json.loads(controller.snapshotJson), "qml": errors}

    def visible_caption(text):
        return any(text == obj.property("text") and obj.property("visible")
                   for obj in window.findChildren(QObject) if obj.inherits("QQuickText"))

    def caption(text, capture):
        wait(lambda: controller.subtitle_text() == text)
        wait(lambda: visible_caption(text))
        events(100)
        assert window.grabWindow().save(str(root / (capture + ".png")))

    try:
        assert sink is not None, "Bind the video sink before media playback starts"
        controller.library.add(path.parent)
        wait(lambda: not controller.library.pending)
        item = next(item for item in controller.library.items if item["path"] == str(path))
        controller.setTab(1)
        controller.open_item(item["id"])
        assert controller.media.player.videoSink() is sink
        wait(lambda: controller.media.player.position() > 300)
        wait(lambda: controller.media.player.videoSink() is not None
             and controller.media.player.videoSink().videoFrame().isValid())
        controller.media.player.pause()
        controller.seek(3)
        controller.set_track(True, 0)
        caption("First long embedded caption", "late-enable")
        checks.append("enable-embedded-track-while-paused-in-middle-of-cue")
        controller.seek(4.5)
        caption("First long embedded caption", "seek-forward")
        controller.seek(2)
        caption("First long embedded caption", "seek-back")
        checks.append("forward-and-backward-seek-retains-current-embedded-cue")
        controller.seek(6.5)
        wait(lambda: not controller.subtitle_text())
        assert not visible_caption("First long embedded caption")
        controller.seek(8)
        caption("Second embedded caption", "second-cue")
        checks.append("cue-gap-clears-text-and-seek-selects-next-cue")
        controller.set_track(True, 1)
        caption("第二段内嵌中文字幕", "chinese-track")
        controller.command("hide-controls")
        controller.seek(4)
        caption("第一段内嵌中文字幕", "hidden-chinese")
        checks.append("switch-embedded-languages-and-hide-controls")
        controller.set_track(True, -1)
        events(150)
        assert not controller.subtitle_text() and not visible_caption("第一段内嵌中文字幕")
        checks.append("off-removes-embedded-text")
        controller.set_track(True, 0)
        caption("First long embedded caption", "reenabled")
        controller.load_subtitles(path.parent / "chinese.srt")
        caption("第一段内嵌中文字幕", "external-after-embedded")
        controller.set_track(True, 0)
        caption("First long embedded caption", "embedded-after-external")
        checks.append("external-and-embedded-selection-replaces-the-other")
        controller.seek(5.5)
        controller.set_speed(2)
        controller.media.player.play()
        wait(lambda: controller.media.player.position() > 6100)
        assert not controller.subtitle_text()
        wait(lambda: controller.subtitle_text() == "Second embedded caption")
        controller.media.player.pause()
        checks.append("captions-follow-playback-position-at-double-speed")
        controller.back()
        assert controller.page == "library"
        controller.open_item(item["id"])
        controller.choose(0)
        assert controller.media.player.videoSink() is sink
        wait(lambda: not controller.media.loading and controller.media.player.position() > 7000)
        controller.media.player.pause()
        controller.set_track(True, 0)
        caption("Second embedded caption", "resumed-cue")
        checks.append("resume-then-enable-current-embedded-cue")
        assert not errors, errors
        report = {"passed": True, "checks": checks, "qmlErrors": errors,
                  "rendering": "software" if controller.media.software else "native"}
        (root / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
        print(json.dumps(report, ensure_ascii=False), flush=True)
    finally:
        controller.close()
        window.setProperty("allowClose", True)
        window.close()
        delete(engine)


if __name__ == "__main__":
    run(Path(sys.argv[1]))
