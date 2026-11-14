import json
import os
import subprocess
import sys

import pytest


def run_probe(tmp_path, width, height, language, theme, *extra):
    result = subprocess.run(
        [sys.executable, "tests/settings_qml_probe.py", str(tmp_path), "--width", str(width),
         "--height", str(height), "--language", language, "--theme", theme, *extra],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen", "QT_QUICK_BACKEND": "software",
             "QT_QUICK_CONTROLS_STYLE": "Basic", "PYTHONPATH": "src"},
        text=True, capture_output=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert report["qmlErrors"] == []
    assert len(report["captures"]) == 11
    assert len(list(tmp_path.glob("*.png"))) == 11
    assert "Error" not in result.stderr, result.stderr
    return report


@pytest.mark.parametrize(("width", "height"), [(1280, 720), (960, 600)])
@pytest.mark.parametrize(("language", "theme"), [("en", "classic"), ("en", "dark"), ("zh_CN", "classic"), ("zh_CN", "dark")])
def test_timezone_and_key_test_render_and_receive_actual_keyboard_events(tmp_path, width, height, language, theme):
    run_probe(tmp_path, width, height, language, theme)


def test_settings_clock_refreshes_after_a_minute_rollover(tmp_path):
    report = run_probe(tmp_path, 1280, 720, "en", "classic", "--clock-rollover")
    assert report["clock"] == "09:01"


@pytest.mark.parametrize(("width", "height"), [(1280, 720), (960, 600)])
@pytest.mark.parametrize(("language", "theme"), [("en", "classic"), ("en", "dark"), ("zh_CN", "classic"), ("zh_CN", "dark")])
def test_system_information_renders_scrolls_refreshes_and_returns_with_keyboard(tmp_path, width, height, language, theme):
    result = subprocess.run(
        [sys.executable, "tests/settings_qml_probe.py", str(tmp_path), "--width", str(width),
         "--height", str(height), "--language", language, "--theme", theme, "--system-info"],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen", "QT_QUICK_BACKEND": "software",
             "QT_QUICK_CONTROLS_STYLE": "Basic", "PYTHONPATH": "src"},
        text=True, capture_output=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert report["qmlErrors"] == []
    assert len(report["captures"]) == 5
    assert len(list(tmp_path.glob("*.png"))) == 5
    assert "Error" not in result.stderr, result.stderr
