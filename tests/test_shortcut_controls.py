import json

import pytest
from PySide6.QtCore import QCoreApplication

from udeck.controller import ShellController
from udeck.core import ConfigStore
from udeck.mock import MockBackend


def create(tmp_path):
    application = QCoreApplication.instance() or QCoreApplication([])
    return application, ShellController(MockBackend(), config=ConfigStore(tmp_path / 'settings.json'), mock=True)


def choose(controller, identifier):
    controller.chooseModal(next(i for i, option in enumerate(controller.modal['options']) if option['id'] == identifier))


def test_settings_lists_unbound_actions_and_edit_keeps_menu_position(tmp_path):
    app, controller = create(tmp_path)
    try:
        assert any(item['id'] == 'shortcuts' for item in controller._settings())
        controller.activateSetting('shortcuts')
        choose(controller, 'power')
        choose(controller, 'poweroff')
        assert controller.modal['source'] == 'shortcut-action'
        assert any(option['id'] == 'add' for option in controller.modal['options'])
        controller.setShortcut('poweroff', 'Ctrl+Alt+F12', -1)
        assert controller.shortcut_store.bindings()['poweroff'] == ['C-A-F12']
        assert controller.modal['source'] == 'shortcut-action'
        controller.dispatch('back')
        assert controller.modal['source'] == 'shortcuts-group'
        assert controller.modal['options'][controller.modal['index']]['id'] == 'poweroff'
    finally:
        controller.close()
    assert app


def test_conflict_cancel_and_transfer_preserve_other_aliases(tmp_path):
    app, controller = create(tmp_path)
    try:
        controller.setLanguage('zh_CN')
        controller.activateSetting('shortcuts')
        choose(controller, 'navigation')
        choose(controller, 'terminal')
        controller.setShortcut('terminal', 'Ctrl+Alt+P', 0)
        assert controller.modal['kind'] == 'confirm'
        assert '全屏截图' in json.loads(controller.snapshotJson)['modal']['body']
        controller.dispatch('accept')
        assert controller.shortcut_store.bindings()['terminal'] == ['C-A-t']
        controller.setShortcut('terminal', 'Ctrl+Alt+P', 0)
        controller.dispatch('right')
        controller.dispatch('accept')
        assert controller.shortcut_store.bindings()['terminal'] == ['C-A-p']
        assert controller.shortcut_store.bindings()['screenshot'] == ['Print']
    finally:
        controller.close()
    assert app


def test_dangerous_global_actions_only_open_confirmation(tmp_path):
    app, controller = create(tmp_path)
    try:
        for action in ('logout', 'reboot', 'poweroff'):
            controller.globalAction(action)
            assert controller.modal['kind'] == 'confirm' and controller.modal['index'] == 0
            assert not controller.backend.actions
            controller.dispatch('accept')
            assert not controller.backend.actions
        controller.globalAction('apps')
        assert json.loads(controller.snapshotJson)['page'] == 'apps'
    finally:
        controller.close()
    assert app


@pytest.mark.parametrize(('action', 'component', 'current', 'expected'), [
    ('volume-up', 'audio', 0.98, ('volume', {'value': 1.0})),
    ('volume-down', 'audio', 0.02, ('volume', {'value': 0})),
    ('mute', 'audio', 0.5, ('mute', {})),
    ('brightness-up', 'brightness', 0.98, ('brightness', {'value': 1.0})),
    ('brightness-down', 'brightness', 0.02, ('brightness', {'value': 0.05})),
])
def test_media_shortcuts_use_existing_backend_with_clamped_levels(tmp_path, monkeypatch, action, component, current, expected):
    app, controller = create(tmp_path)
    try:
        calls = []
        monkeypatch.setattr(controller.backend, 'request', lambda name, payload: calls.append((name, payload)))
        controller.data[component]['volume' if component == 'audio' else 'value'] = current
        assert controller.globalAction(action)
        assert calls == [expected]
    finally:
        controller.close()
    assert app


def test_unavailable_media_action_does_not_call_backend(tmp_path):
    app, controller = create(tmp_path)
    try:
        controller.mock = False
        controller.data['sessionInput'] = {'available': True, 'active': True, 'locked': False}
        controller.data['audio']['outputs'] = []
        controller.data['brightness']['available'] = False
        assert not controller.globalAction('volume-up')
        assert not controller.globalAction('brightness-up')
        assert not controller.backend.actions
    finally:
        controller.close()
    assert app


def test_footer_follows_rebound_disabled_and_non_icon_shortcuts(tmp_path):
    app, controller = create(tmp_path)
    try:
        hints = json.loads(controller.snapshotJson)['homeShortcutHints']
        assert hints == [{'keys': ['keyboard_ctrl', '+', 'keyboard_alt', '+', 'keyboard_escape'], 'label': 'Home'}]
        controller.setShortcut('home', 'Ctrl+Alt+Q', 0)
        hints = json.loads(controller.snapshotJson)['homeShortcutHints']
        assert hints[0]['keys'][-1] == 'keyboard_q'
        controller._write_shortcut('home', ['F22'])
        hints = json.loads(controller.snapshotJson)['homeShortcutHints']
        assert hints == [{'keys': [], 'label': 'F22 · Home'}]
        controller._write_shortcut('home', [])
        assert json.loads(controller.snapshotJson)['homeShortcutHints'] == []
    finally:
        controller.close()
    assert app


def test_media_key_labels_remain_translatable_when_joined(tmp_path):
    app, controller = create(tmp_path)
    try:
        controller.setLanguage('zh_CN')
        controller.activateSetting('shortcuts')
        choose(controller, 'audio')
        assert 'Volume' not in json.loads(controller.snapshotJson)['modal']['options'][0]['subtitle']
    finally:
        controller.close()
    assert app


def test_open_shortcut_list_refreshes_device_availability_without_moving_focus(tmp_path):
    app, controller = create(tmp_path)
    try:
        controller.mock = False
        controller.activateSetting('shortcuts')
        choose(controller, 'audio')
        controller.dispatch('down')
        assert controller.modal['index'] == 1
        controller.backend.updated.emit({'audio': {'available': False, 'outputs': []}})
        modal = json.loads(controller.snapshotJson)['modal']
        assert modal['index'] == 1
        assert all('Feature unavailable' in option['subtitle'] for option in modal['options'])
    finally:
        controller.close()
    assert app
