"""
[INPUT]: 依赖全局控制面板、桌面控制器与窗口服务替身。
[OUTPUT]: 验证 Console 导航入口、焦点恢复和电源确认。
[POS]: 现有快捷控制面板的兼容性回归。
[PROTOCOL]: Update this header on change, then check AGENTS.md
"""

import json
import os
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QCoreApplication, QObject, Signal

from udeck.console import ConsolePanel
from udeck.controller import ShellController
from udeck.core import ConfigStore
from udeck.main import Control
from udeck.mock import MockBackend
from udeck.runtime_console.processes import Identity
from udeck.windows import WindowService


class Windows(QObject):
    changed = Signal(object)

    def __init__(self):
        super().__init__()
        self.rows = [{'id': 'app', 'appId': 'io.github.zhubby.uDeck.Music', 'active': True}]
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
    windows.rows = [{'id': 'other', 'appId': 'io.github.zhubby.uDeck.Video', 'active': True}]
    windows.changed.emit(windows.rows)
    panel.open()
    controller.dispatch('back')
    assert windows.requests == [('other', 'activate')]


def test_console_dismiss_does_not_restore_an_external_application(console):
    controller, panel, windows, _application = console
    windows.rows = [{'id': 'archive', 'appId': 'xarchiver', 'active': True}]
    panel.open()
    controller.dispatch('back')
    assert windows.requests == []
    assert panel.return_target is None


@pytest.mark.parametrize('verified,expired,withdrawn,restored', [
    (False, False, False, False), (True, False, False, True),
    (True, True, False, False), (True, False, True, False),
])
def test_console_game_return_requires_verified_live_engine(tmp_path, monkeypatch, verified, expired, withdrawn, restored):
    from udeck import windows as windows_module

    process = [Identity(222, 1000)]
    monkeypatch.setattr(windows_module, 'read_process', lambda pid: SimpleNamespace(
        identity=process[0], uid=os.getuid(), state='S'))
    windows = WindowService()
    windows.available = True
    windows.handles = {'game': {'id': 'game', 'appId': 'com.libretro.RetroArch', 'proxy': 3, 'active': True}}
    requests = []
    windows.library = SimpleNamespace(wl_proxy_get_version=lambda proxy: 3,
                                     wl_proxy_marshal_flags=lambda *args: requests.append(args),
                                     wl_display_flush=lambda display: None)
    controller = ShellController(MockBackend(), windows, ConfigStore(tmp_path / 'game.json'), mock=True)
    panel = ConsolePanel(controller, windows)
    emulator = 'io.github.zhubby.uDeck.Emulator'
    controller.runtime_console.infos[emulator] = {'relatedWindows': [{'appId': 'com.libretro.RetroArch', 'pid': 222}]}
    controller.runtime_console.metrics[emulator] = {'members': [process[0]] if verified else []}
    controller.runtime_console.set_windows(windows.entries())
    try:
        panel.open()
        if expired:
            process[0] = Identity(222, 2000)
        if withdrawn:
            controller.runtime_console.infos.clear()
            controller.runtime_console._rebuild()
        controller.dispatch('back')
        assert bool(requests) is restored
    finally:
        panel.close()
        controller.close()
        windows.close()


def test_session_lock_blocks_open_and_focus_restoration(console):
    controller, panel, windows, _application = console
    panel.open()
    controller.backend.updated.emit({'sessionInput': {'available': True, 'active': True, 'locked': True}})
    controller.dispatch('back')
    panel.open()
    assert not controller.modal and not windows.requests


@pytest.mark.parametrize('language,title,labels', [
    ('en', 'Control panel', ['Back to home', 'Console', 'Settings', 'Shut down', 'Restart']),
    ('zh_CN', '控制面板', ['返回主页', '控制台', '设置', '关机', '重启']),
])
def test_console_names_change_language_while_open(console, language, title, labels):
    controller, panel, _windows, _application = console
    panel.open()
    controller.setLanguage(language)
    modal = json.loads(controller.snapshotJson)['modal']
    assert modal['title'] == title
    assert [entry['label'] for entry in modal['options']] == labels
