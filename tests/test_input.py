import os
import sys
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QCoreApplication

from udeck import input as input_module
from udeck.input import ButtonState, Gamepad


@pytest.fixture
def stock_gamepad(monkeypatch, request):
    application = QCoreApplication.instance() or QCoreApplication([])
    reader, writer = os.pipe()
    events = []
    device = SimpleNamespace(
        name="ClockworkPI uConsole", path="/dev/input/event7", fd=reader, uniq="20230713",
        info=SimpleNamespace(vendor=0x1EAF, product=0x0024),
        capabilities=lambda: {1: list(range(288, 304)), 3: [0, 1, 16, 17]},
        active_keys=lambda: [], grab=lambda: None, ungrab=lambda: None,
        close=lambda: None, read=lambda: list(events),
    )
    monkeypatch.setitem(sys.modules, "evdev", SimpleNamespace(
        InputDevice=lambda path: device, list_devices=lambda: [device.path],
        ecodes=SimpleNamespace(EV_KEY=1, EV_SYN=0, SYN_DROPPED=3, EV_ABS=3, BTN_MISC=256),
    ))
    monkeypatch.setattr(input_module, "sys", SimpleNamespace(platform="linux"))
    gamepad = Gamepad(getattr(request, "param", None))
    gamepad._test_application = application
    yield gamepad, device, events
    gamepad.close()
    os.close(reader)
    os.close(writer)


def test_stock_abxy_works_on_first_launch_without_a_saved_profile(stock_gamepad):
    gamepad, device, events = stock_gamepad
    actions = []
    gamepad.action.connect(actions.append)
    gamepad.set_foreground(True)
    for code in (289, 290, 288, 291):
        events[:] = [SimpleNamespace(type=1, code=code, value=1),
                     SimpleNamespace(type=1, code=code, value=0)]
        gamepad._read()
    assert actions == ["accept", "back", "context", "quick-settings"]


def test_unknown_firmware_does_not_receive_a_guessed_button_mapping(stock_gamepad):
    gamepad, device, events = stock_gamepad
    device.uniq = "unknown-firmware"
    actions = []
    gamepad.action.connect(actions.append)
    gamepad.set_foreground(True)
    events[:] = [SimpleNamespace(type=1, code=289, value=1)]
    gamepad._read()
    assert actions == []


@pytest.mark.parametrize("stock_gamepad", [{
    "fingerprint": "1eaf:0024:another-device", "buttons": {"289": "accept"},
}], indirect=True)
def test_profile_from_a_different_device_is_not_applied(stock_gamepad):
    gamepad, device, events = stock_gamepad
    actions = []
    gamepad.action.connect(actions.append)
    gamepad.set_foreground(True)
    events[:] = [SimpleNamespace(type=1, code=289, value=1)]
    gamepad._read()
    assert actions == []


@pytest.mark.parametrize("stock_gamepad", [{
    "fingerprint": "1eaf:0024:20230713", "buttons": {"289": "back"},
}], indirect=True)
def test_saved_custom_mapping_overrides_stock_defaults(stock_gamepad):
    gamepad, device, events = stock_gamepad
    actions = []
    gamepad.action.connect(actions.append)
    gamepad.set_foreground(True)
    events[:] = [SimpleNamespace(type=1, code=289, value=1)]
    gamepad._read()
    assert actions == ["back"]


def test_foreground_status_and_button_ownership_are_released_together(stock_gamepad):
    gamepad, device, events = stock_gamepad
    status = {}
    gamepad.status.connect(status.update)
    gamepad.set_foreground(True)
    assert status["foreground"] is True
    assert status["grabbed"] is True
    gamepad.set_foreground(False)
    assert status["foreground"] is False
    assert status["grabbed"] is False
    assert gamepad.device is None


@pytest.mark.parametrize("name", ["ClockworkPI uConsole Mouse", "ClockworkPI uConsole Keyboard"])
def test_keyboard_and_mouse_interfaces_are_never_grabbed(stock_gamepad, name):
    gamepad, device, events = stock_gamepad
    device.name = name
    gamepad.set_foreground(True)
    assert gamepad.device is None
    assert gamepad.grabbed is False


def test_keyboard_directions_complete_a_saved_mixed_input_profile(stock_gamepad):
    gamepad, device, events = stock_gamepad
    status = {}
    gamepad.status.connect(status.update)
    gamepad.set_foreground(True)
    assert status.get("mapped") is True
    assert status["verified"] is False
    profile = gamepad.set_profile(
        {"289": "accept", "290": "back", "288": "context", "291": "quick-settings"},
        keyboard_directions=["up", "down", "left", "right"],
    )
    assert status["verified"] is True
    assert profile["keyboardDirections"] == ["up", "down", "left", "right"]


def test_buttons_only_fire_once_and_release_on_focus_loss():
    router = ButtonState({289: "accept", 290: "back"})
    assert router.key(289, 1) == "accept"
    assert router.key(289, 2) is None
    assert router.key(289, 1) is None
    assert router.key(289, 0) is None
    assert router.key(289, 1) == "accept"
    router.reset()
    assert router.pressed == set()


def test_gamepad_reports_real_press_and_release_for_application_drag(stock_gamepad):
    gamepad, device, events = stock_gamepad
    edges = []
    gamepad.button.connect(lambda action, pressed: edges.append((action, pressed)))
    gamepad.set_foreground(True)
    for value in (1, 2, 1, 0):
        events[:] = [SimpleNamespace(type=1, code=289, value=value)]
        gamepad._read()
    assert edges == [('accept', True), ('accept', False)]


def test_direction_edges_include_diagonals_and_release_on_disconnect(stock_gamepad):
    gamepad, _, _ = stock_gamepad
    edges = []
    gamepad.direction.connect(lambda action, pressed: edges.append((action, pressed)))
    gamepad.axis_actions = {0: "left", 1: "up"}
    gamepad._update_direction()
    gamepad._update_direction()
    assert edges == [("left", True), ("up", True)]
    gamepad.axis_actions[0] = "right"
    gamepad._update_direction()
    assert edges[-2:] == [("left", False), ("right", True)]
    gamepad._close()
    assert edges[-2:] == [("right", False), ("up", False)]
    assert not gamepad.pressed_directions


def test_unknown_buttons_do_not_become_keyboard_shortcuts():
    router = ButtonState({289: "accept"})
    assert router.key(30, 1) is None
    assert router.key(288, 1) is None


def test_malformed_mapping_does_not_crash_or_map_keyboard_letters():
    router = ButtonState({"invalid": "accept", "30": "accept", "289": "unknown"})
    assert router.mapping == {}


def test_held_gamepad_disconnection_during_grab_is_not_fatal():
    from types import SimpleNamespace

    from PySide6.QtCore import QCoreApplication

    from udeck.input import Gamepad

    application = QCoreApplication.instance() or QCoreApplication([])

    def disconnected():
        raise OSError("device removed")

    gamepad = Gamepad()
    gamepad.foreground = True
    gamepad.device = SimpleNamespace(active_keys=disconnected, close=lambda: None)
    gamepad._try_grab()
    assert not gamepad.grabbed
    assert gamepad.device is None
    assert application is not None
