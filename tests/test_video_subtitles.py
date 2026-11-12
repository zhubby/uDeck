import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from PySide6.QtCore import QEventLoop, QProcess, QTimer

from udeck.apps.common.library import Source, scan
from udeck.apps.video import subtitles
from udeck.apps.video.controller import VideoController
from udeck.apps.video.subtitles import EmbeddedSubtitles, parse_srt
from udeck.i18n import Msg, render, tr

CAPTION = "1\n00:00:00,000 --> 00:00:06,000\nSelected caption\n"


def events(milliseconds):
    loop = QEventLoop()
    QTimer.singleShot(milliseconds, loop.quit)
    loop.exec()


def wait(condition):
    for _ in range(250):
        if condition():
            return
        events(20)
    assert condition()


@pytest.fixture
def extractor():
    reader = EmbeddedSubtitles()
    reader.results, reader.failures = [], []
    reader.ready.connect(lambda: reader.results.append(reader.cues))
    reader.failed.connect(reader.failures.append)
    yield reader
    reader.close()


@pytest.fixture
def fake_ffmpeg(tmp_path, monkeypatch):
    def install(body):
        executable = tmp_path / "ffmpeg"
        executable.write_text(f"#!{sys.executable}\nimport sys, time\n" + body)
        executable.chmod(0o700)
        monkeypatch.setenv("PATH", str(tmp_path))
    return install


def test_srt_unicode_markup_overlaps_and_invalid_cues():
    assert parse_srt(
        "\ufeff1\r\n00:00:01,025 --> 00:00:03,750\r\n<b>中文</b> &amp; text\r\nsecond line\r\n\r\n"
        "2\r\n00:00:02.000 --> 00:00:04.000 align:center\r\noverlap\r\n\r\n"
        "3\r\n00:00:04,000 --> 00:00:02,000\r\ninvalid\r\n\r\n"
        "4\r\n00:00:05,000 --> 00:00:06,000\r\n<i></i>\r\n") == [
            (1.025, 3.75, "中文 & text\nsecond line"), (2, 4, "overlap")]
    assert parse_srt("9" * 100000 + ":00:00,000 --> 00:00:01,000\ninvalid\n") == []


@pytest.mark.parametrize("codec,extension,offset", [
    ("srt", ".mkv", 0), ("ass", ".mkv", 0), ("mov_text", ".mp4", 0),
    ("srt", ".mkv", 5), ("mov_text", ".mp4", 5),
])
def test_real_text_codecs_and_nonzero_media_start(extractor, tmp_path, codec, extension, offset):
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg is required to generate the embedded text fixture")
    srt = tmp_path / "captions.srt"
    srt.write_text("1\n00:00:02,000 --> 00:00:06,000\n中文 & selected caption\n", encoding="utf-8")
    movie = tmp_path / ("captions" + extension)
    subprocess.run([
        "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", "color=c=blue:size=160x90:rate=5:duration=8",
        "-i", str(srt), "-map", "0:v", "-map", "1:s", "-c:v", "mpeg4",
        "-c:s", codec, "-output_ts_offset", str(offset), str(movie),
    ], check=True, capture_output=True, timeout=20)
    extractor.load(movie, 0)
    wait(lambda: bool(extractor.results or extractor.failures))
    assert not extractor.failures
    assert extractor.cues == [(2, 6, "中文 & selected caption")]


def test_extracts_in_background_and_reaps_process(extractor, fake_ffmpeg):
    fake_ffmpeg(f"time.sleep(0.15)\nsys.stdout.write({CAPTION!r})\n")
    extractor.load("video.mkv", 0)
    pulses = []
    QTimer.singleShot(30, lambda: pulses.append("UI tick"))
    wait(lambda: bool(extractor.results))
    assert pulses and not extractor.failures
    assert extractor.cues == [(0, 6, "Selected caption")]
    assert extractor.process is None and not extractor.timer.isActive()
    # Completion must not leave a demuxer running behind the player.
    assert not any(child.state() != QProcess.ProcessState.NotRunning
                   for child in extractor.findChildren(QProcess))


@pytest.mark.parametrize("action", ["off", "replace", "close"])
def test_cancelled_load_cannot_deliver_old_cues(extractor, fake_ffmpeg, action):
    fake_ffmpeg(f"time.sleep(0.2)\nsys.stdout.write({CAPTION!r})\n")
    extractor.load("old.mkv", 0)
    if action == "replace":
        extractor.load("new.mkv", 1)
        wait(lambda: bool(extractor.results))
        assert extractor.index == 1
        assert len(extractor.results) == 1
    else:
        getattr(extractor, "clear" if action == "off" else "close")()
        events(350)
        assert not extractor.results and extractor.cues is None and extractor.index == -1
    assert not extractor.failures
    # A queued old result/error is ignored even while a new selection is active.
    assert extractor.process is None and not extractor.timer.isActive()
    assert not any(child.state() != QProcess.ProcessState.NotRunning
                   for child in extractor.findChildren(QProcess))


@pytest.mark.parametrize("failure", ["missing", "exit", "timeout", "oversized", "encoding"])
def test_failed_extraction_is_bounded_and_retryable(extractor, fake_ffmpeg, tmp_path,
                                                   monkeypatch, failure):
    if failure == "missing":
        monkeypatch.setenv("PATH", str(tmp_path))
    elif failure == "exit":
        fake_ffmpeg("sys.stderr.write('Subtitle codec is unsupported')\nsys.exit(2)\n")
    elif failure == "timeout":
        monkeypatch.setattr(subtitles, "LOAD_TIMEOUT_MS", 120)
        fake_ffmpeg("time.sleep(10)\n")
    elif failure == "oversized":
        monkeypatch.setattr(subtitles, "MAX_BYTES", 256)
        fake_ffmpeg("sys.stdout.write('x' * 4096)\n")
    else:
        fake_ffmpeg("sys.stdout.buffer.write(b'\\xff\\xfe')\n")
    extractor.load("video.mkv", 0)
    wait(lambda: bool(extractor.failures))
    events(150)
    assert len(extractor.failures) == 1 and not extractor.results
    assert extractor.cues is None and extractor.process is None
    assert not extractor.timer.isActive()
    if failure == "exit":
        assert "Subtitle codec is unsupported" in extractor.failures[0]
    elif failure == "timeout":
        assert extractor.failures[0] == tr(Msg.SUBTITLE_LOADING_TIMED_OUT)
    elif failure == "oversized":
        assert extractor.failures[0] == tr(Msg.SUBTITLE_FILE_EXCEEDS_4_MIB)
    monkeypatch.setattr(subtitles, "LOAD_TIMEOUT_MS", 30000)
    fake_ffmpeg(f"sys.stdout.write({CAPTION!r})\n")
    extractor.load("video.mkv", 0)
    wait(lambda: bool(extractor.results))
    assert extractor.cues == [(0, 6, "Selected caption")]


@pytest.fixture
def video(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "movie.mkv").write_bytes(b"fixture only used by the fake subtitle demuxer")
    controller = VideoController(tmp_path / "state", tmp_path / "settings.json")
    controller.isolated = True
    folder = Source.create(source)
    controller.library.sources = [folder]
    controller.library.items = scan(folder, "video")
    controller.current = dict(controller.library.items[0])
    yield controller
    controller.close()


def test_subtitle_retry_clears_previous_failure(video, fake_ffmpeg):
    fake_ffmpeg("sys.stderr.write('decode failed')\nsys.exit(1)\n")
    video.set_track(True, 0)
    wait(lambda: bool(video.error))
    assert "decode failed" in render(video.error)
    fake_ffmpeg(f"sys.stdout.write({CAPTION!r})\n")
    video.set_track(True, 0)
    wait(lambda: video.embedded_subtitles.cues is not None)
    assert not video.error and not video.notice
    assert video.subtitle_text() == "Selected caption"


def test_changing_subtitles_preserves_an_unrelated_playback_error(video, fake_ffmpeg):
    fake_ffmpeg("sys.stderr.write('decode failed')\nsys.exit(1)\n")
    video.set_track(True, 0)
    wait(lambda: bool(video.error))
    video.playback_failed("Video decoder failed")
    error = video.error
    video.set_track(True, -1)
    assert video.error == error


@pytest.mark.parametrize("action", ["off", "external", "source", "file", "close"])
def test_controller_cancels_pending_subtitles(video, fake_ffmpeg, tmp_path, action):
    fake_ffmpeg(f"time.sleep(0.2)\nsys.stdout.write({CAPTION!r})\n")
    video.set_track(True, 0)
    if action == "off":
        video.set_track(True, -1)
    elif action == "external":
        external = tmp_path / "external.srt"
        external.write_text(CAPTION.replace("Selected", "External"))
        video.load_subtitles(external)
    elif action == "source":
        video.media.player.sourceChanged.emit(video.media.player.source())
    elif action == "file":
        assert video.prepare_play(video.current, 0, False, False)
    else:
        video.close()
    events(350)
    assert video.embedded_subtitles.cues is None
    assert video.embedded_subtitles.process is None
    assert not video.notice and not video.error
    assert video.subtitle_text() == ("External caption" if action == "external" else "")


def test_replaced_media_is_revalidated_before_captions_are_used(video, fake_ffmpeg):
    fake_ffmpeg(f"time.sleep(0.15)\nsys.stdout.write({CAPTION!r})\n")
    video.set_track(True, 0)
    Path(video.current["path"]).write_bytes(b"replaced")
    wait(lambda: bool(video.error))
    assert render(tr(Msg.THE_FILE_HAS_CHANGED_REFRESH_THE_LIBRARY_BEFORE_OPENING_IT)) in render(video.error)
    assert not video.subtitle_text()


def test_subtitles_can_be_turned_off_after_the_media_disappears(video, fake_ffmpeg):
    fake_ffmpeg(f"time.sleep(0.2)\nsys.stdout.write({CAPTION!r})\n")
    video.set_track(True, 0)
    Path(video.current["path"]).unlink()
    video.set_track(True, -1)
    events(350)
    assert not video.error and not video.notice and not video.subtitle_text()
    assert video.embedded_subtitles.process is None


def test_embedded_captions_follow_selection_and_seeks_in_the_visible_window(tmp_path):
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg is required for the original embedded subtitle fixture")
    result = subprocess.run([sys.executable, "tests/video_subtitle_probe.py", str(tmp_path)],
                            env={**os.environ, "QT_QPA_PLATFORM": "offscreen",
                                 "QT_QUICK_BACKEND": "software", "PYTHONPATH": "src",
                                 "QT_QUICK_CONTROLS_STYLE": "Basic",
                                 "PYTHONFAULTHANDLER": "1"},
                            capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads((tmp_path / "report.json").read_text())
    assert report["passed"] and report["qmlErrors"] == []
