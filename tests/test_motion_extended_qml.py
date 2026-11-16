"""
[INPUT]: 依赖真实 QML 探针、双主题和减少动画开关。
[OUTPUT]: 验证补位、Toast、封面和共享应用输入边界。
[POS]: 完整动效的独立进程回归入口。
[PROTOCOL]: Update this header on change, then check AGENTS.md
"""

import json
import os
import subprocess
import sys

import pytest


@pytest.mark.parametrize("theme", ["classic", "dark"])
@pytest.mark.parametrize("reduced", [False, True])
def test_extended_motion_keeps_content_and_input_current(tmp_path, theme, reduced):
    result = subprocess.run(
        [sys.executable, "tests/motion_extended_probe.py", str(tmp_path), theme],
        env={**os.environ, "PYTHONPATH": "src", "QT_QPA_PLATFORM": "offscreen",
             "QT_QUICK_BACKEND": "software", "QT_QUICK_CONTROLS_STYLE": "Basic",
             "UDECK_REDUCED_MOTION": "1" if reduced else "0"},
        capture_output=True, text=True, timeout=35,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout.strip().splitlines()[-1])
    assert report["qmlErrors"] == []
    assert all(report[name] for name in ("rowReflow", "toastRetained", "coverReadyFade", "appInputImmediate"))
