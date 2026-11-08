import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


def test_shell_package_declares_the_svg_loader_for_home_icons():
    script = (Path(__file__).resolve().parents[1] / "tools/build-deb").read_text()
    dependencies = next(line for line in script.splitlines() if line.startswith("Depends:"))
    assert "qt6-svg-plugins" in [package.strip() for package in dependencies.removeprefix("Depends:").split(",")]


@pytest.mark.parametrize("width,height", [(1280, 720), (960, 600)])
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
    assert report["shortcutCount"] == 6
    assert report["focusRestored"]
    assert len(report["captures"]) == 5
    assert all((tmp_path / (name + ".png")).stat().st_size > 10000 for name in report["captures"])
