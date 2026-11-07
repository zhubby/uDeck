import json
import os
import subprocess
import sys

import pytest


@pytest.mark.parametrize("language", ["en", "zh_CN"])
@pytest.mark.parametrize("width,height", [(1280, 720), (960, 600)])
def test_both_themes_render_and_sync_without_recreating_native_windows(tmp_path, language, width, height):
    result = subprocess.run(
        [sys.executable, "tests/theme_qml_probe.py", str(tmp_path), "--language", language,
         "--width", str(width), "--height", str(height)],
        env={**os.environ, "PYTHONPATH": "src", "QT_QPA_PLATFORM": "offscreen", "QT_QUICK_BACKEND": "software"},
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout.strip().splitlines()[-1])
    assert report["qmlErrors"] == [] and report["sessionsPreserved"]
    assert report["liveWindows"] == 8
    assert len(report["captures"]) == 36
    assert all((tmp_path / (name + ".png")).stat().st_size > 10000 for name in report["captures"])
