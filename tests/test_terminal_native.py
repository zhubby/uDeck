import os
import subprocess
import sys
from pathlib import Path

import pytest


def test_native_pty_and_buffer_contract(tmp_path):
    root = Path(__file__).resolve().parent.parent
    plugin = Path(os.environ.get("UDECK_TERMINAL_PLUGIN_PATH", root / "build/terminal-plugin"))
    if not (plugin / "QMLTermWidget/qmldir").is_file():
        if os.environ.get("UDECK_REQUIRE_NATIVE"):
            pytest.fail("Required native plugin has not been built")
        pytest.skip("Build the native plugin to exercise real PTY/buffer integration")
    result = subprocess.run([sys.executable, str(root / "tests/native_terminal_probe.py"), str(plugin), str(tmp_path)],
                            capture_output=True, text=True, timeout=25,
                            env={**os.environ, "QT_QPA_PLATFORM": "offscreen", "QT_QUICK_BACKEND": "software"})
    assert result.returncode == 0, result.stdout + result.stderr
    assert '"native": "passed"' in result.stdout


def test_application_session_lifecycle():
    root = Path(__file__).resolve().parent.parent
    plugin = Path(os.environ.get("UDECK_TERMINAL_PLUGIN_PATH", root / "build/terminal-plugin"))
    if not (plugin / "QMLTermWidget/qmldir").is_file():
        if os.environ.get("UDECK_REQUIRE_NATIVE"):
            pytest.fail("Required native plugin has not been built")
        pytest.skip("Native plugin required")
    result = subprocess.run([sys.executable, str(root / "tests/terminal_application_probe.py")],
                            capture_output=True, text=True, timeout=25,
                            env={**os.environ, "PYTHONPATH": str(root / "src"), "QT_QPA_PLATFORM": "offscreen", "QT_QUICK_BACKEND": "software", "QT_QUICK_CONTROLS_STYLE": "Basic"})
    assert result.returncode == 0, result.stdout + result.stderr
    assert '"application":"passed"' in result.stdout
