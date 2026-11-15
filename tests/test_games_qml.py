import json
import os
import subprocess
import sys

import pytest


@pytest.mark.parametrize("theme", ["classic", "dark"])
@pytest.mark.parametrize("language", ["en", "zh_CN"])
def test_games_settings_and_focus_with_real_qt_events(tmp_path, language, theme):
    result = subprocess.run([sys.executable, "tests/games_qml_probe.py", str(tmp_path), language, theme],
                            env={**os.environ, "QT_QPA_PLATFORM": "offscreen", "QT_QUICK_BACKEND": "software",
                                 "QT_QUICK_CONTROLS_STYLE": "Basic", "PYTHONPATH": "src"},
                            capture_output=True, text=True, timeout=45)
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout.strip().splitlines()[-1])["qmlErrors"] == []
    assert all((tmp_path / (name + ".png")).stat().st_size > 10000
               for name in ("platforms", "empty-platform", "library", "settings", "cores",
                            "save-management", "save-confirmation", "save-history", "save-settings",
                            "thumbnail-boxart", "thumbnail-snapshot", "scan-preview"))


@pytest.mark.parametrize("theme", ["classic", "dark"])
@pytest.mark.parametrize("language", ["en", "zh_CN"])
def test_game_titles_scroll_on_all_platforms_and_collections(tmp_path, language, theme):
    result = subprocess.run([sys.executable, "tests/games_qml_probe.py", str(tmp_path), language, theme, "titles"],
                            env={**os.environ, "QT_QPA_PLATFORM": "offscreen", "QT_QUICK_BACKEND": "software",
                                 "QT_QUICK_CONTROLS_STYLE": "Basic", "PYTHONPATH": "src"},
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout.strip().splitlines()[-1])
    assert report["qmlErrors"] == [] and report["platforms"] == ["gb", "gbc", "gba", "nes", "psp"]
    assert all((tmp_path / (name + ".png")).stat().st_size > 10000
               for name in ("game-title-scrolling", "game-title-end", "favorite-title-scrolling"))
