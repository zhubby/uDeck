"""
[INPUT]: 依赖独立 QML 进程、双主题与减少动画开关。
[OUTPUT]: 验证快速导航、弹窗输入隔离和即时启动反馈。
[POS]: 桌面短过渡的 pytest 入口；实机帧耗时另记。
[PROTOCOL]: Update this header on change, then check AGENTS.md
"""

import json
import os
import subprocess
import sys

import pytest


@pytest.mark.parametrize("reduced", [False, True])
@pytest.mark.parametrize("theme", ["classic", "dark"])
def test_motion_preserves_immediate_input_and_modal_boundaries(tmp_path, reduced, theme):
    result = subprocess.run(
        [sys.executable, "tests/motion_qml_probe.py", str(tmp_path), theme],
        env={**os.environ, "PYTHONPATH": "src", "QT_QPA_PLATFORM": "offscreen",
             "QT_QUICK_BACKEND": "software", "QT_QUICK_CONTROLS_STYLE": "Basic",
             "UDECK_REDUCED_MOTION": "1" if reduced else "0"},
        capture_output=True, text=True, timeout=25,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout.strip().splitlines()[-1])
    assert report["qmlErrors"] == []
    assert report["focusRetargeted"] and report["dialogInputIsolated"]
    assert report["launchImmediate"] and report["pageDelegatesRetained"]
