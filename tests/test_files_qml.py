import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize("language", ["en", "zh_CN"])
@pytest.mark.parametrize("theme", ["classic", "dark"])
@pytest.mark.parametrize("size", [(1280, 720), (960, 600)])
def test_files_workspace_renders_with_controller_navigation(tmp_path, language, theme, size):
    result = subprocess.run(
        [sys.executable, str(Path(__file__).with_name("files_qml_probe.py")), str(tmp_path), language, theme,
         str(size[0]), str(size[1])],
        env={**os.environ, "PYTHONPATH": "src", "QT_QPA_PLATFORM": "offscreen", "QT_QUICK_BACKEND": "software"},
        capture_output=True, text=True, timeout=25,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout.strip().splitlines()[-1])
    assert report["qmlErrors"] == []
    assert report["selectionCount"] == 1
    assert (tmp_path / "files.png").stat().st_size > 10000
