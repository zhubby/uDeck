"""
[INPUT]: 依赖离屏 Console QML 探针与主题、语言和窗口尺寸。
[OUTPUT]: 验证单行密度、详情交互、实时指标与中英文布局。
[POS]: Console 视图回归的 pytest 入口。
[PROTOCOL]: Update this header on change, then check AGENTS.md
"""

import json
import os
import subprocess
import sys

import pytest


@pytest.mark.parametrize("language", ["en", "zh_CN"])
@pytest.mark.parametrize("theme", ["classic", "dark"])
@pytest.mark.parametrize("size", [(1280, 720), (960, 600)])
def test_console_single_line_density_and_refresh_preserve_scroll(tmp_path, language, theme, size):
    result = subprocess.run([sys.executable, "tests/runtime_console_qml_probe.py", str(tmp_path / "settings.json"),
                             language, theme, str(size[0]), str(size[1])],
                            env={**os.environ, "QT_QPA_PLATFORM": "offscreen", "QT_QUICK_BACKEND": "software", "QT_QUICK_CONTROLS_STYLE": "Basic", "PYTHONPATH": "src"},
                            capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "TypeError" not in result.stderr
    report = json.loads(result.stdout)
    assert report["qmlErrors"] == []
    assert report["heights"] and all(height == 48 for height in report["heights"])
    assert report["scrollStable"] and report["index"] == 8
    assert report["detailsMouseAndKeyboard"] and report["detailsLiveMetrics"]
    assert report["detailsContained"] and report["scrimBlocksRows"]
    assert report["hoverTracksScroll"]
    assert report["title"] == ("Console" if language == "en" else "控制台")
    if size == (1280, 720):
        assert report["capacity"] >= 7
