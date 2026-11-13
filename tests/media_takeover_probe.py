"""Exercise real music/video processes sharing one graphical session bus."""

import json
import os
import subprocess
import sys
import time
import wave
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QEventLoop, QTimer
from PySide6.QtDBus import QDBusConnection, QDBusInterface, QDBusMessage

from udeck.app_routing import APP_IDS, object_path, service_name
from udeck.apps.common.state import AppState


def run(root):
    root.mkdir(parents=True, exist_ok=True)
    content = root / "content"
    content.mkdir()
    music = content / "Original music.wav"
    other_music = content / "Another music.wav"
    for path, seconds in ((music, 30), (other_music, 29)):
        with wave.open(str(path), "wb") as stream:
            stream.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
            stream.writeframes(b"\0\0" * 16000 * seconds)
    video = content / "Original video.mp4"
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                    "-f", "lavfi", "-i", "color=c=blue:size=160x90:rate=10",
                    "-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono", "-t", "12",
                    "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", str(video)],
                   check=True, capture_output=True, timeout=30)
    # An old enabled preference must not restore music or reintroduce the switch.
    state = AppState("video", root / "video")
    state.data["preferences"]["resumeMusic"] = True
    state.save()
    state.close()
    application = QCoreApplication.instance() or QCoreApplication([])
    bus = QDBusConnection.sessionBus()
    assert bus.isConnected()
    processes, logs, controls = {}, {}, {}
    env = {**os.environ, "XDG_CONFIG_HOME": str(root / "config"),
           "XDG_DATA_HOME": str(root / "data"), "QT_QUICK_CONTROLS_STYLE": "Basic"}

    def pump(milliseconds=50):
        loop = QEventLoop()
        QTimer.singleShot(milliseconds, loop.quit)
        loop.exec()

    def wait(condition, label, seconds=15):
        deadline = time.monotonic() + seconds
        while not condition() and time.monotonic() < deadline:
            pump()
        assert condition(), {"check": label, "states": {app: diagnose(app) for app in controls}}

    def call(app, method, *args):
        reply = controls[app].call(method, *args)
        assert reply.type() != QDBusMessage.MessageType.ErrorMessage, reply.errorMessage()
        return reply.arguments()[0] if reply.arguments() else None

    def diagnose(app):
        return json.loads(call(app, "Diagnose"))

    def playing(app):
        return diagnose(app)["state"]["media"]["playing"]

    def position(app):
        return diagnose(app)["state"]["media"]["position"]

    def open_file(app, path):
        assert call(app, "Open", json.dumps({"files": [str(path)]})) == ""

    def toggle(app):
        assert call(app, "Action", "play-pause") == ""

    def exclusive(app, label):
        other = "video" if app == "music" else "music"
        wait(lambda: playing(app) and not playing(other), label)
        for _ in range(4):
            pump()
            assert playing(app) and not playing(other), label

    checks = []
    try:
        for app in ("music", "video"):
            app_id = APP_IDS[app]
            assert not bus.interface().isServiceRegistered(service_name(app_id)).value(), app
            logs[app] = (root / (app + ".log")).open("w")
            processes[app] = subprocess.Popen(
                [sys.executable, "-m", "udeck.apps.main", app, "--no-input", "--windowed",
                 "--data-dir", str(root / app), "--source", str(content)],
                env=env, stdout=logs[app], stderr=subprocess.STDOUT)
            wait(lambda app_id=app_id: bus.interface().isServiceRegistered(service_name(app_id)).value(),
                 app + " service startup")
            controls[app] = QDBusInterface(service_name(app_id), object_path(app_id),
                                          app_id + ".Control", bus)
            wait(controls[app].isValid, app + " object startup")

        open_file("music", music)
        exclusive("music", "music starts")
        wait(lambda: position("music") > 0.3, "music progress")
        open_file("video", video)
        exclusive("video", "video preempts music without confirmation")
        assert not diagnose("video")["state"]["menu"].get("title")
        music_position = position("music")
        checks.append("video-preempts-music-without-confirmation")

        wait(lambda: position("video") > 0.3, "video progress")
        toggle("music")
        exclusive("music", "music resume preempts video")
        assert position("music") >= music_position
        video_position = position("video")
        checks.append("music-resume-preempts-video-and-keeps-position")

        assert call("video", "Open", "{}") == ""
        exclusive("music", "showing video does not request playback")
        checks.append("window-activation-does-not-preempt-playback")

        toggle("video")
        exclusive("video", "video resume preempts music")
        assert position("video") >= video_position
        checks.append("video-resume-preempts-music-and-keeps-position")

        open_file("music", other_music)
        exclusive("music", "new music preempts video")
        assert diagnose("music")["state"]["current"]["path"] == str(other_music)
        checks.append("new-music-preempts-video")
        toggle("video")
        exclusive("video", "video resumes after new music")

        toggle("video")
        wait(lambda: not playing("video"), "video paused")
        pump(300)
        assert not playing("music")
        checks.append("pausing-winner-does-not-resume-other-player")

        # Repeated requests while sources are already loaded must settle on the last one.
        for app in ("music", "video", "music", "video"):
            toggle(app)
        exclusive("video", "last playback request wins")
        checks.append("rapid-playback-requests-remain-exclusive")

        assert call("video", "Action", "settings") == ""
        menu = diagnose("video")["state"]["menu"]
        assert len(menu["options"]) == 3 and all("checked" not in row for row in menu["options"]), menu
        checks.append("video-settings-have-no-auto-resume-switch")

        # Real EOF must leave the preempted music paused even with the old preference enabled.
        wait(lambda: diagnose("video")["state"]["media"]["status"] == "EndOfMedia",
             "video finishes", seconds=20)
        assert not playing("music")
        assert not diagnose("video")["qmlErrors"]
        checks.append("video-eof-does-not-resume-music-with-legacy-preference")
        processes["video"].terminate()
        processes["video"].wait(timeout=10)
        del controls["video"]
        pump(400)
        assert not playing("music")
        checks.append("winner-exit-does-not-resume-music-with-legacy-preference")
        assert not diagnose("music")["qmlErrors"]
        report = {"checks": checks, "music": diagnose("music"), "passed": True}
        (root / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps({"checks": checks, "passed": True}), flush=True)
    finally:
        for process in processes.values():
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
        for log in logs.values():
            log.close()
        application.processEvents()


if __name__ == "__main__":
    run(Path(sys.argv[1]).resolve())
