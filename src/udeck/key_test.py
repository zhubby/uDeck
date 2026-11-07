"""Observe input edges in the diagnostic dialog without changing input mappings."""

from PySide6.QtCore import QEvent, QObject, Qt, QTimer, Slot
from PySide6.QtGui import QKeySequence

from .i18n import tr

TEST_ACTIONS = {
    "up": tr("Up"), "down": tr("Down"), "left": tr("Left"), "right": tr("Right"),
    "accept": "A", "back": "B", "context": "X", "quick-settings": "Y",
    "previous-page": "L", "next-page": "R",
}
KEY_ACTIONS = {
    Qt.Key.Key_Up: "up", Qt.Key.Key_Down: "down", Qt.Key.Key_Left: "left", Qt.Key.Key_Right: "right",
    Qt.Key.Key_Return: "accept", Qt.Key.Key_Enter: "accept", Qt.Key.Key_Escape: "back",
    Qt.Key.Key_F10: "context", Qt.Key.Key_F1: "quick-settings",
    Qt.Key.Key_PageUp: "previous-page", Qt.Key.Key_PageDown: "next-page",
}
SOURCES = {"keyboard": tr("Keyboard"), "gamepad": tr("Gamepad"), "shoulder": tr("Shoulder buttons")}


class KeyTestControls:
    def _init_key_test(self):
        self._test_inputs = {}
        self._test_active = True
        self._test_exit_timer = QTimer(self)
        self._test_exit_timer.setSingleShot(True)
        self._test_exit_timer.setInterval(1200)
        self._test_exit_timer.timeout.connect(self._exit_key_test)

    def _open_key_test(self):
        self._clear_test_inputs()
        self._push({"kind": "key-test", "source": "key-test", "title": tr("Key test"),
                    "pressed": [], "tested": [], "activeLabels": [], "pressCount": 0,
                    "lastKey": tr("Press any key"), "lastSource": "", "exitHolding": False})

    @Slot(str, bool, str)
    def testButton(self, action, pressed, source):
        if action in TEST_ACTIONS:
            self._test_event(action, action, TEST_ACTIONS[action], pressed, source)

    def _test_event(self, token, action, label, pressed, source):
        if self.modal.get("kind") != "key-test" or not self._test_active:
            return
        identifier = (source, token)
        if pressed:
            if identifier in self._test_inputs:
                return
            self._test_inputs[identifier] = (action, label)
            self.modal["pressCount"] += 1
            self.modal.update(lastKey=label, lastSource=SOURCES.get(source, source))
            if action and action not in self.modal["tested"]:
                self.modal["tested"].append(action)
        else:
            self._test_inputs.pop(identifier, None)
        self._sync_test_inputs()

    def _sync_test_inputs(self):
        if self.modal.get("kind") != "key-test":
            return
        self.modal["pressed"] = sorted({action for action, _ in self._test_inputs.values() if action})
        self.modal["activeLabels"] = [label for _, label in self._test_inputs.values()]
        holding = "back" in self.modal["pressed"]
        if holding and not self.modal["exitHolding"]:
            self._test_exit_timer.start()
        elif not holding:
            self._test_exit_timer.stop()
        self.modal["exitHolding"] = holding
        self._publish()

    def _clear_test_inputs(self, source=None):
        self._test_inputs = {key: value for key, value in self._test_inputs.items() if source and key[0] != source}
        self._sync_test_inputs()
        if not self._test_inputs:
            self._test_exit_timer.stop()

    def _exit_key_test(self):
        if self.modal.get("kind") == "key-test" and "back" in self.modal["pressed"]:
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
            # Use the key code as fallback for synthetic events without native data.
            token = str(event.nativeScanCode() or key)
            label = QKeySequence(key).toString(QKeySequence.SequenceFormat.PortableText) or event.text() or str(key)
            self.controller._test_event(token, KEY_ACTIONS.get(key, ""), label,
                                        event.type() == QEvent.Type.KeyPress, "keyboard")
        event.accept()
        return True
