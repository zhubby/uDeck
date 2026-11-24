"""
[INPUT]: 依赖真实窗口服务和 Wayland 协议替身。
[OUTPUT]: 验证窗口监听生命周期、激活确认与原生激活边界。
[POS]: 合成器控制边界回归；不连接真实会话。
[PROTOCOL]: Update this header on change, then check AGENTS.md
"""

from types import SimpleNamespace

import pytest

from udeck import windows as windows_module
from udeck.runtime_console.processes import Identity
from udeck.windows import WindowService


def test_wayland_callbacks_are_owned_by_proxy_and_released_on_close():
    windows = WindowService()
    windows.library = SimpleNamespace(wl_proxy_add_listener=lambda *arguments: 0)
    windows._listen(123, [((), lambda proxy: None)])
    assert 123 in windows.listeners
    assert windows.retained == []
    windows.close()
    assert windows.listeners == {}


@pytest.fixture
def controlled_windows(monkeypatch):
    monkeypatch.setattr(windows_module, 'read_process', lambda pid: SimpleNamespace(
        identity=Identity(pid, 1000), uid=windows_module.os.getuid(), state='S'), raising=False)
    windows = WindowService()
    sent = []
    windows.available = True
    windows.library = SimpleNamespace(
        wl_proxy_get_version=lambda proxy: 3,
        wl_proxy_marshal_flags=lambda *arguments: sent.append(arguments),
        wl_display_flush=lambda display: None,
    )
    windows.handles = {
        'external': {'id': 'external', 'appId': 'xarchiver', 'proxy': 1},
        'native': {'id': 'native', 'appId': 'io.github.zhubby.uDeck.Music', 'proxy': 2},
        'shell': {'id': 'shell', 'appId': 'io.github.zhubby.uDeck', 'proxy': 3},
        'dialog': {'id': 'dialog', 'appId': '', 'parentId': 'native', 'proxy': 4},
        'game': {'id': 'game', 'appId': 'com.libretro.RetroArch', 'proxy': 5},
    }
    return windows, sent


@pytest.mark.parametrize('identifier', ['external', 'game'])
def test_activation_rejects_external_and_unmanaged_engine_windows(controlled_windows, identifier):
    windows, sent = controlled_windows
    with pytest.raises(RuntimeError):
        windows.request(identifier, 'activate')
    assert sent == []


@pytest.mark.parametrize('identifier', ['native', 'shell', 'dialog'])
def test_activation_keeps_native_windows_and_owned_dialogs(controlled_windows, identifier):
    windows, sent = controlled_windows
    windows.request(identifier, 'activate')
    assert sent[0][1] == 4


def test_external_close_does_not_activate_the_application(controlled_windows):
    windows, sent = controlled_windows
    windows.request('external', 'close')
    assert sent[0][1] == 5


def test_managed_engine_authorization_cannot_follow_a_reused_window(controlled_windows):
    windows, sent = controlled_windows
    authorize = getattr(windows, 'allow_managed_window', None)
    assert callable(authorize)
    assert not authorize('external', 'io.github.zhubby.uDeck.Emulator', 222)
    assert authorize('game', 'io.github.zhubby.uDeck.Emulator', 222)
    windows.request('game', 'activate')
    windows.handles['game'] = {**windows.handles['game'], 'proxy': 6}
    with pytest.raises(RuntimeError):
        windows.request('game', 'activate')
    assert len(sent) == 1


def test_managed_engine_authorization_expires_when_process_identity_changes(controlled_windows, monkeypatch):
    windows, sent = controlled_windows
    assert windows.allow_managed_window('game', 'io.github.zhubby.uDeck.Emulator', 222)
    monkeypatch.setattr(windows_module, 'read_process', lambda pid: SimpleNamespace(
        identity=Identity(pid, 2000), uid=windows_module.os.getuid(), state='S'), raising=False)
    with pytest.raises(RuntimeError):
        windows.request('game', 'activate')
    assert sent == []


def test_managed_engine_authorization_rejects_a_missing_process(controlled_windows, monkeypatch):
    windows, _sent = controlled_windows
    def missing(pid):
        raise ProcessLookupError(pid)
    monkeypatch.setattr(windows_module, 'read_process', missing, raising=False)
    assert not windows.allow_managed_window('game', 'io.github.zhubby.uDeck.Emulator', 222)


def test_confirmed_activation_waits_for_compositor_before_releasing_connection(controlled_windows):
    windows, sent = controlled_windows
    acknowledged = []
    windows.display = 100

    def roundtrip(display):
        assert display == 100 and sent[0][1] == 4
        acknowledged.append('activation-consumed')
        windows.handles['game']['active'] = True
        return 0

    windows.library.wl_display_roundtrip = roundtrip
    assert windows.allow_managed_window('game', 'io.github.zhubby.uDeck.Emulator', 222)
    assert windows.activate_confirmed('game')
    assert acknowledged == ['activation-consumed']


def test_confirmed_activation_does_not_accept_an_inactive_window(controlled_windows):
    windows, _sent = controlled_windows
    windows.display = 100
    windows.library.wl_display_roundtrip = lambda display: 0
    assert not windows.activate_confirmed('native')


def test_confirmed_activation_revalidates_the_managed_window_after_acknowledgment(controlled_windows):
    windows, _sent = controlled_windows
    windows.display = 100

    def replace_window(display):
        windows.handles['game'] = {**windows.handles['game'], 'proxy': 10, 'active': True}
        return 0

    windows.library.wl_display_roundtrip = replace_window
    assert windows.allow_managed_window('game', 'io.github.zhubby.uDeck.Emulator', 222)
    assert not windows.activate_confirmed('game')


def test_confirmed_activation_reports_a_failed_protocol_roundtrip(controlled_windows):
    windows, _sent = controlled_windows
    disconnected = []
    windows.display = 100
    windows.library.wl_display_roundtrip = lambda display: -1
    windows.library.wl_display_disconnect = disconnected.append
    with pytest.raises(RuntimeError):
        windows.activate_confirmed('native')
    assert disconnected == [100] and not windows.available
