import shutil
import subprocess
import wave

import pytest
from PySide6.QtCore import QEventLoop, QTimer

from udeck.apps.common.library import Source, scan
from udeck.apps.media.engine import MediaEngine
from udeck.apps.music.controller import MusicController
from udeck.apps.video.controller import VideoController
from udeck.i18n import Msg, render, tr


@pytest.fixture
def video(tmp_path):
    controller = VideoController(tmp_path / "state", tmp_path / "settings.json")
    controller.isolated = True
    try:
        yield controller
    finally:
        controller.close()


def test_video_end_reveals_controls_for_replay(video):
    video.current = {"id": "finished-video"}
    video.controls_visible = False

    video.end_file()

    assert video.snapshot()["controlsVisible"]
    assert video.notice == tr(Msg.PLAYBACK_FINISHED)
    assert video.store.data["positions"]["finished-video"] == 0


@pytest.mark.parametrize("value", ["nan", "inf", "-inf", "1e309", "-1e309"])
def test_seek_rejects_nonfinite_input_and_keeps_the_prompt(video, value):
    video.command("seek")
    video.setDraft(value)
    prompt = video.menus[-1]

    video.submit(value)

    assert video.menus == [prompt] and prompt["draft"] == value
    assert render(tr(Msg.ENTER_A_FINITE_NUMBER)) in render(video.error)
    assert video.media.player.position() == 0


@pytest.mark.parametrize("seconds", [1e308, -1e308])
def test_seek_clamps_finite_values_before_integer_conversion(seconds):
    media = MediaEngine()
    try:
        media.seek(seconds)
        assert media.player.position() == 0
    finally:
        media.close()


def wait_for(condition, timeout=5):
    loop = QEventLoop()
    poll = QTimer()
    poll.setInterval(10)
    poll.timeout.connect(lambda: loop.quit() if condition() else None)
    deadline = QTimer()
    deadline.setSingleShot(True)
    deadline.timeout.connect(loop.quit)
    poll.start()
    deadline.start(int(timeout * 1000))
    try:
        if not condition():
            loop.exec()
        assert condition()
    finally:
        poll.stop()
        deadline.stop()


@pytest.mark.parametrize("app_class,extension", [(VideoController, ".mp4"), (MusicController, ".wav")])
def test_opening_healthy_media_clears_previous_playback_messages(tmp_path, app_class, extension):
    source = tmp_path / "source"
    source.mkdir()
    path = source / ("original" + extension)
    if extension == ".mp4":
        if not shutil.which("ffmpeg"):
            pytest.skip("ffmpeg is required for the original video fixture")
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                        "-f", "lavfi", "-i", "color=c=blue:size=160x90:rate=10",
                        "-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono", "-t", "2",
                        "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", str(path)],
                       check=True, capture_output=True, timeout=20)
    else:
        with wave.open(str(path), "wb") as stream:
            stream.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
            stream.writeframes(b"\0\0" * 16000)
    controller = app_class(tmp_path / "state", tmp_path / "settings.json")
    controller.isolated = True
    try:
        folder = Source.create(source)
        controller.library.sources = [folder]
        controller.library.items = scan(folder, controller.app)
        controller.playback_failed("Previous file was damaged")
        controller.notice = tr(Msg.PLAYBACK_FINISHED)

        controller.open_item(controller.library.items[0]["id"])
        wait_for(lambda: controller.media.player.position() > 50)

        assert not controller.media.player.errorString()
        assert not controller.snapshot()["error"]
        assert not controller.snapshot()["notice"]
    finally:
        controller.close()
