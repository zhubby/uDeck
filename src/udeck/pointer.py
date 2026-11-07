from PySide6.QtCore import QObject, QSocketNotifier, QTimer, Signal

from .i18n import error_text, tr
from .input import STOCK_FINGERPRINT


class PointerGuard(QObject):
    action = Signal(str)
    shoulder = Signal(str)
    button = Signal(str, bool)
    status = Signal(object)

    def __init__(self, parent=None, *, built_in_only=False):
        super().__init__(parent)
        self.devices = {}
        self.foreground = False
        self.last_status = None
        self.built_in_only = built_in_only
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self._scan)

    def start(self):
        self.timer.start()
        self._scan()

    def set_foreground(self, foreground):
        self.foreground = foreground

    def _scan(self):
        from evdev import InputDevice, list_devices

        errors = []
        try:
            paths = set(list_devices())
        except OSError as error:
            self._report([error_text(error)])
            return
        for path in set(self.devices) - paths:
            self._remove(path)
        for path in paths - self.devices.keys():
            device = None
            try:
                device = InputDevice(path)
                fingerprint = f"{device.info.vendor:04x}:{device.info.product:04x}:{device.uniq}"
                built_in = fingerprint == STOCK_FINGERPRINT and device.name == "ClockworkPI uConsole Mouse"
                if self.built_in_only and not built_in:
                    continue
                capabilities = device.capabilities()
                keys = set(capabilities.get(1, []))
                relative = set(capabilities.get(2, []))
                absolute = {entry[0] if isinstance(entry, tuple) else entry for entry in capabilities.get(3, [])}
                if 272 not in keys or not ({0, 1} <= relative or {0, 1} <= absolute):
                    continue
                if any(0 < code < 256 for code in keys):
                    errors.append(tr('{value0}: 混合键盘接口不能独占', value0=device.name))
                    continue
                if device.active_keys():
                    errors.append(tr('{value0}: 请松开鼠标按键', value0=device.name))
                    continue
                device.grab()
                notifier = QSocketNotifier(device.fd, QSocketNotifier.Type.Read, self)
                notifier.activated.connect(lambda *arguments, path=path: self._read(path))
                self.devices[path] = {"device": device, "notifier": notifier, "pressed": set(),
                                      "shoulders": built_in,
                                      "syncing": False}
                device = None
            except OSError as error:
                errors.append(f"{path}: {error}")
            finally:
                if device is not None:
                    device.close()
        self._report(errors)

    def _report(self, errors):
        status = {"scope": "session", "active": self.timer.isActive(),
                  "blockedDevices": len(self.devices), "errors": errors,
                  "devices": sorted(entry["device"].name for entry in self.devices.values())}
        if status != self.last_status:
            self.last_status = status
            self.status.emit({"pointer": status})

    def _read(self, path):
        entry = self.devices.get(path)
        if entry is None:
            return
        try:
            for event in entry["device"].read():
                if event.type == 0 and event.code == 3:
                    self._release_buttons(entry)
                    entry["syncing"] = True
                    continue
                if entry["syncing"]:
                    if event.type == 0 and event.code == 0:
                        entry["pressed"] = set(entry["device"].active_keys())
                        entry["syncing"] = False
                    continue
                if event.type != 1:
                    continue
                if event.value == 0:
                    if event.code in entry["pressed"] and entry["shoulders"] and event.code in (272, 273):
                        self.button.emit("previous-page" if event.code == 272 else "next-page", False)
                    entry["pressed"].discard(event.code)
                elif event.value == 1 and event.code not in entry["pressed"]:
                    entry["pressed"].add(event.code)
                    if entry["shoulders"] and event.code in (272, 273):
                        action = "previous-page" if event.code == 272 else "next-page"
                        self.button.emit(action, True)
                        self.shoulder.emit(action)
                        if self.foreground:
                            self.action.emit(action)
        except BlockingIOError:
            pass
        except OSError as error:
            self._remove(path)
            self._report([error_text(error)])

    def _remove(self, path):
        entry = self.devices.pop(path)
        self._release_buttons(entry)
        entry["notifier"].setEnabled(False)
        entry["notifier"].deleteLater()
        try:
            entry["device"].ungrab()
        except OSError:
            pass
        entry["device"].close()

    def _release_buttons(self, entry):
        if entry["shoulders"]:
            for code in sorted(entry["pressed"] & {272, 273}):
                self.button.emit("previous-page" if code == 272 else "next-page", False)
        entry["pressed"].clear()

    def close(self):
        self.timer.stop()
        for path in list(self.devices):
            self._remove(path)
        self._report([])
