import json
import os
import subprocess
import sys

import pytest


@pytest.mark.parametrize("width,height", [(1280, 720), (960, 600)])
@pytest.mark.parametrize("theme", ["classic", "dark"])
@pytest.mark.parametrize("reduced", [False, True])
def test_trackball_cursor_visibility_navigation_and_rendering(tmp_path, width, height, theme, reduced):
    result = subprocess.run(
        [sys.executable, "tests/cursor_qml_probe.py", str(tmp_path), "--width", str(width),
         "--height", str(height), "--theme", theme,
         *(["--reduced-motion"] if reduced else [])],
        env={**os.environ, "PYTHONPATH": "src", "QT_QPA_PLATFORM": "offscreen",
             "QT_QUICK_BACKEND": "software", "QT_QUICK_CONTROLS_STYLE": "Basic"},
        capture_output=True, text=True, timeout=25,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout.strip().splitlines()[-1])
    assert report["qmlErrors"] == []
    assert report["navigationPreserved"]
    assert report["inputReleased"]
    assert report["inactiveMotionIgnored"]
    assert report["captures"] == ["hidden", "trackball", "preview", "loading"]
    assert all((tmp_path / (name + ".png")).stat().st_size > 1000 for name in report["captures"])
