"""
[INPUT]: 依赖真实 Qt 独立进程探针和双主题。
[OUTPUT]: 验证弹窗尺寸连续性和加载退出快照。
[POS]: 动画回归入口；不将离屏结果视为实机帧率。
[PROTOCOL]: Update this header on change, then check AGENTS.md
"""

import os
import subprocess
import sys

import pytest


@pytest.mark.parametrize("scenario", ["loading", "dialog", "first-open", "mid-close"])
@pytest.mark.parametrize("theme", ["classic", "dark"])
@pytest.mark.parametrize("reduced", [False, True])
def test_dialog_motion_continuity(tmp_path, scenario, theme, reduced):
    result = subprocess.run(
        [sys.executable, "tests/dialog_motion_continuity_probe.py", str(tmp_path), scenario, theme, str(int(reduced))],
        env={**os.environ, "PYTHONPATH": "src", "QT_QPA_PLATFORM": "offscreen",
             "QT_QUICK_BACKEND": "software", "QT_QUICK_CONTROLS_STYLE": "Basic",
             "UDECK_REDUCED_MOTION": "1" if reduced else "0"},
        capture_output=True, text=True, timeout=20,
    )
    assert result.returncode == 0, result.stdout + result.stderr
