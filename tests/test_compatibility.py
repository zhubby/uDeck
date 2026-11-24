"""
[INPUT]: 依赖隔离窗口、输入输出与真实桌面控制器。
[OUTPUT]: 验证连续导航、受限交接和激活超时恢复。
[POS]: 应用路由回归；覆盖会话锁定、指针隔离和焦点切换。
[PROTOCOL]: Update this header on change, then check AGENTS.md
"""

from types import SimpleNamespace

import pytest
from PySide6.QtCore import QCoreApplication, QObject, Signal

from udeck.compatibility import ApplicationRouter, application_profile
from udeck.controller import ShellController
from udeck.core import ConfigStore
from udeck.i18n import Msg
from udeck.mock import MockBackend


class Windows(QObject):
    changed = Signal(list)
    failed = Signal(str)

    def __init__(self):
        super().__init__()
        self.rows = []
        self.requests = []

    def entries(self):
        return self.rows

    def request(self, identifier, operation):
        if not any(entry['id'] == identifier for entry in self.rows):
            raise RuntimeError('window gone')
        self.requests.append((identifier, operation))


class Isolation(QObject):
    finished = Signal(bool)

    def __init__(self):
        super().__init__()
        self.available = True
        self.applied = False
        self.pending = None
        self.error = ''

    def request(self, enabled):
        self.pending = enabled

    def complete(self, success=True):
        if success:
            self.applied = self.pending
        self.pending = None
        self.error = '' if success else 'reload timed out'
        self.finished.emit(success)


@pytest.fixture
def routing(tmp_path):
    application = QCoreApplication.instance() or QCoreApplication([])
    windows, isolation = Windows(), Isolation()
    controller = ShellController(MockBackend(), windows, ConfigStore(tmp_path / 'settings.json'), mock=True)
    events = []
    output = SimpleNamespace(available=True, error='', chord=lambda keys: events.append(('chord', tuple(keys))),
                             button=lambda code, pressed: events.append(('button', code, pressed)),
                             move=lambda horizontal, vertical: events.append(('move', horizontal, vertical)),
                             scroll=lambda amount: events.append(('scroll', amount)),
                             release_all=lambda: events.append(('release',)))
    ownership = []
    gamepad = SimpleNamespace(set_foreground=ownership.append)
    router = ApplicationRouter(controller, windows, gamepad, output, isolation)
    router.direction_status({'available': True})
    yield SimpleNamespace(router=router, controller=controller, windows=windows, isolation=isolation,
                          events=events, ownership=ownership, application=application)
    router.close()
    controller.close()


def focus(routing, identifier='10', app_id='firefox'):
    routing.windows.rows = [{'id': identifier, 'appId': app_id, 'name': 'Owned application', 'active': True, 'parentId': ''}]
    routing.router.window_active(False)
    routing.windows.changed.emit(routing.windows.rows)


def test_native_activation_releases_input_before_presenting_the_target(routing):
    from udeck.app_routing import APP_IDS

    router = routing.router
    routing.windows.rows = [{'id': 'music', 'appId': APP_IDS['music'], 'active': False}]
    router.window_active(True)
    assert routing.ownership[-1] is True

    assert router.prepare_native_activation(APP_IDS['music'])
    assert routing.ownership[-1] is False
    assert router.mode == 'transition' and not routing.windows.requests
    router.refresh()
    assert routing.ownership[-1] is False

    router.window_active(False)
    routing.windows.rows[0]['active'] = True
    routing.windows.changed.emit(routing.windows.rows)
    assert router.mode == 'native' and not router.activation_pending
    assert not router.activation_timer.isActive()


@pytest.mark.parametrize('retry', [False, True])
def test_late_native_focus_clears_its_activation_timeout_and_owned_menu(routing, retry):
    from udeck.app_routing import APP_IDS

    router = routing.router
    routing.windows.rows = [{'id': 'emulator', 'appId': APP_IDS['emulator'], 'active': False}]
    router.window_active(True)
    assert router.prepare_native_activation(APP_IDS['emulator'])
    router._activation_expired()
    assert router.error and router.menu_open and routing.controller.modal
    if retry:
        assert router.prepare_native_activation(APP_IDS['emulator'])
    router.window_active(False)
    routing.windows.rows[0]['active'] = True
    routing.windows.changed.emit(routing.windows.rows)
    assert router.mode == 'native' and not router.activation_pending
    assert not router.error and not router.menu_open and not routing.controller.modal


@pytest.mark.parametrize('retry', [False, True])
def test_activation_timeout_recovers_when_qt_focus_arrives_after_toplevel_state(routing, retry):
    from udeck.app_routing import APP_IDS

    router = routing.router
    routing.windows.rows = [{'id': 'emulator', 'appId': APP_IDS['emulator'], 'active': False}]
    router.window_active(True)
    assert router.prepare_native_activation(APP_IDS['emulator'])
    routing.windows.rows[0]['active'] = True
    routing.windows.changed.emit(routing.windows.rows)
    assert router.activation_pending
    router._activation_expired()
    if retry:
        assert router.prepare_native_activation(APP_IDS['emulator'])
    router.window_active(False)
    assert router.mode == 'native' and not router.activation_pending
    assert not router.error and not router.menu_open and not routing.controller.modal


@pytest.mark.parametrize('failure', ['direction', 'protocol'])
def test_late_native_focus_preserves_a_new_device_or_protocol_error(routing, failure):
    from udeck.app_routing import APP_IDS

    router = routing.router
    routing.windows.rows = [{'id': 'emulator', 'appId': APP_IDS['emulator'], 'active': False}]
    router.window_active(True)
    assert router.prepare_native_activation(APP_IDS['emulator'])
    router._activation_expired()
    if failure == 'direction':
        router.direction_status({'available': False, 'error': 'Keyboard disconnected after timeout'})
    else:
        routing.windows.failed.emit('Window protocol disconnected after timeout')
    current_error = router.error
    router.window_active(False)
    routing.windows.rows[0]['active'] = True
    routing.windows.changed.emit(routing.windows.rows)
    assert router.error == current_error
    if failure == 'direction':
        assert router.mode == 'native' and not router.menu_open and not routing.controller.modal
    else:
        assert router.mode == 'suspended' and router.protocol_failed


def test_late_native_focus_preserves_another_applications_control_menu(routing):
    from udeck.app_routing import APP_IDS

    router = routing.router
    routing.windows.rows = [{'id': 'emulator', 'appId': APP_IDS['emulator'], 'active': False}]
    router.window_active(True)
    assert router.prepare_native_activation(APP_IDS['emulator'])
    router._activation_expired()
    router.leave_menu()
    routing.controller._cancel_modals()
    routing.windows.rows.append({'id': 'other', 'appId': 'external.application', 'name': 'Other', 'active': True})
    router.window_active(False)
    routing.windows.changed.emit(routing.windows.rows)
    router.open_menu()
    owned_menu = routing.controller.modal['key']
    router.window_active(True)
    routing.windows.rows[0]['active'] = True
    routing.windows.rows[1]['active'] = False
    router.window_active(False)
    routing.windows.changed.emit(routing.windows.rows)
    assert router.menu_open and router.return_target['id'] == 'other'
    assert routing.controller.modal['key'] == owned_menu


def test_activation_timeout_waits_for_an_unambiguous_matching_window(routing):
    from udeck.app_routing import APP_IDS

    router = routing.router
    routing.windows.rows = [{'id': 'emulator', 'appId': APP_IDS['emulator'], 'active': False}]
    router.window_active(True)
    assert router.prepare_native_activation(APP_IDS['emulator'])
    router._activation_expired()
    error, menu = router.error, routing.controller.modal['key']
    router.window_active(False)
    routing.windows.rows[0]['active'] = True
    routing.windows.rows.append({'id': 'other', 'appId': 'external.application', 'active': True})
    routing.windows.changed.emit(routing.windows.rows)
    assert router.error == error and routing.controller.modal['key'] == menu
    routing.windows.rows[1]['active'] = False
    routing.windows.rows[0]['appId'] = 'different.application'
    routing.windows.changed.emit(routing.windows.rows)
    assert router.error == error and routing.controller.modal['key'] == menu
    routing.windows.rows[0]['appId'] = APP_IDS['emulator']
    routing.windows.changed.emit(routing.windows.rows)
    assert router.mode == 'native' and not router.error and not router.menu_open


def test_native_cold_start_releases_input_until_its_first_window_has_focus(routing, monkeypatch):
    from udeck.app_routing import APP_IDS

    monkeypatch.setattr('udeck.compatibility.native_service_registered', lambda _app_id: True)
    router = routing.router
    router.window_active(True)
    assert router.prepare_native_activation(APP_IDS['music'])
    assert routing.ownership[-1] is False and router.mode == 'transition'
    router.refresh()
    assert routing.ownership[-1] is False
    routing.windows.rows = [{'id': 'other', 'appId': 'external.application', 'active': False}]
    routing.windows.changed.emit(routing.windows.rows)
    assert router.mode == 'transition' and router.activation_pending
    routing.windows.rows.append({'id': 'music', 'appId': APP_IDS['music'], 'active': True})
    router.window_active(False)
    routing.windows.changed.emit(routing.windows.rows)
    assert router.mode == 'native' and not router.activation_pending
    assert not router.activation_timer.isActive() and not routing.windows.requests


def test_failed_native_cold_start_restores_desktop_input_after_its_deadline(routing, monkeypatch):
    from PySide6.QtCore import QEventLoop, QTimer

    from udeck.app_routing import APP_IDS

    monkeypatch.setattr('udeck.compatibility.native_service_registered', lambda _app_id: True)
    router = routing.router
    router.window_active(True)
    router.activation_timer.setInterval(20)
    assert router.prepare_native_activation(APP_IDS['music'])
    assert routing.ownership[-1] is False
    loop = QEventLoop()
    QTimer.singleShot(100, loop.quit)
    loop.exec()
    assert not router.activation_pending and not router.activation_timer.isActive()
    assert router.mode == 'desktop' and routing.ownership[-1] is True


def test_native_cold_start_rejects_an_application_without_a_current_session_service(routing, monkeypatch):
    from udeck.app_routing import APP_IDS

    monkeypatch.setattr('udeck.compatibility.native_service_registered', lambda _app_id: False)
    routing.router.window_active(True)
    routing.ownership.clear()
    assert not routing.router.prepare_native_activation(APP_IDS['music'])
    assert not routing.ownership and not routing.router.activation_pending


@pytest.mark.parametrize('unsafe', ['unknown-app', 'locked-session', 'suspended', 'failed-protocol'])
def test_native_input_preparation_rejects_an_invalid_target_or_session(routing, unsafe):
    from udeck.app_routing import APP_IDS

    router = routing.router
    routing.windows.rows = [{'id': 'music', 'appId': APP_IDS['music'], 'active': False}]
    router.window_active(True)
    app_id = APP_IDS['music']
    if unsafe == 'unknown-app':
        app_id = 'external.application'
    elif unsafe == 'locked-session':
        router.session_safe = False
    elif unsafe == 'suspended':
        router.suspended = True
    elif unsafe == 'failed-protocol':
        router.protocol_failed = True
    routing.ownership.clear()

    assert not router.prepare_native_activation(app_id)
    assert not routing.ownership and not router.activation_pending


def test_keyboard_mode_routes_abxy_and_shoulders_without_typing_letters(routing):
    focus(routing)
    routing.router.button('accept', True)
    routing.router.button('accept', False)
    routing.router.button('back', True)
    routing.router.button('context', True)
    routing.router.shoulder('previous-page')
    routing.router.shoulder('next-page')
    chords = [event for event in routing.events if event[0] == 'chord']
    assert chords == [('chord', (28,)), ('chord', (1,)), ('chord', (42, 68)), ('chord', (42, 15)), ('chord', (15,))]
    assert routing.router.state()['mode'] == 'keyboard'
    assert routing.ownership[-1] is True


def test_y_menu_defaults_to_return_and_back_restores_exact_window(routing):
    focus(routing, app_id='io.github.zhubby.uDeck.Music')
    routing.router.open_menu()
    assert routing.controller.modal['source'] == 'application'
    assert routing.controller.modal['index'] == 0
    assert 'Owned application' in routing.controller.modal['title']
    routing.router.window_active(True)
    routing.controller.dispatch('back')
    routing.isolation.complete()
    assert routing.windows.requests[-1] == ('10', 'activate')
    assert not routing.controller.modal


def test_pointer_input_keeps_existing_foreground_without_activating_a_window(routing):
    focus(routing)
    routing.controller.config.data['applicationInput']['firefox'] = 'pointer'
    routing.isolation.applied = True
    routing.router.refresh()
    routing.router.button('accept', True)
    routing.router.direction('right', True)
    assert ('button', 272, True) in routing.events
    assert any(event[0] == 'move' and event[1] > 0 for event in routing.events)
    routing.router.button('accept', False)
    assert routing.events[-1] == ('button', 272, False)
    routing.router.direction('right', False)
    assert not routing.router.motion.isActive()
    assert routing.windows.requests == []


def test_console_resume_waits_for_isolation_ack_before_restoring_native_window(routing):
    focus(routing, app_id='io.github.zhubby.uDeck.Music')
    routing.isolation.applied = True
    routing.router.window_active(True)
    assert routing.router.resume_window('10')
    assert ('10', 'activate') not in routing.windows.requests
    routing.isolation.complete()
    assert routing.windows.requests[-1] == ('10', 'activate')
    assert not routing.router.resume_window('gone')


def test_console_resume_rejects_an_external_window_before_input_handoff(routing):
    focus(routing, app_id='xarchiver')
    routing.router.window_active(True)
    assert not routing.router.resume_window('10')
    assert routing.isolation.pending is None
    assert routing.windows.requests == []


def test_delayed_application_return_cannot_activate_a_reused_external_window(routing):
    focus(routing, app_id='io.github.zhubby.uDeck.Music')
    routing.router.open_menu()
    routing.router.window_active(True)
    routing.router.resume()
    routing.windows.rows[0]['appId'] = 'xarchiver'
    routing.isolation.complete()
    assert routing.windows.requests == []
    assert routing.controller.navigation.page == 'windows'


def test_console_resume_preserves_parent_application_profile(routing):
    routing.windows.rows = [
        {'id': '10', 'appId': 'io.github.zhubby.uDeck.Music', 'name': 'Parent', 'active': False, 'parentId': ''},
        {'id': '11', 'appId': '', 'name': 'Dialog', 'active': True, 'parentId': '10'},
    ]
    assert routing.router.resume_window('11')
    assert routing.router.return_target['application'] == 'io.github.zhubby.uDeck.Music'
    assert routing.isolation.pending is False


def test_reload_failure_keeps_menu_and_does_not_inject(routing):
    focus(routing, app_id='io.github.zhubby.uDeck.Music')
    routing.router.open_menu()
    routing.router.window_active(True)
    routing.router.resume()
    routing.isolation.complete(False)
    routing.router.button('accept', True)
    assert not routing.windows.requests
    assert not any(event[0] == 'button' for event in routing.events)
    assert routing.controller.modal
    assert routing.router.state()['error']


def test_focus_handoff_releases_drag_and_requires_new_button_press(routing):
    focus(routing)
    routing.isolation.applied = True
    routing.controller.config.data['applicationInput']['firefox'] = 'pointer'
    routing.router.refresh()
    routing.router.button('accept', True)
    focus(routing, '11', 'chromium')
    assert routing.events[-1] == ('release',)
    routing.isolation.complete()
    routing.router.button('accept', True)
    assert routing.events[-1] == ('release',)
    routing.router.button('accept', False)
    routing.router.button('accept', True)
    assert routing.events[-1] == ('chord', (28,))


def test_gone_return_window_goes_to_switcher(routing):
    focus(routing)
    routing.router.open_menu()
    routing.windows.rows = []
    routing.windows.changed.emit([])
    routing.router.resume()
    assert routing.controller.navigation.page == 'windows'
    assert not routing.windows.requests


def test_native_terminal_and_retroarch_release_controller(routing):
    for identifier in ('io.github.zhubby.uDeck.Terminal', 'retroarch'):
        focus(routing, app_id=identifier)
        assert routing.ownership[-1] is False
        assert routing.router.state()['mode'] == 'native'


def test_lock_and_protocol_failure_stop_injection(routing):
    focus(routing)
    routing.router.set_suspended(True)
    before = list(routing.events)
    routing.router.button('accept', True)
    routing.router.shoulder('next-page')
    assert routing.events == before
    assert routing.ownership[-1] is False
    routing.router.set_suspended(False)
    routing.windows.failed.emit('connection lost')
    assert routing.router.state()['mode'] == 'suspended'


def test_child_dialog_inherits_parent_application_profile(routing):
    routing.windows.rows = [{'id': '10', 'appId': 'firefox', 'active': False, 'parentId': ''},
                            {'id': '11', 'appId': '', 'name': 'Save', 'active': True, 'parentId': '10'}]
    routing.windows.changed.emit(routing.windows.rows)
    assert routing.router.state()['application'] == 'firefox'
    assert routing.router.state()['windowId'] == '11'


def test_profiles_use_fixed_actions_and_default_unknown_to_keyboard():
    assert application_profile('some.custom.app')['mode'] == 'keyboard'
    assert application_profile('Code')['kind'] == 'editor'
    commands = {label.key: keys for label, keys in application_profile('chromium')['commands']}
    assert commands[Msg.ADDRESS_BAR] == (29, 38)


def test_mode_config_preserves_existing_user_data(tmp_path):
    config = ConfigStore(tmp_path / 'settings.json')
    config.data['favorites'] = ['app.desktop']
    config.data['input'] = {'fingerprint': 'existing'}
    config.data['applicationInput'] = {'firefox': 'pointer', 'bad': 'shell command'}
    config.save()
    loaded = ConfigStore(config.path)
    assert loaded.data['applicationInput'] == {'firefox': 'pointer'}
    assert loaded.data['favorites'] == ['app.desktop']
    assert loaded.data['input'] == {'fingerprint': 'existing'}


def test_pointer_unavailable_without_direction_reader_and_disconnect_restores_keyboard(routing):
    focus(routing)
    routing.router.direction_status({'available': False, 'error': 'Keyboard disconnected'})
    assert routing.router.set_mode('pointer') is False
    assert routing.router.state()['directionReader'] is False
    assert routing.isolation.pending is None
    routing.router.direction_status({'available': True})
    routing.router.open_menu()
    routing.router.window_active(True)
    routing.router.set_mode('pointer')
    routing.isolation.complete()
    routing.router.window_active(False)
    routing.windows.changed.emit(routing.windows.rows)
    routing.router.direction('right', True)
    routing.router.direction_status({'available': False, 'error': 'Keyboard disconnected'})
    assert not routing.router.motion.isActive()
    routing.router.window_active(True)
    assert routing.isolation.pending is False
    routing.isolation.complete()
    assert not routing.isolation.applied
    assert routing.controller.modal


def test_external_shortcut_cannot_activate_or_inject_into_a_return_target(routing):
    focus(routing)
    routing.controller.config.data['applicationInput']['firefox'] = 'pointer'
    routing.isolation.applied = True
    routing.router.refresh()
    routing.router.open_menu()
    routing.router.window_active(True)
    routing.isolation.complete()
    routing.router.menu_action('shortcut:0')
    routing.isolation.complete()
    routing.router.window_active(False)
    routing.windows.rows = [{'id': '20', 'appId': 'other', 'name': 'Other', 'active': True}]
    routing.windows.changed.emit(routing.windows.rows)
    assert ('chord', (29, 38)) not in routing.events
    focus(routing)
    assert ('chord', (29, 38)) not in routing.events
    assert routing.windows.requests == []
    assert routing.router.command_pending is None


def test_late_ack_after_session_lock_cannot_activate_or_inject(routing):
    focus(routing)
    routing.router.open_menu()
    routing.router.window_active(True)
    routing.router.set_mode('pointer')
    routing.router.session_update({'available': True, 'active': False, 'locked': True})
    routing.isolation.complete()
    assert not routing.windows.requests
    assert routing.router.state()['mode'] == 'suspended'
    assert not any(event[0] in ('chord', 'button', 'move') for event in routing.events)


def test_nested_mode_menu_back_and_regrab_require_fresh_press(routing):
    focus(routing)
    routing.router.button('quick-settings', True)
    routing.router.window_active(True)
    routing.router.menu_action('modes')
    routing.controller.dispatch('back')
    assert routing.controller.modal['source'] == 'application'
    assert routing.controller.modal['title'].startswith('Owned application')
    routing.router.gamepad_status({'grabbed': False})
    routing.router.gamepad_status({'grabbed': True})
    routing.router.button('quick-settings', True)
    assert 'quick-settings' not in routing.router.suppressed


def test_home_handoff_stops_injection_before_shell_takes_focus(routing):
    focus(routing)
    routing.router.leave_menu()
    before = list(routing.events)
    routing.router.button('accept', True)
    routing.router.shoulder('next-page')
    assert routing.events == before
    assert routing.ownership[-1] is False


def test_desktop_page_handoff_keeps_input_ready_without_releasing_device(routing):
    routing.router.window_active(True)
    routing.ownership.clear()
    routing.router.leave_menu()
    assert routing.router.mode == 'desktop'
    assert False not in routing.ownership
    routing.router.action('next-page')
    assert routing.controller.navigation.page == 'apps'


def test_duplicate_input_status_does_not_republish_the_view(routing):
    controller = routing.controller
    controller.input_status({'foreground': True})
    publications = []
    controller.viewChanged.connect(lambda: publications.append(True))
    controller.input_status({'foreground': True})
    assert not publications
    controller.input_status({'foreground': False})
    assert publications == [True]


def test_duplicate_ungrab_still_clears_diagnostic_held_buttons(routing):
    controller = routing.controller
    controller.input_status({'grabbed': False})
    controller._open_key_test()
    controller.testButton('accept', True, 'gamepad')
    assert controller.modal['pressed'] == ['accept']
    controller.input_status({'grabbed': False})
    assert controller.modal['pressed'] == []


def test_protocol_failure_still_allows_shell_navigation(routing):
    focus(routing)
    routing.router._failed('protocol unavailable')
    routing.router.window_active(True)
    assert routing.router.mode == 'desktop'
    routing.router.action('next-page')
    assert routing.controller.navigation.page == 'apps'
