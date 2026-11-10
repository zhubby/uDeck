"""Route stock trackball gestures without conflating recovery and release edges."""

import math
import time

from PySide6.QtCore import QObject, Qt, QTimer

from .windows import APP_ID


class TrackballInput(QObject):
    HOLD_SECONDS = 2.0

    def __init__(self, pointer, controller, windows=None, output=None, *, clock=time.monotonic):
        super().__init__(controller)
        self.pointer, self.controller = pointer, controller
        self.windows, self.output = windows, output
        self.clock = clock
        self.foreground = False
        self.session_safe = controller.mock
        self.suspended = False
        self.diagnostic = False
        self.held = False
        self.fired = False
        self.started = 0.0
        self.owner = None
        self.target = None
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.timeout.connect(self._timeout)
        pointer.middleButtonTimed.connect(self.button)
        pointer.reset.connect(self.cancel)
        pointer.motion.connect(self.motion)
        controller.foregroundChanged.connect(self.window_active)
        controller.inputSuspended.connect(self.set_suspended)
        controller.changed.connect(self._modal_changed)
        controller.backend.updated.connect(self.session_update)
        if windows:
            windows.changed.connect(self._windows_changed)
            windows.failed.connect(self._failed)
            self._windows_changed(windows.entries())
        if output:
            output.failed.connect(self._failed)
        self._modal_changed()

    def _target(self):
        if not self.session_safe or self.suspended or self.diagnostic:
            return None
        if self.foreground:
            return ('shell',)
        if self.windows and self.windows.available and self.output and self.output.available and self.target:
            return ('application', *self.target)
        return None

    def window_active(self, active):
        if self.foreground != active:
            self.cancel()
        self.foreground = active

    def _windows_changed(self, rows):
        active = next((entry for entry in rows if entry.get('active') and entry.get('appId') != APP_ID), None)
        target = (active['id'], active.get('appId', '')) if active else None
        if target != self.target:
            self.cancel()
        self.target = target

    def session_update(self, values):
        if 'sessionInput' in values:
            state = values['sessionInput']
            self.session_safe = bool(state.get('available') and state.get('active') and not state.get('locked'))
            if not self.session_safe:
                self.cancel()

    def set_suspended(self, suspended):
        self.suspended = suspended
        if suspended:
            self.cancel()

    def _modal_changed(self):
        diagnostic = self.controller.modal.get('kind') in ('key-test', 'calibration')
        if diagnostic != self.diagnostic:
            self.cancel()
        self.diagnostic = diagnostic

    def _failed(self, _message):
        self.cancel()

    def cancel(self):
        self.timer.stop()
        self.held = False
        self.owner = None

    def button(self, pressed, occurred):
        if pressed:
            if self.held or not (target := self._target()):
                return
            self.held, self.fired = True, False
            self.owner, self.started = target, min(self.clock(), occurred)
            self.timer.start(max(1, math.ceil((self.HOLD_SECONDS - (self.clock() - self.started)) * 1000) + 1))
        elif self.held:
            elapsed = max(0, occurred - self.started)
            owner, fired = self.owner, self.fired
            self.cancel()
            if not fired and owner == self._target():
                self._click(273 if elapsed > self.HOLD_SECONDS else 272)

    def _timeout(self):
        if not self.held or self.fired:
            return
        if self.owner != self._target():
            self.cancel()
            return
        remaining = self.HOLD_SECONDS - (self.clock() - self.started)
        if remaining >= 0:
            self.timer.start(max(1, math.ceil(remaining * 1000) + 1))
            return
        self.fired = True
        self._click(273)

    def _click(self, code):
        target = self._target()
        if not target:
            return
        if target[0] == 'shell':
            self.controller.dispatch('accept' if code == 272 else 'context')
        elif code not in self.output.buttons:
            # Never release a button held by the gamepad's drag gesture.
            try:
                self.output.button(code, True)
            finally:
                self.output.button(code, False)

    def motion(self, axis, value):
        target = self._target()
        if not value or not target or target[0] != 'application':
            return
        if axis in (0, 1):
            self.output.move(value if axis == 0 else 0, value if axis == 1 else 0)
        elif axis == 8:
            self.output.scroll(-value)

    def close(self):
        self.cancel()
        for signal, slot in (
            (self.pointer.middleButtonTimed, self.button), (self.pointer.reset, self.cancel),
            (self.pointer.motion, self.motion), (self.controller.foregroundChanged, self.window_active),
            (self.controller.inputSuspended, self.set_suspended), (self.controller.changed, self._modal_changed),
            (self.controller.backend.updated, self.session_update),
        ):
            signal.disconnect(slot)
        if self.windows:
            self.windows.changed.disconnect(self._windows_changed)
            self.windows.failed.disconnect(self._failed)
        if self.output:
            self.output.failed.disconnect(self._failed)
