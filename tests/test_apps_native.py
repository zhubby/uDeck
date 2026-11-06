import json
import os
import shutil
import subprocess
import sys

import pytest


@pytest.mark.parametrize("app", ["music", "video", "reader", "browser"])
def test_real_engines_with_original_content_and_qml_workflows(tmp_path, app):
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg is required for original native fixtures")
    result = subprocess.run([sys.executable, "tests/apps_native_probe.py", app, str(tmp_path)],
                            env={**os.environ, "QT_QPA_PLATFORM": "offscreen", "QT_QUICK_BACKEND": "software",
                                 "PYTHONPATH": "src"}, capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout.strip().splitlines()[-1])
    assert report["qmlErrors"] == [] and report["checks"]


@pytest.mark.parametrize("app", ["music", "video", "browser", "reader", "games"])
@pytest.mark.parametrize("language", ["en", "zh_CN"])
def test_native_app_empty_library_menus_and_translations(tmp_path, app, language):
    result = subprocess.run([sys.executable, "-m", "udeck.apps.main", app, "--isolated", "--smoke-test",
                             "--language", language, "--width", "960", "--height", "600",
                             "--screenshot", str(tmp_path / "screen.png")],
                            env={**os.environ, "QT_QPA_PLATFORM": "offscreen", "QT_QUICK_BACKEND": "software",
                                 "PYTHONPATH": "src"}, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout.strip().splitlines()[-1])["qmlErrors"] == []
    assert (tmp_path / "screen.png").stat().st_size > 10000
