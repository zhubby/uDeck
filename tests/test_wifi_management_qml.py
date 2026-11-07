import json
import os
import subprocess
import sys

import pytest


@pytest.mark.parametrize(("width", "height"), [(1280, 720), (960, 600)])
@pytest.mark.parametrize(("language", "theme"), [("en", "classic"), ("en", "dark"), ("zh_CN", "classic"), ("zh_CN", "dark")])
def test_network_management_menus_fit_and_keep_keyboard_focus(tmp_path, width, height, language, theme):
    result = subprocess.run(
        [sys.executable, "tests/wifi_management_qml_probe.py", str(tmp_path), "--width", str(width), "--height", str(height),
         "--language", language, "--theme", theme],
        env={**os.environ, "PYTHONPATH": "src", "QT_QPA_PLATFORM": "offscreen", "QT_QUICK_BACKEND": "software", "QT_QUICK_CONTROLS_STYLE": "Basic"},
        text=True, capture_output=True, timeout=35)
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert report["qmlErrors"] == []
    assert len(report["scenarios"]) == 12
    assert len(list(tmp_path.glob("*.png"))) == 12
    assert "Error" not in result.stderr, result.stderr
