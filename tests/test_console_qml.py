import json
import os
import subprocess
import sys

import pytest


@pytest.mark.parametrize('language,theme', [('en', 'classic'), ('zh_CN', 'classic'), ('en', 'dark'), ('zh_CN', 'dark')])
@pytest.mark.parametrize('width,height', [(1280, 720), (960, 600)])
def test_console_keyboard_routes_render_in_both_languages_and_themes(tmp_path, language, theme, width, height):
    result = subprocess.run(
        [sys.executable, 'tests/console_qml_probe.py', str(tmp_path), '--language', language,
         '--theme', theme, '--width', str(width), '--height', str(height)],
        env={**os.environ, 'PYTHONPATH': 'src', 'QT_QPA_PLATFORM': 'offscreen', 'QT_QUICK_BACKEND': 'software',
             'QT_QUICK_CONTROLS_STYLE': 'Basic'}, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)['qmlErrors'] == []
    assert (tmp_path / 'console.png').stat().st_size > 10000
