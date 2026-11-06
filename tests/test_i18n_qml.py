import json
import os
import subprocess
import sys

import pytest


@pytest.mark.parametrize(("module", "language", "description", "error"), [
    ("udeck.main", "en", "uDeck · Button-first desktop for uConsole", "--smoke-test requires --mock"),
    ("udeck.main", "zh_CN", "uDeck · uConsole 按键原生桌面", "--smoke-test 必须同时使用 --mock"),
    ("udeck.terminal.main", "en", "uDeck Terminal · Button-first terminal", "--smoke-test requires --mock"),
    ("udeck.terminal.main", "zh_CN", "uDeck Terminal · 按键原生终端", "--smoke-test 必须配合 --mock"),
])
def test_command_line_renders_messages_in_the_saved_language(tmp_path, module, language, description, error):
    path = tmp_path / "udeck/settings.json"
    path.parent.mkdir()
    path.write_text(json.dumps({"preferences": {"language": language}}))
    environment = {**os.environ, "XDG_CONFIG_HOME": str(tmp_path), "PYTHONPATH": "src"}
    help_result = subprocess.run([sys.executable, "-m", module, "--help"],
                                 env=environment, capture_output=True, text=True, timeout=10)
    assert help_result.returncode == 0
    assert description in help_result.stdout
    error_result = subprocess.run([sys.executable, "-m", module, "--smoke-test"],
                                  env=environment, capture_output=True, text=True, timeout=10)
    assert error_result.returncode == 2
    assert error in error_result.stderr


@pytest.mark.parametrize("language", ["en", "zh_CN"])
@pytest.mark.parametrize(("width", "height"), [(1280, 720), (960, 600)])
def test_languages_render_and_switch_in_live_qml_without_restarting_sessions(tmp_path, language, width, height):
    result = subprocess.run(
        [sys.executable, "tests/i18n_qml_probe.py", language, str(tmp_path),
         "--width", str(width), "--height", str(height)],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen", "QT_QUICK_BACKEND": "software", "PYTHONPATH": "src"},
        capture_output=True, text=True, timeout=25,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert report["language"] == language
    assert report["qmlErrors"] == []
    assert report["sessionsPreserved"]
    assert len(report["captures"]) == 11
    assert "Error" not in result.stderr, result.stderr
    assert all((tmp_path / (name + ".png")).stat().st_size > 10000 for name in report["captures"])


@pytest.mark.parametrize(("language", "expected"), [("en", "Cannot run program: "), ("zh_CN", "无法运行程序：")])
def test_terminal_startup_errors_use_the_saved_language(tmp_path, language, expected):
    path = tmp_path / "udeck/settings.json"
    path.parent.mkdir()
    path.write_text(json.dumps({"preferences": {"language": language}}))
    result = subprocess.run(
        [sys.executable, "-m", "udeck.terminal.main", "--mock", "-e", "/nonexistent-udeck-program"],
        env={**os.environ, "XDG_CONFIG_HOME": str(tmp_path), "QT_QPA_PLATFORM": "offscreen", "PYTHONPATH": "src"},
        capture_output=True, text=True, timeout=15,
    )
    assert result.returncode == 2
    assert expected + "/nonexistent-udeck-program" in result.stderr
