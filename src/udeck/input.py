import sys

from PySide6.QtCore import QObject, QSocketNotifier, QTimer, Signal

from .i18n import error_text, tr

DIRECTIONS = {"left", "right", "up", "down"}
BUTTON_ACTIONS = {"accept", "back", "context", "quick-settings"}
ACTIONS = DIRECTIONS | BUTTON_ACTIONS
STOCK_FINGERPRINT = "1eaf:0024:20230713"
STOCK_BUTTONS = {289: "accept", 290: "back", 288: "context", 291: "quick-settings"}


class ButtonState:
    def __init__(self, mapping):
        self.mapping = {}
        for code, action in (mapping.items() if isinstance(mapping, dict) else []):
            try:
                number = int(code)
                if 0x100 <= number <= 0x2FF and isinstance(action, str) and action in ACTIONS:
                    self.mapping[number] = action
            except (ValueError, TypeError):
                continue
        self.pressed = set()

    def key(self, code, value):
        if value == 0:
            self.pressed.discard(code)
            return None
        if value != 1 or code in self.pressed:
            return None
        self.pressed.add(code)
        return self.mapping.get(code)

    def reset(self):
        self.pressed.clear()


class Gamepad(QObject):
    action = Signal(str)
    button = Signal(str, bool)
    auxiliaryButton = Signal(str, bool)
    direction = Signal(str, bool)
    captured = Signal(int)
    axisCaptured = Signal(str)
    status = Signal(object)

    def __init__(self, profile=None, parent=None):
        super().__init__(parent)
        self.profile = profile or {}
        self.device = None
        self.notifier = None
        self.foreground = False
        self.grabbed = False
        self.calibrating = False
        self._load_profile(self.profile)
        self.axis_actions = {}
        self.axis_positions = {}
        self.pressed_directions = set()
        self.held_direction = None
        self.repeat = QTimer(self)
        self.repeat.timeout.connect(self._repeat_direction)
        self.reconnect = QTimer(self)
        self.reconnect.setInterval(2000)
        self.reconnect.timeout.connect(self._connect)

    def _load_profile(self, profile):
        self.router = ButtonState(profile.get("buttons", {}))
        axes = profile.get("axes", {})
        self.axes = {key: value for key, value in (axes.items() if isinstance(axes, dict) else [])
                     if key in {f"{code}:{sign}" for code in (0, 1, 16, 17) for sign in (-1, 1)}
                     and isinstance(value, str) and value in DIRECTIONS}
        keyboard = profile.get("keyboardDirections", [])
        self.keyboard_directions = {value for value in (keyboard if isinstance(keyboard, list) else [])
                                    if isinstance(value, str) and value in DIRECTIONS}

    def _mapping_status(self, source):
        actions = set(self.router.mapping.values()) | set(self.axes.values())
        return {"mapped": BUTTON_ACTIONS <= actions, "mappingSource": source,
                "verified": source == "calibrated" and ACTIONS <= actions | self.keyboard_directions}

    def set_foreground(self, foreground):
        self.foreground = foreground
        self.status.emit({"foreground": foreground})
        if foreground:
            self._connect()
            self.reconnect.start()
        else:
            self.reconnect.stop()
            self._close()
            self.status.emit({"foreground": False, "grabbed": False})

    def _connect(self):
        if self.device is not None or not self.foreground or sys.platform != "linux":
            return
        try:
            from evdev import InputDevice, ecodes, list_devices

            for path in list_devices():
                candidate = InputDevice(path)
                capabilities = candidate.capabilities()
                buttons = capabilities.get(ecodes.EV_KEY, [])
                if (candidate.info.vendor, candidate.info.product) != (0x1EAF, 0x0024) or not any(code >= ecodes.BTN_MISC for code in buttons) or "Keyboard" in candidate.name or "Consumer" in candidate.name or "Mouse" in candidate.name:
                    candidate.close()
                    continue
                self.device = candidate
                self.fingerprint = f"{candidate.info.vendor:04x}:{candidate.info.product:04x}:{candidate.uniq}"
                effective = self.profile
                source = "calibrated"
                if self.profile.get("fingerprint") not in (None, self.fingerprint):
                    effective = {}
                    source = "unconfigured"
                elif not self.profile:
                    effective = {"buttons": STOCK_BUTTONS} if self.fingerprint == STOCK_FINGERPRINT and STOCK_BUTTONS.keys() <= set(buttons) else {}
                    source = "stock" if effective else "unconfigured"
                self._load_profile(effective)
                self.notifier = QSocketNotifier(candidate.fd, QSocketNotifier.Type.Read, self)
                self.notifier.activated.connect(self._read)
                self.status.emit({"available": True, "name": candidate.name,
                                  "fingerprint": self.fingerprint,
                                  **self._mapping_status(source), "grabbed": False})
                self._try_grab()
                return
            self.status.emit({"available": False, "verified": False, "message": tr('未找到独立手柄；可用方向键、Enter、Esc 操作')})
        except (ImportError, OSError) as error:
            self.status.emit({"available": False, "verified": False, "message": error_text(error)})

    def _try_grab(self):
        if self.device is None or self.grabbed or not self.foreground:
            return
        try:
            if self.device.active_keys():
                QTimer.singleShot(60, self._try_grab)
                return
            self.device.grab()
            self.grabbed = True
            self.status.emit({"grabbed": True})
        except OSError:
            self._close()
            self.status.emit({"grabbed": False, "message": tr('未能获取手柄输入；请确认设备已连接，且未被其他程序占用')})

    def _read(self, *arguments):
        try:
            from evdev import ecodes

            for event in self.device.read():
                if not self.grabbed:
                    continue
                if event.type == ecodes.EV_SYN and event.code == ecodes.SYN_DROPPED:
                    self._close()
                    self.status.emit({"grabbed": False, "message": tr('输入事件丢失，请松开按键后重试')})
                    return
                if event.type == ecodes.EV_KEY:
                    was_pressed = event.code in self.router.pressed
                    action = self.router.key(event.code, event.value)
                    if (self.fingerprint == STOCK_FINGERPRINT and event.code in (296, 297)
                            and ((event.value == 1 and not was_pressed) or (event.value == 0 and was_pressed))):
                        self.auxiliaryButton.emit("select" if event.code == 296 else "start", event.value == 1)
                    mapped = self.router.mapping.get(event.code)
                    if mapped and not self.calibrating and ((event.value == 1 and not was_pressed) or (event.value == 0 and was_pressed)):
                        self.button.emit(mapped, event.value == 1)
                    if self.calibrating and event.value == 1 and event.code >= ecodes.BTN_MISC:
                        self.captured.emit(event.code)
                    elif action and action not in DIRECTIONS:
                        self.action.emit(action)
                    self._update_direction()
                elif event.type == ecodes.EV_ABS and event.code in (ecodes.ABS_X, ecodes.ABS_Y, ecodes.ABS_HAT0X, ecodes.ABS_HAT0Y):
                    information = self.device.absinfo(event.code)
                    midpoint = (information.min + information.max) / 2
                    deadzone = max((information.max - information.min) / 4, 0.1)
                    position = 0
                    if event.value < midpoint - deadzone:
                        position = -1
                    elif event.value > midpoint + deadzone:
                        position = 1
                    identifier = f"{event.code}:{position}"
                    if self.calibrating and position and self.axis_positions.get(event.code) != position:
                        self.axisCaptured.emit(identifier)
                    self.axis_positions[event.code] = position
                    self.axis_actions[event.code] = self.axes.get(identifier) if position else None
                    self._update_direction()
        except BlockingIOError:
            pass
        except (OSError, AttributeError):
            self._close()
            self.status.emit({"available": False, "grabbed": False, "message": tr('手柄已断开')})

    def _update_direction(self):
        key_directions = [self.router.mapping.get(code) for code in sorted(self.router.pressed)]
        all_directions = key_directions + list(self.axis_actions.values())
        current = {value for value in all_directions if value in DIRECTIONS}
        for value in sorted(self.pressed_directions - current):
            self.direction.emit(value, False)
        for value in sorted(current - self.pressed_directions):
            self.direction.emit(value, True)
        self.pressed_directions = current
        direction = next((value for value in all_directions if value in DIRECTIONS), None)
        if direction != self.held_direction:
            self.held_direction = direction
            self.repeat.stop()
            if direction and not self.calibrating:
                self.action.emit(direction)
                self.repeat.start(350)

    def _repeat_direction(self):
        if self.foreground and self.held_direction and not self.calibrating:
            self.action.emit(self.held_direction)
            self.repeat.setInterval(90)

    def set_profile(self, mapping, axes=None, keyboard_directions=None):
        self.profile = {"buttons": mapping, "axes": axes or {},
                        "keyboardDirections": keyboard_directions or [],
                        "fingerprint": getattr(self, "fingerprint", "")}
        self._load_profile(self.profile)
        self.status.emit(self._mapping_status("calibrated"))
        return self.profile

    def _close(self):
        self.repeat.stop()
        for code in sorted(self.router.pressed):
            if getattr(self, "fingerprint", "") == STOCK_FINGERPRINT and code in (296, 297):
                self.auxiliaryButton.emit("select" if code == 296 else "start", False)
            if self.router.mapping.get(code):
                self.button.emit(self.router.mapping[code], False)
        for action in sorted(self.pressed_directions):
            self.direction.emit(action, False)
        self.pressed_directions.clear()
        self.router.reset()
        self.axis_actions.clear()
        self.axis_positions.clear()
        self.held_direction = None
        self.status.emit({'grabbed': False})
        if self.notifier:
            self.notifier.setEnabled(False)
            self.notifier.deleteLater()
            self.notifier = None
        if self.device:
            if self.grabbed:
                try:
                    self.device.ungrab()
                except OSError:
                    pass
            self.device.close()
            self.device = None
        self.grabbed = False

    def close(self):
        self.reconnect.stop()
        self.foreground = False
        self._close()
