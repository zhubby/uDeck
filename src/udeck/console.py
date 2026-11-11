"""Global shell panel and focus restoration for compositor shortcuts."""

from PySide6.QtCore import QObject

from .windows import APP_ID


class ConsolePanel(QObject):
    def __init__(self, controller, windows=None, router=None):
        super().__init__(controller)
        self.controller, self.windows, self.router = controller, windows, router
        self.return_target = None
        self.session_safe = controller.mock
        self.suspended = False
        controller.consoleAction.connect(self.action)
        controller.backend.updated.connect(self.session_update)
        controller.inputSuspended.connect(self.set_suspended)
        if windows:
            windows.changed.connect(self._windows_changed)

    def session_update(self, values):
        if 'sessionInput' in values:
            state = values['sessionInput']
            self.session_safe = bool(state.get('available') and state.get('active') and not state.get('locked'))
            if not self.session_safe:
                self.return_target = None

    def set_suspended(self, suspended):
        self.suspended = suspended
        if suspended:
            self.return_target = None

    def _windows_changed(self, rows):
        if self.return_target and not any((entry['id'], entry.get('appId', '')) == self.return_target for entry in rows):
            self.return_target = None

    def open(self):
        if not self.session_safe or self.suspended:
            return
        already_open = any(modal.get('source') == 'console' for modal in self.controller._modals)
        active = next((entry for entry in self.windows.entries()
                       if entry.get('active') and entry.get('appId') != APP_ID), None) if self.windows else None
        if not already_open or active:
            self.return_target = (active['id'], active.get('appId', '')) if active else None
            if self.router:
                self.router.leave_menu()
        self.controller.dispatch('console')

    def action(self, command):
        if command == 'dismiss':
            target, self.return_target = self.return_target, None
            if target and self.session_safe and not self.suspended and self.windows:
                entry = next((entry for entry in self.windows.entries()
                              if (entry['id'], entry.get('appId', '')) == target), None)
                if entry:
                    if self.router and self.router.enabled:
                        self.router.resume_window(entry['id'])
                    else:
                        try:
                            self.windows.request(entry['id'], 'activate')
                        except RuntimeError:
                            pass
            return
        if not self.session_safe or self.suspended:
            return
        if command in ('poweroff', 'reboot'):
            self.controller.activateSetting(command)
        elif command in ('home', 'switcher', 'settings'):
            self.return_target = None
            if self.router:
                self.router.leave_menu()
            self.controller._cancel_modals()
            if command == 'settings':
                self.controller.setPage('settings')
                self.controller.present.emit()
            else:
                self.controller.dispatch(command)

    def close(self):
        self.return_target = None
        self.controller.consoleAction.disconnect(self.action)
        self.controller.backend.updated.disconnect(self.session_update)
        self.controller.inputSuspended.disconnect(self.set_suspended)
        if self.windows:
            self.windows.changed.disconnect(self._windows_changed)
