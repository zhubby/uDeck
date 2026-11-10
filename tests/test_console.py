import json

import pytest
from PySide6.QtCore import QCoreApplication, QObject, Signal

from udeck.console import ConsolePanel
from udeck.controller import ShellController
from udeck.core import ConfigStore
from udeck.main import Control
from udeck.mock import MockBackend


class Windows(QObject):
    changed = Signal(object)

    def __init__(self):
        super().__init__()
        self.rows = [{'id': 'app', 'appId': 'firefox', 'active': True}]
        self.requests = []

    def entries(self):
        return self.rows

    def request(self, identifier, operation):
        self.requests.append((identifier, operation))


@pytest.fixture
def console(tmp_path):
    application = QCoreApplication.instance() or QCoreApplication([])
    controller = ShellController(MockBackend(), config=ConfigStore(tmp_path / 'config.json'), mock=True)
    windows = Windows()
    panel = ConsolePanel(controller, windows)
    yield controller, panel, windows, application
    panel.close()
    controller.close()


def test_control_opens_one_console_and_back_restores_exact_window(console):
    controller, panel, windows, _application = console
    control = Control(controller, windows)
    control.console_panel = panel
    controller.activateSetting('key-test')
    control.Console()
    control.Console()
    assert len(controller._modals) == 1
    assert [entry['id'] for entry in controller.modal['options']] == ['home', 'switcher', 'settings', 'poweroff', 'reboot']
    assert not controller.backend.actions
    controller.dispatch('back')
    assert windows.requests == [('app', 'activate')]
    assert panel.return_target is None


@pytest.mark.parametrize('index,page', [(0, 'home'), (1, 'windows'), (2, 'settings')])
def test_console_routes_navigation_and_does_not_restore_old_app(console, index, page):
    controller, panel, windows, _application = console
    panel.open()
    controller.chooseModal(index)
    assert controller.navigation.page == page and not controller.modal
    assert panel.return_target is None and not windows.requests


@pytest.mark.parametrize('index,action', [(3, 'poweroff'), (4, 'reboot')])
def test_console_power_actions_retain_panel_and_require_confirmation(console, index, action):
    controller, panel, windows, _application = console
    panel.open()
    controller.chooseModal(index)
    assert controller.modal['kind'] == 'confirm' and controller.modal['index'] == 0
    assert not controller.backend.actions
    panel.open()  # Repeated compositor keypress must not discard the confirmation.
    assert controller.modal['kind'] == 'confirm'
    controller.dispatch('accept')  # Default is Cancel.
    assert controller.modal['source'] == 'console'
    assert not controller.backend.actions
    controller.chooseModal(index)
    controller.dispatch('right')
    controller.dispatch('accept')
    assert controller.backend.actions[-1] == action
    assert not windows.requests


def test_window_closure_and_id_reuse_cannot_restore_another_app(console):
    controller, panel, windows, _application = console
    panel.open()
    windows.rows = []
    windows.changed.emit([])
    windows.rows = [{'id': 'app', 'appId': 'mousepad', 'active': False}]
    controller.dispatch('back')
    assert not windows.requests


def test_reopening_console_from_another_app_restores_the_new_foreground(console):
    controller, panel, windows, _application = console
    panel.open()
    windows.rows = [{'id': 'other', 'appId': 'mousepad', 'active': True}]
    windows.changed.emit(windows.rows)
    panel.open()
    controller.dispatch('back')
    assert windows.requests == [('other', 'activate')]


def test_session_lock_blocks_open_and_focus_restoration(console):
    controller, panel, windows, _application = console
    panel.open()
    controller.backend.updated.emit({'sessionInput': {'available': True, 'active': True, 'locked': True}})
    controller.dispatch('back')
    panel.open()
    assert not controller.modal and not windows.requests


@pytest.mark.parametrize('language,title,labels', [
    ('en', 'Control Panel', ['Back to Home', 'Running', 'Settings', 'Power Off', 'Restart']),
    ('zh_CN', '控制台', ['回到主界面', '运行中', '设置', '关机', '重启']),
])
def test_console_names_change_language_while_open(console, language, title, labels):
    controller, panel, _windows, _application = console
    panel.open()
    controller.setLanguage(language)
    modal = json.loads(controller.snapshotJson)['modal']
    assert modal['title'] == title
    assert [entry['label'] for entry in modal['options']] == labels
