from udeck.input import ButtonState


def test_buttons_only_fire_once_and_release_on_focus_loss():
    router = ButtonState({289: "accept", 290: "back"})
    assert router.key(289, 1) == "accept"
    assert router.key(289, 2) is None
    assert router.key(289, 1) is None
    assert router.key(289, 0) is None
    assert router.key(289, 1) == "accept"
    router.reset()
    assert router.pressed == set()


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
