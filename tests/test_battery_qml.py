import json
import os
import subprocess
import sys

import pytest


@pytest.mark.parametrize(("width", "height"), [(1280, 720), (960, 600)])
@pytest.mark.parametrize(("language", "theme"), [("en", "classic"), ("en", "dark"), ("zh_CN", "classic"), ("zh_CN", "dark")])
def test_battery_measurements_refresh_in_place_and_fit_the_information_panel(tmp_path, width, height, language, theme):
    result = subprocess.run(
        [sys.executable, "tests/battery_qml_probe.py", str(tmp_path), "--width", str(width),
         "--height", str(height), "--language", language, "--theme", theme],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen", "QT_QUICK_BACKEND": "software",
             "QT_QUICK_CONTROLS_STYLE": "Basic", "PYTHONPATH": "src"},
        text=True, capture_output=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert report["qmlErrors"] == []
    assert len(report["scenarios"]) == 8
    assert len(list(tmp_path.glob("*.png"))) == 8
    assert "Error" not in result.stderr, result.stderr
