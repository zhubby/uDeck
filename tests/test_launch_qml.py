import json
import os
import subprocess
import sys

import pytest


@pytest.mark.parametrize("width,height", [(1280, 720), (960, 600)])
@pytest.mark.parametrize("language", ["en", "zh_CN"])
@pytest.mark.parametrize("theme", ["classic", "dark"])
@pytest.mark.parametrize("reduced", [False, True])
def test_loading_layers_render_and_release_keyboard_focus(tmp_path, width, height, language, theme, reduced):
    result = subprocess.run(
        [sys.executable, "tests/launch_qml_probe.py", str(tmp_path), "--width", str(width),
         "--height", str(height), "--language", language, "--theme", theme,
         *(["--reduced-motion"] if reduced else [])],
        env={**os.environ, "PYTHONPATH": "src", "QT_QPA_PLATFORM": "offscreen",
             "QT_QUICK_BACKEND": "software", "QT_QUICK_CONTROLS_STYLE": "Basic"},
        capture_output=True, text=True, timeout=25,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout.strip().splitlines()[-1])
    assert report["qmlErrors"] == []
    assert report["focusRestored"]
    assert len(report["captures"]) == 4
    assert all((tmp_path / (name + ".png")).stat().st_size > 1000 for name in report["captures"])


def test_main_reports_desktop_frame_separately_from_loading_frame(tmp_path):
    result = subprocess.run(
        [sys.executable, "-m", "udeck.main", "--mock", "--windowed", "--smoke-test",
         "--quit-after", "1.8"],
        env={**os.environ, "PYTHONPATH": "src", "QT_QPA_PLATFORM": "offscreen",
             "QT_QUICK_BACKEND": "software"},
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout.strip().splitlines()[-1])
    assert report["qmlErrors"] == []
    diagnostics = report["diagnostics"]
    assert 0 < diagnostics["startupFrameSeconds"] < diagnostics["firstFrameSeconds"]
