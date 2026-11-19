"""
[INPUT]: 依赖共享应用的独立 Qt 探针。
[OUTPUT]: 验证连续切页、封面身份和单次标题滚动。
[POS]: 应用动效连续性的离屏回归入口。
[PROTOCOL]: Update this header on change, then check AGENTS.md
"""

import json
import os
import subprocess
import sys

import pytest


@pytest.mark.parametrize('mode', ['pages', 'artwork', 'titles'])
@pytest.mark.parametrize('reduced', [False, True])
@pytest.mark.parametrize('theme', ['classic', 'dark'])
def test_shared_app_motion_keeps_the_latest_content(tmp_path, mode, reduced, theme):
    result = subprocess.run(
        [sys.executable, 'tests/apps_motion_continuity_probe.py', str(tmp_path), mode, theme],
        env={**os.environ, 'PYTHONPATH': 'src', 'QT_QPA_PLATFORM': 'offscreen',
             'QT_QUICK_BACKEND': 'software', 'QT_QUICK_CONTROLS_STYLE': 'Basic',
             'UDECK_REDUCED_MOTION': '1' if reduced else '0'},
        capture_output=True, text=True, timeout=25,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout.strip().splitlines()[-1])
    assert report['passed'] and report['mode'] == mode
