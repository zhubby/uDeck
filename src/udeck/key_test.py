"""Observe input edges in the diagnostic dialog without changing input mappings."""

import sys

from PySide6.QtCore import QEvent, QObject, QTimer, Slot
from PySide6.QtGui import QKeySequence

from .i18n import tr
from .key_test_layout import (
    GAMEPAD_KEYS,
    INTERNAL_KEYS,
    KEY_SPECS,
    KEYBOARD_ROWS,
    LINUX_KEYS,
    POINTER_KEYS,
    QT_KEYS,
)

TEST_ACTIONS = {
    "up": tr("Up"), "down": tr("Down"), "left": tr("Left"), "right": tr("Right"),
    "accept": "A", "back": "B", "context": "X", "quick-settings": "Y",
    "previous-page": "L", "next-page": "R",
    **{key["id"]: key["label"] for key in GAMEPAD_KEYS + POINTER_KEYS},
}
SOURCES = {"keyboard": tr("Keyboard"), "gamepad": tr("Gamepad"), "shoulder": tr("Shoulder buttons"),
           "pointer": tr("Trackball"), "native": tr("uConsole keyboard")}


class KeyTestControls:
    def _init_key_test(self):
        self._test_inputs = {}
        self._test_native_keys = set()
        self._test_active = True
        self._test_motion_timers = {}
        self._test_exit_timer = QTimer(self)
        self._test_exit_timer.setSingleShot(True)
        self._test_exit_timer.setInterval(1200)
        self._test_exit_timer.timeout.connect(self._exit_key_test)

    def _open_key_test(self):
        self._clear_test_inputs()
        self._push({"kind": "key-test", "source": "key-test", "title": tr("Key test"),
                    "pressed": [], "tested": [], "activeLabels": [], "pressCount": 0,
                    "lastKey": tr("Press any key"), "lastSource": "", "exitHolding": False,
                    "keyboardRows": KEYBOARD_ROWS, "gamepadKeys": GAMEPAD_KEYS, "pointerKeys": POINTER_KEYS,
                    "internalKeys": INTERNAL_KEYS, "totalKeys": sum(key["detectable"] for key in KEY_SPECS.values()),
                    "deviceWarning": ""})

    @Slot(str, bool, str)
    def testButton(self, action, pressed, source):
        if action in TEST_ACTIONS:
            self._test_event(action, action, TEST_ACTIONS[action], pressed, source)

    @Slot(str, bool, str)
    def testHardwareKey(self, identifier, pressed, source):
        if identifier in KEY_SPECS and KEY_SPECS[identifier]["detectable"]:
            self._test_event(identifier, identifier, KEY_SPECS[identifier]["label"], pressed, "native:" + source)

    @Slot(str)
    def resetHardwareKeys(self, source):
        self._clear_test_inputs("native:" + source)
        # Qt cannot attribute a lost key release to a particular USB interface.
        self._clear_test_inputs("keyboard")

    def _set_test_native_keys(self, keys):
        self._test_native_keys = set(keys)
        inputs = {key: value for key, value in self._test_inputs.items()
                  if key[0] != "keyboard" or value[0] not in self._test_native_keys}
        if inputs != self._test_inputs:
            self._test_inputs = inputs
            self._sync_test_inputs()

    @Slot(int, int)
    def testPointerMotion(self, axis, value):
        if not value or axis not in (0, 1, 8) or self.modal.get("kind") != "key-test" or not self._test_active:
            return
        identifiers = {0: ("pointer-left", "pointer-right"), 1: ("pointer-up", "pointer-down"),
                       8: ("wheel-down", "wheel-up")}
        identifier = identifiers[axis][value > 0]
        self._test_event(identifier, identifier, KEY_SPECS[identifier]["label"], True, "pointer", count=False)
        if identifier not in self._test_motion_timers:
            timer = self._test_motion_timers[identifier] = QTimer(self)
            timer.setSingleShot(True)
            timer.setInterval(180)
            timer.timeout.connect(lambda identifier=identifier: self._test_event(
                identifier, identifier, KEY_SPECS[identifier]["label"], False, "pointer"))
        self._test_motion_timers[identifier].start()

    def _test_event(self, token, action, label, pressed, source, *, count=True):
        if self.modal.get("kind") != "key-test" or not self._test_active:
            return
        # Native ownership lasts while its interface is readable, including
        # between taps. Qt may deliver an entire duplicate tap after key-up.
        if source == "keyboard" and action in self._test_native_keys:
            return
        identifier = (source, token)
        if pressed:
            if identifier in self._test_inputs:
                return
            if source == "keyboard" and any(key[0].startswith("native:") and value[0] == action
                                             for key, value in self._test_inputs.items()):
                return
            already_pressed = action and any(value[0] == action for value in self._test_inputs.values())
            if source.startswith("native:"):
                # The native edge is authoritative for the same keyboard report.
                # A compositor shortcut can consume Qt's release after Qt's press.
                self._test_inputs = {key: value for key, value in self._test_inputs.items()
                                     if not (key[0] == "keyboard" and value[0] == action)}
            self._test_inputs[identifier] = (action, label)
            if not already_pressed:
                if count:
                    self.modal["pressCount"] += 1
                self.modal.update(lastKey=label, lastSource=SOURCES.get(source.split(":")[0], source))
            if action and action not in self.modal["tested"]:
                self.modal["tested"].append(action)
        else:
            self._test_inputs.pop(identifier, None)
        self._sync_test_inputs()

    def _sync_test_inputs(self):
        if self.modal.get("kind") != "key-test":
            return
        self.modal["pressed"] = sorted({action for action, _ in self._test_inputs.values() if action})
        self.modal["activeLabels"] = list(dict.fromkeys(label for _, label in self._test_inputs.values()))
        holding = bool({"back", "escape"} & set(self.modal["pressed"]))
        if holding and not self.modal["exitHolding"]:
            self._test_exit_timer.start()
        elif not holding:
            self._test_exit_timer.stop()
        self.modal["exitHolding"] = holding
        self._publish()

    def _clear_test_inputs(self, source=None):
        if source in (None, "pointer"):
            for timer in self._test_motion_timers.values():
                timer.stop()
        self._test_inputs = {key: value for key, value in self._test_inputs.items() if source and key[0] != source}
        self._sync_test_inputs()
        if not self._test_inputs:
            self._test_exit_timer.stop()

    def _exit_key_test(self):
        if self.modal.get("kind") == "key-test" and self.modal["exitHolding"]:
            self._pop()


class KeyTestFilter(QObject):
    """Catch keyboard input before QML navigation, including keys with no action."""

    def __init__(self, controller, window):
        super().__init__(window)
        self.controller = controller
        window.installEventFilter(self)

    def eventFilter(self, watched, event):
        if self.controller.modal.get("kind") != "key-test":
            return False
        if event.type() == QEvent.Type.ShortcutOverride:
            event.accept()
            return True
        if event.type() not in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
            return False
        if not event.isAutoRepeat():
            key = event.key()
            identifier = QT_KEYS.get(key, "")
            if sys.platform == "linux" and event.nativeScanCode():
                identifier = LINUX_KEYS.get(event.nativeScanCode() - 8, identifier)
            # Modifier key codes are shared by both sides; XKB keysyms retain the side.
            identifier = {0xffe1: "shift-left", 0xffe2: "shift-right", 0xffe3: "ctrl-left",
                          0xffe4: "ctrl-right", 0xffe9: "alt-left", 0xffea: "alt-right"}.get(
                              event.nativeVirtualKey(), identifier)
            # Use the key code as fallback for synthetic events without native data.
            token = str(event.nativeScanCode() or identifier or key)
            label = KEY_SPECS[identifier]["label"] if identifier else (
                QKeySequence(key).toString(QKeySequence.SequenceFormat.PortableText) or event.text() or str(key))
            self.controller._test_event(token, identifier, label,
                                        event.type() == QEvent.Type.KeyPress, "keyboard")
        event.accept()
        return True
