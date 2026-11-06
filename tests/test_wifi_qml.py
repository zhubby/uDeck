import json
import os
import subprocess
import sys

import pytest


@pytest.mark.parametrize("scenario", ["adapters", "networks", "confirm", "saved", "off", "single", "empty", "unplug", "long-name"])
@pytest.mark.parametrize(("width", "height"), [(1280, 720), (960, 600)])
def test_wifi_flows_fit_the_screen_and_route_back_without_qml_warnings(tmp_path, scenario, width, height):
    screenshot = tmp_path / f"wifi-{scenario}.png"
    result = subprocess.run(
        [sys.executable, "tests/wifi_qml_probe.py", scenario, str(screenshot), "--width", str(width), "--height", str(height)],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen", "QT_QUICK_BACKEND": "software", "QT_QUICK_CONTROLS_STYLE": "Basic", "PYTHONPATH": "src"},
        capture_output=True, text=True, timeout=20,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Error" not in result.stderr, result.stderr
    report = json.loads(result.stdout)
    assert report["qmlErrors"] == []
    assert report["backReachedSettings"]
    assert len(report["bounds"]) == 2
    for item in report["bounds"]:
        assert item["x"] >= 0 and item["y"] >= 0
        assert item["x"] + item["width"] <= width + 1
        assert item["y"] + item["height"] <= height + 1
    assert screenshot.stat().st_size > 10000
