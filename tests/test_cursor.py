"""
[INPUT]: 依赖桌面与真实原生入口的独立 Qt 探针。
[OUTPUT]: 验证圆点动效、输入穿透与窗口切换清理。
[POS]: 统一指针样式和生命周期的回归入口。
[PROTOCOL]: Update this header on change, then check AGENTS.md
"""

import json
import os
import subprocess
import sys

import pytest


@pytest.mark.parametrize("width,height", [(1280, 720), (960, 600)])
@pytest.mark.parametrize("theme", ["classic", "dark"])
@pytest.mark.parametrize("reduced", [False, True])
def test_trackball_cursor_visibility_navigation_and_rendering(tmp_path, width, height, theme, reduced):
    result = subprocess.run(
        [sys.executable, "tests/cursor_qml_probe.py", str(tmp_path), "--width", str(width),
         "--height", str(height), "--theme", theme,
         *(["--reduced-motion"] if reduced else [])],
        env={**os.environ, "PYTHONPATH": "src", "QT_QPA_PLATFORM": "offscreen",
             "QT_QUICK_BACKEND": "software", "QT_QUICK_CONTROLS_STYLE": "Basic"},
        capture_output=True, text=True, timeout=25,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout.strip().splitlines()[-1])
    assert report["qmlErrors"] == []
    assert report["navigationPreserved"]
    assert report["inputReleased"]
    assert report["inactiveMotionIgnored"]
    assert report["captures"] == ["hidden", "trackball", "preview", "pressed", "click", "loading"]
    assert all((tmp_path / (name + ".png")).stat().st_size > 1000 for name in report["captures"])


@pytest.mark.parametrize("kind", ["reader", "terminal"])
@pytest.mark.parametrize("reduced", [False, True])
def test_native_windows_use_the_dot_and_preserve_pointer_delivery(tmp_path, kind, reduced):
    result = subprocess.run([sys.executable, "tests/native_cursor_probe.py", kind, str(tmp_path)],
                            env={**os.environ, "PYTHONPATH": "src", "QT_QPA_PLATFORM": "offscreen",
                                 "QT_QUICK_BACKEND": "software", "QT_QUICK_CONTROLS_STYLE": "Basic",
                                 "UDECK_REDUCED_MOTION": "1" if reduced else "0"},
                            capture_output=True, text=True, timeout=40)
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout.strip().splitlines()[-1])
    assert report["passed"] and report["inputPolicyPreserved"] and report["focusReset"]
    assert report["windows"] == (2 if kind == "terminal" else 1)
