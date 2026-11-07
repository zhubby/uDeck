"""Coverage for the stock uConsole keyboard's reportable keys and Fn outputs."""

from copy import deepcopy

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QObject, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtTest import QTest

from udeck.controller import ShellController
from udeck.core import ConfigStore
from udeck.key_test import KeyTestFilter
from udeck.key_test_layout import KEY_SPECS, LINUX_KEYS
from udeck.mock import MockBackend


@pytest.fixture
def diagnostic(tmp_path):
    application = QCoreApplication.instance() or QCoreApplication([])
    controller = ShellController(MockBackend(), config=ConfigStore(tmp_path / "config.json"), mock=True)
    controller._test_application = application
    window = QObject()
    event_filter = KeyTestFilter(controller, window)
    controller.activateSetting("key-test")
    yield application, controller, window, event_filter
    controller.close()


@pytest.mark.parametrize("character", "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789")
def test_every_letter_and_digit_has_independent_press_release_feedback(diagnostic, character):
    application, controller, window, _ = diagnostic
    before = deepcopy(controller.config.data)
    for kind in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
        application.sendEvent(window, QKeyEvent(kind, ord(character), Qt.NoModifier, character))
        assert (character.lower() in controller.modal["pressed"]) == (kind == QEvent.Type.KeyPress)
    assert character.lower() in controller.modal["tested"]
    assert not {"accept", "back", "context", "quick-settings"} & set(controller.modal["tested"])
    assert controller.config.data == before and not controller.backend.actions


@pytest.mark.parametrize(("key", "identifier"), [
    (Qt.Key_Backspace, "backspace"), (Qt.Key_Tab, "tab"), (Qt.Key_Return, "enter"),
    (Qt.Key_Space, "space"), (Qt.Key_QuoteLeft, "grave"), (Qt.Key_Minus, "minus"),
    (Qt.Key_Equal, "equals"), (Qt.Key_BracketLeft, "bracket-open"),
    (Qt.Key_BracketRight, "bracket-close"), (Qt.Key_Backslash, "backslash"),
    (Qt.Key_Semicolon, "semicolon"), (Qt.Key_Apostrophe, "apostrophe"),
    (Qt.Key_Comma, "comma"), (Qt.Key_Period, "period"), (Qt.Key_Slash, "slash"),
    (Qt.Key_CapsLock, "caps-lock"), (Qt.Key_Insert, "insert"), (Qt.Key_Delete, "delete"),
    (Qt.Key_Home, "home"), (Qt.Key_End, "end"), (Qt.Key_PageUp, "page-up"),
    (Qt.Key_PageDown, "page-down"), (Qt.Key_Print, "print"), (Qt.Key_Pause, "pause"),
    (Qt.Key_VolumeDown, "volume-down"), (Qt.Key_VolumeUp, "volume-up"),
    (Qt.Key_VolumeMute, "mute"), (Qt.Key_MonBrightnessDown, "brightness-down"),
    (Qt.Key_MonBrightnessUp, "brightness-up"),
] + [(getattr(Qt, f"Key_F{number}"), f"f{number}") for number in range(1, 13)])
def test_editing_punctuation_fn_and_media_keys_do_not_execute_shell_actions(diagnostic, key, identifier):
    application, controller, window, _ = diagnostic
    owner = controller.modal["key"]
    application.sendEvent(window, QKeyEvent(QEvent.Type.KeyPress, key, Qt.NoModifier))
    assert identifier in controller.modal["pressed"]
    application.sendEvent(window, QKeyEvent(QEvent.Type.KeyRelease, key, Qt.NoModifier))
    assert not controller.modal["pressed"] and identifier in controller.modal["tested"]
    assert controller.modal["key"] == owner and controller.backend.actions == []


def test_shifted_symbols_keep_the_base_key_identity_until_release(diagnostic):
    application, controller, window, _ = diagnostic
    application.sendEvent(window, QKeyEvent(QEvent.Type.KeyPress, Qt.Key_Exclam, Qt.ShiftModifier, "!"))
    assert controller.modal["pressed"] == ["1"]
    application.sendEvent(window, QKeyEvent(QEvent.Type.KeyRelease, Qt.Key_1, Qt.NoModifier, "1"))
    assert not controller.modal["pressed"] and controller.modal["tested"] == ["1"]


@pytest.mark.parametrize(("key", "keysym", "identifier"), [
    (Qt.Key_Shift, 0xffe2, "shift-right"), (Qt.Key_Control, 0xffe4, "ctrl-right"),
    (Qt.Key_Alt, 0xffea, "alt-right"),
])
def test_qt_native_modifier_identity_keeps_right_and_left_keys_separate(diagnostic, key, keysym, identifier):
    application, controller, window, _ = diagnostic
    application.sendEvent(window, QKeyEvent(QEvent.Type.KeyPress, key, Qt.NoModifier, 0, keysym, 0))
    assert controller.modal["pressed"] == [identifier]
    application.sendEvent(window, QKeyEvent(QEvent.Type.KeyRelease, key, Qt.NoModifier, 0, keysym, 0))
    assert not controller.modal["pressed"]


def test_native_and_qt_edges_are_counted_once_and_track_both_sides_of_modifiers(diagnostic):
    application, controller, window, _ = diagnostic
    controller.testHardwareKey("ctrl-left", True, "event4")
    application.sendEvent(window, QKeyEvent(QEvent.Type.KeyPress, Qt.Key_Control, Qt.ControlModifier))
    controller.testHardwareKey("ctrl-right", True, "event4")
    assert set(controller.modal["pressed"]) == {"ctrl-left", "ctrl-right"}
    assert controller.modal["pressCount"] == 2
    controller.testHardwareKey("ctrl-left", False, "event4")
    application.sendEvent(window, QKeyEvent(QEvent.Type.KeyRelease, Qt.Key_Control, Qt.NoModifier))
    assert controller.modal["pressed"] == ["ctrl-right"]
    controller.resetHardwareKeys("event4")
    assert not controller.modal["pressed"]


@pytest.mark.parametrize("native_first", [True, False])
def test_native_release_clears_qt_shadow_when_compositor_consumes_the_qt_keyup(diagnostic, native_first):
    application, controller, window, _ = diagnostic
    def native_press():
        controller.testHardwareKey("ctrl-left", True, "event4")

    def qt_press():
        application.sendEvent(window, QKeyEvent(QEvent.Type.KeyPress, Qt.Key_Control, Qt.ControlModifier))

    for press in ((native_press, qt_press) if native_first else (qt_press, native_press)):
        press()
    assert controller.modal["pressed"] == ["ctrl-left"] and controller.modal["pressCount"] == 1
    controller.testHardwareKey("ctrl-left", False, "event4")
    assert not controller.modal["pressed"]


def test_start_select_middle_click_motion_and_wheel_have_separate_states(diagnostic):
    _, controller, _, _ = diagnostic
    for identifier in ("select", "start", "pointer-click"):
        controller.testButton(identifier, True, "gamepad" if identifier != "pointer-click" else "pointer")
    for axis, value in ((0, -4), (1, 8), (8, -1)):
        controller.testPointerMotion(axis, value)
    expected = {"select", "start", "pointer-click", "pointer-left", "pointer-down", "wheel-down"}
    assert set(controller.modal["pressed"]) == expected
    assert controller.modal["pressCount"] == 3  # Relative movement is not a button press.
    QTest.qWait(250)
    assert set(controller.modal["pressed"]) == {"select", "start", "pointer-click"}
    assert expected <= set(controller.modal["tested"])
    controller.windowActive(False)
    assert not controller.modal["pressed"]


def test_internal_firmware_controls_are_visible_but_not_counted_as_failed_keys(diagnostic):
    _, controller, _, _ = diagnostic
    assert {"fn", "keyboard-light", "keyboard-lock", "power"} <= KEY_SPECS.keys()
    assert not any(KEY_SPECS[key]["detectable"] for key in ("fn", "keyboard-light", "keyboard-lock", "power"))
    assert controller.modal["totalKeys"] == sum(key["detectable"] for key in KEY_SPECS.values())
    assert set(LINUX_KEYS.values()) <= KEY_SPECS.keys()


def test_global_navigation_is_suppressed_while_testing_and_parent_focus_is_kept(diagnostic):
    _, controller, _, _ = diagnostic
    owner = controller.modal["key"]
    for action in ("home", "switcher", "search", "quick-settings", "previous-page", "next-page"):
        controller.dispatch(action)
        assert controller.modal["key"] == owner
    controller.dispatch("back")
    assert not controller.modal
