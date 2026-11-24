"""
[INPUT]: 依赖独立 Qt 探针与 FFmpeg 的真实媒体输出。
[OUTPUT]: 验证长 GOP TS 定位画面、准备期暂停与资源释放。
[POS]: 媒体引擎的真实播放和子进程生命周期回归。
[PROTOCOL]: Update this header on change, then check AGENTS.md
"""

import json
import os
import shutil
import subprocess
import sys
import wave
from pathlib import Path

import pytest
from PySide6.QtCore import QProcess
from test_video_playback import wait_for

from udeck.apps.common.library import Source, scan
from udeck.apps.media.engine import MediaEngine
from udeck.apps.media.seekable import SeekableSource
from udeck.apps.video.controller import VideoController
from udeck.i18n import Msg, tr


@pytest.fixture
def source(tmp_path):
    path = tmp_path / "original.TS"
    path.write_bytes(b"original source")
    return path


@pytest.fixture
def prepared(tmp_path):
    instance = SeekableSource(directory=tmp_path)
    try:
        yield instance
    finally:
        instance.close()


def fake_ffmpeg(tmp_path, monkeypatch, script):
    executable = tmp_path / "ffmpeg fixture"
    executable.write_text("#!" + sys.executable + "\n" + script)
    executable.chmod(0o700)
    monkeypatch.setattr("udeck.apps.media.seekable.shutil.which", lambda _name: str(executable))
    return executable


def test_preparing_the_same_source_does_not_publish_a_partial_file(prepared, source, tmp_path, monkeypatch):
    fake_ffmpeg(tmp_path, monkeypatch,
                "import sys,time\nfrom pathlib import Path\n"
                "Path(sys.argv[-1]).write_bytes(b'partial')\ntime.sleep(5)\n")
    ready = []
    prepared.ready.connect(ready.append)
    prepared.prepare(source)
    wait_for(lambda: any(tmp_path.glob("udeck-media-seek-*/playback.mkv")))

    prepared.prepare(source)

    assert ready == []


def test_complete_source_is_reused_until_original_changes(prepared, source, tmp_path, monkeypatch):
    counter = tmp_path / "invocations"
    fake_ffmpeg(tmp_path, monkeypatch,
                "import sys\nfrom pathlib import Path\n"
                f"counter=Path({str(counter)!r})\n"
                "counter.write_text(counter.read_text()+'x' if counter.exists() else 'x')\n"
                "Path(sys.argv[-1]).write_bytes(b'completed')\n")
    ready = []
    prepared.ready.connect(ready.append)
    prepared.prepare(source)
    wait_for(lambda: len(ready) == 1)
    first = Path(ready[0])

    prepared.prepare(source)

    assert ready == [str(first), str(first)]
    assert counter.read_text() == "x"
    source.write_bytes(b"new original")
    prepared.prepare(source)
    wait_for(lambda: len(ready) == 3)
    assert ready[-1] != str(first) and not first.exists()
    assert counter.read_text() == "xx"
    assert source.read_bytes() == b"new original"


def test_new_direct_source_cancels_preparation_and_ignores_old_completion(prepared, source, tmp_path, monkeypatch):
    fake_ffmpeg(tmp_path, monkeypatch, "import time\ntime.sleep(5)\n")
    direct = tmp_path / "latest.wav"
    direct.write_bytes(b"latest")
    ready, failed = [], []
    prepared.ready.connect(ready.append)
    prepared.failed.connect(failed.append)
    prepared.prepare(source)

    prepared.prepare(direct)
    wait_for(lambda: all(p.state() == QProcess.ProcessState.NotRunning
                         for p in prepared.findChildren(QProcess)))

    assert ready == [str(direct)] and failed == []
    assert not list(tmp_path.glob("udeck-media-seek-*"))
    assert source.read_bytes() == b"original source"


@pytest.mark.parametrize("failure", ["exit", "timeout", "oversize", "start"])
def test_failed_preparation_cleans_temporary_files(prepared, source, tmp_path, monkeypatch, failure):
    scripts = {
        "exit": "import sys\nsys.stderr.write('test conversion failed')\nsys.exit(9)\n",
        "timeout": "import time\ntime.sleep(5)\n",
        "oversize": "import sys,time\nfrom pathlib import Path\n"
                    "Path(sys.argv[-1]).write_bytes(b'x'*(2*1024*1024))\ntime.sleep(5)\n",
        "start": "",
    }
    executable = fake_ffmpeg(tmp_path, monkeypatch, scripts[failure])
    if failure == "start":
        executable.unlink()
    if failure == "timeout":
        monkeypatch.setattr("udeck.apps.media.seekable.PREPARE_TIMEOUT_MS", 20)
    ready, failed = [], []
    prepared.ready.connect(ready.append)
    prepared.failed.connect(failed.append)

    prepared.prepare(source)
    wait_for(lambda: bool(failed))
    prepared.close()

    assert ready == [] and len(failed) == 1
    if failure == "timeout":
        assert failed == [tr(Msg.MEDIA_PREPARATION_TIMED_OUT)]
    elif failure == "oversize":
        assert failed == [tr(Msg.MEDIA_PREPARATION_SPACE)]
    elif failure == "exit":
        assert "test conversion failed" in failed[0]
    assert not list(tmp_path.glob("udeck-media-seek-*"))
    assert source.read_bytes() == b"original source"


def test_source_change_during_preparation_cannot_publish_stale_media(prepared, source, tmp_path, monkeypatch):
    fake_ffmpeg(tmp_path, monkeypatch,
                "import sys,time\nfrom pathlib import Path\n"
                "time.sleep(.3)\nPath(sys.argv[-1]).write_bytes(b'completed')\n")
    ready, failed = [], []
    prepared.ready.connect(ready.append)
    prepared.failed.connect(failed.append)
    prepared.prepare(source)
    source.write_bytes(b"changed source")
    wait_for(lambda: bool(failed))

    assert ready == []
    assert failed == [tr(Msg.THE_FILE_HAS_CHANGED_REFRESH_THE_LIBRARY_BEFORE_OPENING_IT)]
    assert source.read_bytes() == b"changed source"


@pytest.mark.parametrize("unavailable", ["space", "ffmpeg"])
def test_unavailable_preparation_keeps_resume_state_out_of_player(source, monkeypatch, unavailable):
    if unavailable == "space":
        from types import SimpleNamespace

        monkeypatch.setattr("udeck.apps.media.seekable.shutil.which", lambda _name: sys.executable)
        monkeypatch.setattr("udeck.apps.media.seekable.shutil.disk_usage",
                            lambda _path: SimpleNamespace(free=0))
        expected = Msg.MEDIA_PREPARATION_SPACE
    else:
        monkeypatch.setattr("udeck.apps.media.seekable.shutil.which", lambda _name: None)
        expected = Msg.MEDIA_PREPARATION_UNAVAILABLE
    engine = MediaEngine()
    failed = []
    engine.failed.connect(failed.append)
    try:
        engine.load({"id": "saved-video", "path": str(source)}, 8000)

        assert failed == [tr(expected)]
        assert not engine.loading and not engine.identifier
        assert engine.player.source().isEmpty()
        assert source.read_bytes() == b"original source"
    finally:
        engine.close()


@pytest.mark.parametrize("reason", ["back", "takeover"])
def test_preparation_cannot_restart_playback_after_pause_intent(source, tmp_path, monkeypatch, reason):
    audio = tmp_path / "prepared.wav"
    with wave.open(str(audio), "wb") as stream:
        stream.setparams((1, 2, 8000, 0, "NONE", "not compressed"))
        stream.writeframes(b"\0\0" * 80000)
    fake_ffmpeg(tmp_path, monkeypatch,
                "import sys,time,shutil\n"
                f"time.sleep(.3)\nshutil.copyfile({str(audio)!r},sys.argv[-1])\n")
    controller = VideoController(tmp_path / "state", tmp_path / "settings.json")
    controller.isolated = True
    controller.media.output.setMuted(True)
    folder = Source.create(tmp_path)
    controller.library.sources = [folder]
    controller.library.items = scan(folder, "video")
    item = controller.library.items[0]
    controller.store.data["positions"][item["id"]] = 8
    try:
        controller.play(item, 8)
        assert controller.media.loading
        if reason == "back":
            controller.back()
            assert controller.page == "library"
        else:
            from types import SimpleNamespace

            owner = SimpleNamespace(isValid=lambda: False)
            bus = SimpleNamespace(interface=lambda: SimpleNamespace(serviceOwner=lambda _name: owner))
            monkeypatch.setattr("udeck.apps.media.controller.QDBusConnection",
                                SimpleNamespace(sessionBus=lambda: bus))
            controller.playback_owner_changed("io.github.zhubby.uDeck.MediaPlayback", "", ":other")
        wait_for(lambda: not controller.media.loading)

        assert not controller.media.player.errorString()
        assert not controller.media.snapshot()["playing"]
        assert controller.store.data["positions"][item["id"]] == 8
        assert controller.media.player.position() >= 7900
        controller.command("play-pause")
        wait_for(lambda: controller.media.snapshot()["playing"])
        assert controller.media.player.position() >= 7900
    finally:
        controller.close()


def test_long_gop_ts_resume_and_seeks_produce_decoded_pictures(tmp_path):
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg is required for the original TS fixture")
    result = subprocess.run(
        [sys.executable, str(Path(__file__).with_name("media_seek_probe.py")),
         str(tmp_path / "source with spaces")],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen", "PYTHONPATH": "src"},
        capture_output=True, text=True, timeout=45,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout.strip().splitlines()[-1])
    assert report["resumedFrames"] and report["backwardFrames"] and report["forwardFrames"]
    assert report["sourceUnchanged"] and report["decodedPicturesUnchanged"]
