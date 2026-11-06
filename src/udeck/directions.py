from PySide6.QtCore import QObject, QSocketNotifier, QTimer, Signal

from .input import STOCK_FINGERPRINT

ARROWS = {103: 'up', 108: 'down', 105: 'left', 106: 'right'}
MODIFIERS = {29, 97, 42, 54, 56, 100, 125, 126}


class DirectionReader(QObject):
    direction = Signal(str, bool)
    failed = Signal(str)
    status = Signal(dict)

    def __init__(self):
        super().__init__()
        self.device = None
        self.notifier = None
        self.held = set()
        self.blocked = set()
        self.syncing = False
        self.available = False
        self.last_status = None
        self.timer = QTimer(self)
        self.timer.setInterval(2000)
        self.timer.timeout.connect(self._connect)

    def start(self):
        self.timer.start()
        self._connect()

    def _connect(self):
        if self.device:
            return
        try:
            from evdev import InputDevice, list_devices

            for path in list_devices():
                candidate = InputDevice(path)
                fingerprint = f'{candidate.info.vendor:04x}:{candidate.info.product:04x}:{candidate.uniq}'
                if fingerprint != STOCK_FINGERPRINT or candidate.name != 'ClockworkPI uConsole Keyboard':
                    candidate.close()
                    continue
                self.device = candidate
                self.held = set(candidate.active_keys())
                self.blocked = self.held & ARROWS.keys()
                self.notifier = QSocketNotifier(candidate.fd, QSocketNotifier.Type.Read, self)
                self.notifier.activated.connect(self._read)
                self.available = True
                self._status()
                return
            self._status('未找到内置 Keyboard 方向键接口')
        except (ImportError, OSError) as error:
            self._disconnect()
            self._status(str(error))
            self.failed.emit(str(error))

    def _status(self, error=''):
        status = {'available': self.available, 'error': error}
        if self.last_status != status:
            self.last_status = status
            self.status.emit(status)

    def feed(self, code, value):
        if value == 2:
            return
        if value:
            self.held.add(code)
        else:
            self.held.discard(code)
            self.blocked.discard(code)
        if code in MODIFIERS and value:
            for arrow in self.held & ARROWS.keys():
                self.blocked.add(arrow)
                self.direction.emit(ARROWS[arrow], False)
        if code in ARROWS:
            if not value:
                self.direction.emit(ARROWS[code], False)
            elif not self.held & MODIFIERS and code not in self.blocked:
                self.direction.emit(ARROWS[code], True)
            else:
                self.blocked.add(code)

    def _read(self, *arguments):
        try:
            for event in self.device.read():
                if event.type == 0 and event.code == 3:
                    for action in ARROWS.values():
                        self.direction.emit(action, False)
                    self.syncing = True
                elif self.syncing:
                    if event.type == 0 and event.code == 0:
                        self.held = set(self.device.active_keys())
                        self.blocked = self.held & ARROWS.keys()
                        self.syncing = False
                elif event.type == 1:
                    self.feed(event.code, event.value)
        except BlockingIOError:
            pass
        except OSError as error:
            self._disconnect()
            self._status(str(error))
            self.failed.emit(str(error))

    def _disconnect(self):
        self.available = False
        for action in ARROWS.values():
            self.direction.emit(action, False)
        self.held.clear()
        self.blocked.clear()
        self.syncing = False
        if self.notifier:
            self.notifier.setEnabled(False)
            self.notifier.deleteLater()
            self.notifier = None
        if self.device:
            self.device.close()
            self.device = None
        self._status()

    def close(self):
        self.timer.stop()
        self._disconnect()
