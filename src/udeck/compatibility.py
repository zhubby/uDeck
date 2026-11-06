import math
import time

from PySide6.QtCore import QObject, QTimer

from .app_routing import NATIVE_APPS
from .i18n import error_text, tr

TERMINAL_APP = 'io.github.zhubby.uDeck.Terminal'
MODE_NAMES = {'keyboard': tr('按键模式'), 'pointer': tr('指针模式'), 'native': tr('原生输入')}


def application_profile(identifier):
    identifier = identifier.casefold()
    kind, mode, commands = 'generic', 'keyboard', []
    if identifier in {app.casefold() for app in NATIVE_APPS} or identifier in ('retroarch', 'com.libretro.retroarch', 'emulationstation', 'es-de'):
        kind, mode = 'native', 'native'
    elif identifier in ('firefox', 'firefox-esr', 'chromium', 'chromium-browser'):
        kind = 'browser'
        commands = [(tr('地址栏'), (29, 38)), (tr('上一页'), (56, 105)), (tr('下一页'), (56, 106)), (tr('刷新'), (63,)), (tr('新标签页'), (29, 20))]
    elif identifier in ('code', 'geany', 'mousepad', 'org.xfce.mousepad'):
        kind = 'editor'
        commands = [(tr('打开文件'), (29, 24)), (tr('保存'), (29, 31)), (tr('查找'), (29, 33)), (tr('撤销'), (29, 44))]
    elif identifier in ('pcmanfm', 'pcmanfm-qt'):
        kind = 'files'
        commands = [(tr('地址栏'), (29, 38)), (tr('上级目录'), (56, 103)), (tr('上一目录'), (56, 105)), (tr('重命名'), (60,))]
    elif identifier in ('rp-bookshelf', 'bookshelf'):
        kind = 'bookshelf'
    elif 'terminal' in identifier or identifier in ('ghostty', 'com.mitchellh.ghostty'):
        kind = 'terminal'
    return {'kind': kind, 'mode': mode, 'commands': commands}


class ApplicationRouter(QObject):
    def __init__(self, controller, windows, gamepad, output, isolation, parent=None):
        super().__init__(parent)
        self.controller, self.windows, self.gamepad = controller, windows, gamepad
        self.output, self.isolation = output, isolation
        self.enabled = bool(isolation.available and output.available)
        self.shell = False
        self.suspended = False
        self.session_safe = True
        self.protocol_failed = False
        self.directions_available = False
        self.target = None
        self.return_target = None
        self.resume_pending = False
        self.activation_pending = False
        self.windows_revision = 0
        self.activation_revision = 0
        self.menu_open = False
        self.mode = 'suspended'
        self.error = '' if self.enabled else tr('完整应用兼容模式需要独立 uDeck 会话及虚拟输入协议')
        self.key = None
        self.held = set()
        self.suppressed = set()
        self.directions = set()
        self.movement_started = 0
        self.command_pending = None
        self.motion = QTimer(self)
        self.motion.setInterval(16)
        self.motion.timeout.connect(self._move)
        self.activation_timer = QTimer(self)
        self.activation_timer.setSingleShot(True)
        self.activation_timer.setInterval(2500)
        self.activation_timer.timeout.connect(self._activation_expired)
        windows.changed.connect(self._windows)
        windows.failed.connect(self._failed)
        isolation.finished.connect(self._configured)
        controller.applicationAction.connect(self.menu_action)
        controller.changed.connect(self._modal_changed)

    def state(self):
        target = self.return_target if self.menu_open else self.target
        return {'available': self.enabled, 'mode': self.mode, 'application': (target or {}).get('application', ''),
                'windowId': (target or {}).get('id', ''), 'virtualInput': bool(self.output.available),
                'directionReader': self.directions_available,
                'sessionSafe': self.session_safe and not self.suspended,
                'directionIsolation': bool(self.isolation.applied), 'configurationPending': self.isolation.pending is not None,
                'error': self.error}

    def _publish(self):
        value = self.state()
        if self.controller.data['input'].get('compatibility') != value:
            self.controller.input_status({'compatibility': value})

    def _windows(self, rows):
        self.windows_revision += 1
        active = next((entry for entry in rows if entry.get('active')), None)
        if active:
            parent = active
            seen = set()
            while parent.get('parentId') and parent['parentId'] not in seen:
                seen.add(parent['parentId'])
                parent = next((entry for entry in rows if entry['id'] == parent['parentId']), parent)
            self.target = {**active, 'application': parent.get('appId') or active.get('appId') or ''}
        else:
            self.target = None
        self.refresh()

    def window_active(self, active):
        self.shell = active
        self.refresh()

    def _failed(self, message):
        self.protocol_failed = True
        self.error = message
        self.refresh()
        self.controller.notify(self.error)
        self.controller.present.emit()

    def set_suspended(self, suspended):
        self.suspended = suspended
        if suspended:
            self.activation_pending = False
            self.resume_pending = False
        self.refresh()

    def session_update(self, values):
        self.session_safe = bool(values.get('available') and values.get('active') and not values.get('locked'))
        if not self.session_safe:
            self.activation_pending = False
            self.resume_pending = False
        self.refresh()

    def gamepad_status(self, status):
        if status.get('grabbed') is False:
            self.release()
        elif status.get('grabbed') is True:
            for action in ('accept', 'back', 'context', 'quick-settings'):
                self.held.discard(action)
                self.suppressed.discard(action)

    def direction_status(self, status):
        self.directions_available = bool(status.get('available'))
        if not self.directions_available:
            self.error = status.get('error') or tr('内置方向键接口不可用；指针模式已停用')
            self.release()
            if self.mode == 'pointer' or self.resume_pending or self.activation_pending:
                self.open_menu()
                self.controller.notify(self.error)
        self.refresh()

    def _desired(self, target):
        identifier = target.get('application', '')
        if identifier in NATIVE_APPS:
            return 'native'
        mode = self.controller.config.data['applicationInput'].get(identifier, application_profile(identifier)['mode'])
        return 'keyboard' if mode == 'pointer' and not self.directions_available else mode

    def refresh(self):
        safe = not self.suspended and self.session_safe and not self.protocol_failed
        target_active = bool(self.return_target and self.target and self.target['id'] == self.return_target['id'] and not self.shell
                             and (not self.activation_pending or self.windows_revision > self.activation_revision))
        if self.activation_pending and safe and not target_active:
            self.mode = 'transition'
            self._publish()
            return
        self.activation_pending = False
        self.activation_timer.stop()
        if safe and (self.resume_pending or self.menu_open and not self.shell):
            self.mode = 'transition'
            self.gamepad.set_foreground(False)
            self._publish()
            return
        desired = ('suspended' if self.suspended or not self.session_safe else 'desktop' if self.shell
                   else 'suspended' if self.protocol_failed else self._desired(self.target) if self.target and self.enabled else 'native')
        if desired in ('keyboard', 'pointer') and not self.output.available:
            desired = 'suspended'
            self.error = self.output.error or tr('虚拟输入已断开')
        identity = (desired, (self.target or {}).get('id') if not self.shell else '', self.suspended)
        if identity != self.key:
            self.release()
            self.gamepad.set_foreground(False)
            self.key = identity
        if desired == 'pointer' and (not self.isolation.applied or self.isolation.pending is not None):
            self.mode = 'transition'
            self.open_menu()
            self.resume_pending = True
            self.isolation.request(True)
        elif desired != 'pointer' and (self.isolation.applied or self.isolation.pending is True) and not self.resume_pending:
            self.mode = 'transition'
            self.isolation.request(False)
        else:
            self.mode = desired
            self.gamepad.set_foreground(desired in ('desktop', 'keyboard', 'pointer'))
            if desired == 'pointer' and identity != getattr(self, 'pointer_identity', None):
                self.output.move(0, 0)
                self.pointer_identity = identity
        self._publish()
        if self.command_pending and self.mode in ('keyboard', 'pointer', 'native') and target_active:
            self.output.chord(self.command_pending)
            self.command_pending = None

    def _activation_expired(self):
        if not self.activation_pending:
            return
        self.activation_pending = False
        self.command_pending = None
        if not self.return_target or not any(entry['id'] == self.return_target['id'] for entry in self.windows.entries()):
            self._gone()
            return
        self.error = tr('应用未取得前台焦点；请重新返回应用')
        self.menu_open = True
        self._menu()
        self.controller.notify(self.error)
        self.controller.present.emit()

    def release(self):
        self.motion.stop()
        self.directions.clear()
        self.suppressed.update(self.held)
        self.output.release_all()

    def button(self, action, pressed):
        if not pressed:
            self.held.discard(action)
            self.suppressed.discard(action)
            if self.mode == 'pointer' and action in ('accept', 'context'):
                self.output.button(272 if action == 'accept' else 273, False)
            return
        if action in self.held:
            return
        self.held.add(action)
        if action in self.suppressed or self.mode not in ('keyboard', 'pointer'):
            return
        if action == 'quick-settings':
            self.open_menu()
        elif self.mode == 'pointer' and action in ('accept', 'context'):
            self.output.button(272 if action == 'accept' else 273, True)
        elif action in ('accept', 'back', 'context'):
            self.output.chord({'accept': (28,), 'back': (1,), 'context': (42, 68)}[action])

    def action(self, action):
        if self.mode == 'desktop' and not self.suspended:
            self.controller.dispatch(action)

    def shoulder(self, action):
        if self.mode == 'keyboard':
            self.output.chord((42, 15) if action == 'previous-page' else (15,))
        elif self.mode == 'pointer':
            self.output.scroll(-1 if action == 'previous-page' else 1)

    def direction(self, action, pressed):
        if not pressed:
            self.held.discard('direction:' + action)
            self.suppressed.discard('direction:' + action)
            self.directions.discard(action)
        elif self.mode == 'pointer' and 'direction:' + action not in self.suppressed:
            self.held.add('direction:' + action)
            self.directions.add(action)
        else:
            self.held.add('direction:' + action)
        if self.directions and self.mode == 'pointer':
            if not self.motion.isActive():
                self.movement_started = time.monotonic()
                self._move()
                self.motion.start()
        else:
            self.motion.stop()

    def _move(self):
        if self.mode != 'pointer' or not self.directions:
            self.motion.stop()
            return
        horizontal = int('right' in self.directions) - int('left' in self.directions)
        vertical = int('down' in self.directions) - int('up' in self.directions)
        speed = min(16, 3 + max(0, time.monotonic() - self.movement_started - 0.3) * 12)
        divisor = math.sqrt(2) if horizontal and vertical else 1
        self.output.move(horizontal * speed / divisor, vertical * speed / divisor)

    def open_menu(self):
        target = self.return_target if self.menu_open or self.activation_pending else self.target
        if not target or not self.enabled or self.suspended or not self.session_safe:
            self.controller.notify(self.error or tr('当前没有可控制的应用窗口'))
            return
        self.release()
        self.activation_pending = False
        self.activation_timer.stop()
        self.resume_pending = False
        self.mode = 'transition'
        self.gamepad.set_foreground(False)
        self.return_target = dict(target)
        self.menu_open = True
        self._menu()
        self.controller.present.emit()

    def _menu(self):
        target = self.return_target
        mode = self._desired(target)
        self.controller._cancel_modals()
        self.controller._menu(target.get('name', tr('应用')) + ' · ' + MODE_NAMES[mode], [
            {'label': tr('返回应用'), 'action': 'application-control', 'command': 'return'},
            {'label': tr('切换操作模式'), 'action': 'application-control', 'command': 'modes'},
            {'label': tr('常用操作'), 'action': 'application-control', 'command': 'commands'},
            {'label': tr('返回桌面'), 'action': 'application-control', 'command': 'home'},
            {'label': tr('快捷设置'), 'action': 'application-control', 'command': 'quick-settings'},
            {'label': tr('请求关闭应用'), 'action': 'application-control', 'command': 'close'},
        ], source='application', body=tr('方向键导航 · A 确认 · B 返回；指针模式中 A 按住拖动，L/R 滚动'))

    def _modal_changed(self):
        if self.menu_open and not self.controller.modal and not self.resume_pending:
            QTimer.singleShot(0, self._return_if_closed)

    def _return_if_closed(self):
        if self.menu_open and not self.controller.modal and not self.resume_pending:
            self.resume()

    def menu_action(self, command):
        if not self.menu_open or not self.return_target:
            return
        if command == 'return':
            self.resume()
        elif command == 'modes':
            self._menu()
            self.controller._menu(tr('操作模式'), [{'label': name, 'action': 'application-control', 'command': 'mode:' + mode}
                                              for mode, name in MODE_NAMES.items()], source='application')
        elif command.startswith('mode:'):
            self.set_mode(command[5:])
        elif command == 'commands':
            self._menu()
            options = [{'label': name, 'action': 'application-control', 'command': 'shortcut:' + str(index)}
                       for index, (name, keys) in enumerate(application_profile(self.return_target['application'])['commands'])]
            self.controller._menu(tr('常用操作'), options or [{'label': tr('此应用使用通用按键或指针操作'), 'action': 'none', 'disabled': True}], source='application')
        elif command.startswith('shortcut:'):
            try:
                self.command_pending = application_profile(self.return_target['application'])['commands'][int(command[9:])][1]
                self.resume()
            except (ValueError, IndexError):
                self.controller.notify(tr('操作不存在'))
        elif command == 'home':
            self.leave_menu()
            self.controller.dispatch('home')
        elif command == 'quick-settings':
            self._menu()
            self.controller.dispatch('quick-settings')
        elif command == 'close':
            self._menu()
            self.controller._confirm(tr('请求关闭应用？'), tr('应用可能要求保存工作；不会强制结束进程。'),
                                     {'action': 'application-control', 'command': 'close-confirm'})
        elif command == 'close-confirm':
            try:
                self.windows.request(self.return_target['id'], 'close')
                self.resume()
            except RuntimeError:
                self._gone()

    def set_mode(self, mode):
        if mode not in MODE_NAMES:
            self.controller.notify(tr('未知的输入模式'))
            return False
        if not self.enabled or self.suspended or not self.session_safe:
            self.controller.notify(self.error)
            return False
        if mode == 'pointer' and not self.directions_available:
            self.controller.notify(self.error or tr('内置方向键接口不可用，无法启用指针模式'))
            return False
        if not self.menu_open:
            self.open_menu()
        if not self.return_target:
            return False
        identifier = self.return_target['application']
        if identifier in NATIVE_APPS and mode != 'native':
            self.controller.notify(tr('uDeck 终端使用自身原生按键操作') if identifier == TERMINAL_APP else tr('uDeck apps manage their own input'))
            self._menu()
            return False
        previous = dict(self.controller.config.data['applicationInput'])
        self.controller.config.data['applicationInput'][identifier] = mode
        try:
            self.controller.config.save()
        except OSError as error:
            self.controller.config.data['applicationInput'] = previous
            self.controller.notify(tr('输入模式保存失败：') + error_text(error))
            return False
        self.resume()
        return True

    def resume(self):
        if not self.return_target or self.suspended or not self.session_safe:
            return
        if not any(entry['id'] == self.return_target['id'] for entry in self.windows.entries()):
            self._gone()
            return
        self.release()
        self.mode = 'transition'
        self.gamepad.set_foreground(False)
        self.resume_pending = True
        self.isolation.request(self._desired(self.return_target) == 'pointer')

    def _configured(self, success):
        if not success:
            self.release()
            self.resume_pending = False
            self.error = self.isolation.error
            if self.return_target:
                self.menu_open = True
                self._menu()
                self.controller.notify(self.error)
                self.controller.present.emit()
            self._publish()
            self.refresh()
            return
        if not self.protocol_failed and self.directions_available:
            self.error = ''
        if self.resume_pending and not self.suspended and self.session_safe and not self.protocol_failed:
            self.resume_pending = False
            target = self.return_target
            if not target:
                self._gone()
                return
            self.menu_open = False
            self.controller._cancel_modals()
            try:
                self.activation_pending = True
                self.activation_revision = self.windows_revision
                self.activation_timer.start()
                self.windows.request(target['id'], 'activate')
            except RuntimeError:
                self._gone()
                return
            self.mode = 'transition'
            self._publish()
            return
        self.refresh()

    def leave_menu(self):
        self.menu_open = False
        self.resume_pending = False
        self.activation_pending = False
        self.activation_timer.stop()
        self.return_target = None
        self.command_pending = None
        self.release()
        self.mode = 'transition'
        self.gamepad.set_foreground(False)

    def _gone(self):
        self.leave_menu()
        self.controller.dispatch('switcher')

    def close(self):
        self.leave_menu()
        self.gamepad.set_foreground(False)
