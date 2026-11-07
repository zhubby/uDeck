import json
import os
import subprocess
import sys

import pytest


@pytest.mark.parametrize(("width", "height"), [(1280, 720), (960, 600)])
@pytest.mark.parametrize(("language", "theme", "scale"), [("en", "classic", "1"), ("en", "dark", "2"), ("zh_CN", "classic", "1.5"), ("zh_CN", "dark", "1")])
def test_radio_icons_follow_live_state_without_replacing_input_or_overlapping(tmp_path, width, height, language, theme, scale):
    result = subprocess.run(
        [sys.executable, "tests/wireless_status_qml_probe.py", str(tmp_path), "--width", str(width),
         "--height", str(height), "--language", language, "--theme", theme],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen", "QT_QUICK_BACKEND": "software",
             "QT_QUICK_CONTROLS_STYLE": "Basic", "QT_SCALE_FACTOR": scale, "PYTHONPATH": "src"},
        text=True, capture_output=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert report["qmlErrors"] == []
    assert len(report["scenarios"]) == 19
    assert len(list(tmp_path.glob("*.png"))) == 19
    assert "Error" not in result.stderr, result.stderr
