import json
import os
import subprocess
import sys

import pytest


@pytest.mark.parametrize("width,height", [(1280, 720), (960, 600), (1920, 1080)])
@pytest.mark.parametrize("language,theme", [("en", "classic"), ("zh_CN", "classic"), ("zh_CN", "dark")])
def test_home_shortcuts_render_and_receive_real_keyboard_navigation(tmp_path, width, height, language, theme):
    result = subprocess.run(
        [sys.executable, "tests/home_qml_probe.py", str(tmp_path), "--width", str(width),
         "--height", str(height), "--language", language, "--theme", theme],
        env={**os.environ, "PYTHONPATH": "src", "QT_QPA_PLATFORM": "offscreen",
             "QT_QUICK_BACKEND": "software", "QT_QUICK_CONTROLS_STYLE": "Basic"},
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout.strip().splitlines()[-1])
    assert report["qmlErrors"] == []
    assert report["tabCount"] == 4
    assert report["shortcutCount"] == 7
    assert report["focusRestored"]
    assert len(report["captures"]) == 6
    assert all((tmp_path / (name + ".png")).stat().st_size > 10000 for name in report["captures"])
