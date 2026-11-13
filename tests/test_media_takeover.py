"""Music and video use one output with automatic, bidirectional preemption."""

import json
import os
import shutil
import subprocess
import sys

import pytest


def test_real_music_and_video_preempt_each_other_without_automatic_resume(tmp_path):
    if sys.platform != "linux" or not shutil.which("dbus-run-session") or not shutil.which("ffmpeg"):
        pytest.skip("Real process arbitration needs Linux, D-Bus and original media fixtures")
    result = subprocess.run(
        ["dbus-run-session", "--", sys.executable, "tests/media_takeover_probe.py", str(tmp_path)],
        env={**os.environ, "PYTHONPATH": "src", "QT_QPA_PLATFORM": "offscreen",
             "QT_QUICK_BACKEND": "software"}, capture_output=True, text=True, timeout=100)
    assert result.returncode == 0, result.stdout + result.stderr + "\n" + "\n".join(
        path.read_text() for path in tmp_path.glob("*.log"))
    assert json.loads(result.stdout.strip().splitlines()[-1])["passed"]
