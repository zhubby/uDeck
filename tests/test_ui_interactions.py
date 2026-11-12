import os
import shutil
import subprocess
import sys

import pytest


def run_probe(tmp_path, surface, scenario, *arguments):
    result = subprocess.run(
        [sys.executable, "tests/ui_interaction_probe.py", str(tmp_path), surface, scenario,
         *map(str, arguments)],
        env={**os.environ, "PYTHONPATH": "src", "QT_QPA_PLATFORM": "offscreen",
             "QT_QUICK_BACKEND": "software", "QT_QUICK_CONTROLS_STYLE": "Basic",
             "QTWEBENGINE_DISABLE_SANDBOX": "1"},
        capture_output=True, text=True, timeout=45,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("action", ["enter", "accept", "escape"])
def test_repeated_browser_address_shortcut_keeps_one_matching_draft(tmp_path, action):
    run_probe(tmp_path, "browser", "address", action)


def test_same_title_prompts_restore_their_own_drafts_without_resetting_edits(tmp_path):
    run_probe(tmp_path, "reader", "prompt-identity")


@pytest.mark.parametrize("surface", ["shell", "terminal", "music", "video", "browser",
                                         "reader", "emulator"])
@pytest.mark.parametrize("key", ["Return", "Enter", "Escape"])
def test_composition_keys_do_not_submit_or_close_input(tmp_path, surface, key):
    run_probe(tmp_path, surface, "composition", key)


@pytest.mark.parametrize("key", ["Up", "Down"])
def test_terminal_composition_arrows_do_not_start_search(tmp_path, key):
    run_probe(tmp_path, "terminal", "composition", key)


@pytest.mark.parametrize("surface", ["music", "video"])
def test_held_enter_toggles_real_playback_once_and_arrows_still_repeat(tmp_path, surface):
    if surface == "video" and not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg is required for the original video fixture")
    run_probe(tmp_path, surface, "repeat")


def test_video_pointer_wakes_controls_without_stealing_buttons_or_slider(tmp_path):
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg is required for the original video fixture")
    run_probe(tmp_path, "video", "pointer")


@pytest.mark.parametrize("width,height", [(800, 500), (960, 600), (1280, 720)])
@pytest.mark.parametrize("language", ["en", "zh_CN"])
def test_music_controls_fit_clipped_surface_and_long_metadata_can_scroll(
    tmp_path, width, height, language,
):
    run_probe(tmp_path, "music", "layout", width, height, language)


@pytest.mark.parametrize("surface", ["shell", "terminal", "music", "video", "browser",
                                         "reader", "emulator"])
@pytest.mark.parametrize("action", ["accept", "back"])
def test_button_actions_respect_composition_and_work_after_commit(tmp_path, surface, action):
    run_probe(tmp_path, surface, "composition-action", action)


def test_held_terminal_new_tab_shortcut_creates_only_one_session(tmp_path):
    run_probe(tmp_path, "terminal", "shortcut-repeat")


@pytest.mark.parametrize("action", ["up", "down"])
def test_terminal_button_directions_do_not_search_during_composition(tmp_path, action):
    run_probe(tmp_path, "terminal", "composition-action", action)


def test_background_controller_does_not_inherit_another_inputs_composition(tmp_path):
    run_probe(tmp_path, "reader", "composition-owner")


def test_terminal_held_history_confirmation_does_not_copy_until_second_press(tmp_path):
    run_probe(tmp_path, "terminal", "history-repeat")


def test_terminal_held_settings_confirmation_changes_font_once(tmp_path):
    run_probe(tmp_path, "terminal", "settings-repeat")


@pytest.mark.parametrize("language", ["en", "zh_CN"])
@pytest.mark.parametrize("theme", ["classic", "dark"])
def test_browser_pointer_stays_visible_after_moving_and_resizing(tmp_path, language, theme):
    run_probe(tmp_path, "browser", "pointer-resize", language, theme)


@pytest.mark.parametrize("surface", ["shell", "terminal", "music", "video", "browser",
                                         "reader", "emulator"])
def test_repeated_input_theme_language_and_composition_cycles_preserve_editing(tmp_path, surface):
    run_probe(tmp_path, surface, "input-cycles")


def test_video_controls_stay_visible_while_a_slider_drag_is_held(tmp_path):
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg is required for the original video fixture")
    run_probe(tmp_path, "video", "pointer-hold")
