"""
[INPUT]: 依赖独立 Qt 导航探针、双主题和临时目录。
[OUTPUT]: 验证同步发布、初始布局、切页重入与滚动改向。
[POS]: 导航连续性回归入口；离屏验证不作为实机帧率。
[PROTOCOL]: Update this header on change, then check AGENTS.md
"""

import json
import os
import subprocess
import sys

import pytest


@pytest.mark.parametrize("theme", ["classic", "dark"])
@pytest.mark.parametrize("case", ["publication", "initial-geometry", "page", "scroll", "focus", "console", "files-layout", "files-scroll", "files-task", "settings-refresh"])
def test_navigation_preserves_mid_transition_state(tmp_path, theme, case):
    result = subprocess.run(
        [sys.executable, "tests/navigation_continuity_probe.py", str(tmp_path), case, theme],
        env={**os.environ, "PYTHONPATH": "src", "QT_QPA_PLATFORM": "offscreen",
             "QT_QUICK_BACKEND": "software", "QT_QUICK_CONTROLS_STYLE": "Basic",
             "UDECK_REDUCED_MOTION": "0"},
        capture_output=True, text=True, timeout=25,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout.strip().splitlines()[-1])
    assert report["status"] == "passed" and report["qmlErrors"] == []
