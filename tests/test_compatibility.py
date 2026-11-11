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
    focus(routing)
    routing.router.button('quick-settings', True)
    assert routing.controller.modal['source'] == 'application'
    assert routing.controller.modal['index'] == 0
    assert 'Owned application' in routing.controller.modal['title']
    routing.router.window_active(True)
    routing.controller.dispatch('back')
    routing.isolation.complete()
    assert routing.windows.requests[-1] == ('10', 'activate')
    assert not routing.controller.modal


def test_pointer_waits_for_ack_before_return_and_drags_until_release(routing):
    focus(routing)
    routing.router.open_menu()
    routing.router.window_active(True)
    routing.router.set_mode('pointer')
    assert ('10', 'activate') not in routing.windows.requests
    routing.isolation.complete()
    assert routing.windows.requests[-1] == ('10', 'activate')
    routing.router.window_active(False)
    routing.windows.changed.emit(routing.windows.rows)
    routing.router.button('accept', True)
    routing.router.direction('right', True)
    assert ('button', 272, True) in routing.events
    assert any(event[0] == 'move' and event[1] > 0 for event in routing.events)
    routing.router.button('accept', False)
    assert routing.events[-1] == ('button', 272, False)
    routing.router.direction('right', False)
    assert not routing.router.motion.isActive()


def test_console_resume_waits_for_pointer_isolation_before_restoring_window(routing):
    focus(routing)
    routing.controller.config.data['applicationInput']['firefox'] = 'pointer'
    routing.router.window_active(True)
    assert routing.router.resume_window('10')
    assert ('10', 'activate') not in routing.windows.requests
    routing.isolation.complete()
    assert routing.windows.requests[-1] == ('10', 'activate')
    assert not routing.router.resume_window('gone')


def test_console_resume_preserves_parent_application_profile(routing):
    routing.windows.rows = [
        {'id': '10', 'appId': 'firefox', 'name': 'Parent', 'active': False, 'parentId': ''},
        {'id': '11', 'appId': '', 'name': 'Dialog', 'active': True, 'parentId': '10'},
    ]
    routing.controller.config.data['applicationInput']['firefox'] = 'pointer'
    assert routing.router.resume_window('11')
    assert routing.router.return_target['application'] == 'firefox'
    assert routing.isolation.pending is True


def test_reload_failure_keeps_menu_and_does_not_inject(routing):
    focus(routing)
    routing.router.open_menu()
    routing.router.window_active(True)
    routing.router.set_mode('pointer')
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


def test_shortcut_waits_for_exact_target_and_works_in_pointer_mode(routing):
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
    assert routing.events.count(('chord', (29, 38))) == 1


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


def test_protocol_failure_still_allows_shell_navigation(routing):
    focus(routing)
    routing.router._failed('protocol unavailable')
    routing.router.window_active(True)
    assert routing.router.mode == 'desktop'
    routing.router.action('next-page')
    assert routing.controller.navigation.page == 'apps'
