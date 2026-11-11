"""Read stock keyboard reports only while the diagnostic is open and focused.

This observer never grabs devices or changes shortcuts. Consumer keys may be
handled by the compositor before Qt sees them, so read their actual evdev
reports as well. The existing gamepad/pointer owners retain their ownership.
"""

import sys

from PySide6.QtCore import QObject, QSocketNotifier, QTimer, Signal

from .i18n import Msg, tr
from .key_test_layout import LINUX_KEYS


class KeyTestReader(QObject):
    key = Signal(str, bool, str)
    reset = Signal(str)
    warning = Signal(object)
    status = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.enabled = False
        self._closed = False
        self.devices = {}
        self.last_status = None
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self._scan)

    def set_enabled(self, enabled):
        enabled = bool(enabled and sys.platform == "linux" and not self._closed)
        if enabled == self.enabled:
            return
        self.enabled = enabled
        if enabled:
            self.timer.start()
            self._scan()
        else:
            self._stop()

    def _scan(self):
        from evdev import InputDevice, list_devices

        if not self.enabled:
            return
        failed = False
        try:
            paths = set(list_devices())
        except OSError:
            self.warning.emit(tr(Msg.SOME_SYSTEM_KEYS_CANNOT_BE_READ_CHECK_INPUT_DEVICE_ACCESS))
            return
        for path in set(self.devices) - paths:
            self._remove(path)
        for path in paths - self.devices.keys():
            device = None
            try:
                device = InputDevice(path)
                if ((device.info.vendor, device.info.product) != (0x1EAF, 0x0024)
                        or not any(part in device.name for part in ("Keyboard", "Consumer"))):
                    continue
                keys = {LINUX_KEYS[code] for code in device.capabilities().get(1, []) if code in LINUX_KEYS}
                notifier = QSocketNotifier(device.fd, QSocketNotifier.Type.Read, self)
                notifier.activated.connect(lambda *arguments, path=path: self._read(path))
                self.devices[path] = {"device": device, "notifier": notifier, "keys": keys,
                                      "pressed": set(), "syncing": False}
                device = None
            except OSError:
                failed = True
            finally:
                if device is not None:
                    device.close()
        self._report()
        self.warning.emit(tr(Msg.SOME_SYSTEM_KEYS_CANNOT_BE_READ_CHECK_INPUT_DEVICE_ACCESS) if failed or not self.devices else "")

    def _report(self):
        status = {"keyTestNativeKeys": sorted({key for entry in self.devices.values() for key in entry["keys"]})}
        if status != self.last_status:
            self.last_status = status
            self.status.emit(status)

    def _read(self, path):
        entry = self.devices.get(path)
        if not entry or not self.enabled:
            return
        try:
            for event in entry["device"].read():
                if event.type == 0 and event.code == 3:  # SYN_DROPPED
                    entry["pressed"].clear()
                    entry["syncing"] = True
                    self.reset.emit(path)
                elif entry["syncing"]:
                    if event.type == 0 and event.code == 0:
                        entry["syncing"] = False
                elif event.type == 1 and event.code in LINUX_KEYS:
                    if event.value == 1 and event.code not in entry["pressed"]:
                        entry["pressed"].add(event.code)
                        self.key.emit(LINUX_KEYS[event.code], True, path)
                    elif event.value == 0 and event.code in entry["pressed"]:
                        entry["pressed"].discard(event.code)
                        self.key.emit(LINUX_KEYS[event.code], False, path)
        except BlockingIOError:
            pass
        except OSError:
            self._remove(path)

    def _remove(self, path):
        entry = self.devices.pop(path)
        entry["notifier"].setEnabled(False)
        entry["notifier"].deleteLater()
        entry["device"].close()
        self.reset.emit(path)
        self._report()

    def _stop(self):
        self.enabled = False
        self.timer.stop()
        for path in list(self.devices):
            self._remove(path)
        self._report()

    def close(self):
        # Reset signals can publish controller state while the app is closing.
        # They must not start a new observation session during final teardown.
        self._closed = True
        self._stop()
