"""
[INPUT]: 依赖真实应用控制器及其 D-Bus 适配层。
[OUTPUT]: 验证轻量状态、受控引擎激活确认与有序退出。
[POS]: Console 与原生应用之间的生命周期契约回归。
[PROTOCOL]: Update this header on change, then check AGENTS.md
"""

import json
import time
from types import SimpleNamespace

import pytest

from udeck.apps.common.controller import AppController
from udeck.apps.emulator.controller import EmulatorController
from udeck.apps.main import AppControl
from udeck.terminal.controller import TerminalController
from udeck.terminal.core import LaunchRequest, TerminalPreferences
from udeck.terminal.runtime import Coordinator


def test_runtime_info_does_not_serialize_the_full_app_snapshot(tmp_path):
    controller = AppController("music", tmp_path, tmp_path / "settings.json")
    control = AppControl(controller, lambda: None, [], time.monotonic())
    try:
        info = json.loads(control.RuntimeInfo())
        assert info["state"] == "running" and info["relatedWindows"] == []
        assert "items" not in info and "state" not in info.get("state", {})
    finally:
        controller.close()


def test_quit_request_persists_the_application_before_closing(tmp_path):
    controller = AppController("music", tmp_path, tmp_path / "settings.json")
    events = []
    controller.persist = lambda: events.append("persist")
    controller.closed.connect(lambda: events.append("closed"))
    control = AppControl(controller, lambda: None, [], time.monotonic())
    try:
        assert control.RequestQuit() == ""
        assert events == ["persist", "closed"]
    finally:
        controller.close()


def test_emulator_normal_quit_waits_for_game_exit_without_creating_a_savestate(tmp_path):
    controller = EmulatorController(tmp_path, tmp_path / "settings.json")
    running = [True]
    events = []
    controller.engine.running = lambda: running[0]
    controller.engine.quit = lambda: events.append("quit")
    controller.engine.save = lambda *args: events.append("save")
    controller.uncover_game = lambda: events.append("uncover")
    controller.record_exited_sram = lambda code: events.append("sram")
    controller.persist = lambda: events.append("persist")
    controller.closed.connect(lambda: events.append("closed"))
    try:
        controller.requestQuit()
        assert events == ["quit", "uncover"]
        running[0] = False
        controller.game_exited(0)
        assert "save" not in events
        assert events.index("sram") < events.index("closed")
    finally:
        running[0] = False
        controller.close()


def test_emulator_failed_normal_exit_keeps_the_frontend_open(tmp_path):
    controller = EmulatorController(tmp_path, tmp_path / "settings.json")
    events = []
    controller.engine.running = lambda: True
    controller.engine.quit = lambda: None
    controller.uncover_game = lambda: None
    controller.record_exited_sram = lambda code: None
    controller.closed.connect(lambda: events.append("closed"))
    try:
        controller.requestQuit()
        controller.engine.running = lambda: False
        controller.game_exited(15)
        assert not events and controller.error
    finally:
        controller.engine.running = lambda: False
        controller.close()


def test_emulator_persistence_failure_after_game_exit_restores_the_frontend(tmp_path):
    controller = EmulatorController(tmp_path, tmp_path / "settings.json")
    events = []
    controller.engine.running = lambda: False
    controller.quit_application = True
    controller.record_exited_sram = lambda code: None
    def fail_persist():
        raise OSError("state disk is read-only")
    controller.persist = fail_persist
    controller.closed.connect(lambda: events.append("closed"))
    controller.present.connect(lambda: events.append("present"))
    try:
        controller.game_exited(0)
        assert events == ["present"] and "read-only" in str(controller.error)
    finally:
        controller.close()


def test_terminal_app_quit_preserves_each_windows_existing_confirmation(tmp_path):
    controllers = [TerminalController(LaunchRequest(str(tmp_path), [], "", {}),
                                      TerminalPreferences(tmp_path / f"terminal-{index}.json"), mock=True)
                   for index in range(2)]
    operations, activated = [], []
    windows = [{"controller": controller, "window": index} for index, controller in enumerate(controllers)]
    for controller in controllers:
        controller.operate.connect(lambda *args: operations.append(args))
    coordinator = SimpleNamespace(windows=windows, recent=windows[1], activate=activated.append)
    Coordinator.request_quit(coordinator)
    assert [controller.mode for controller in controllers] == ["close", "close"]
    assert not operations and activated == [1]
    for controller in controllers:
        controller.dispatch("accept")
    assert not operations and all(controller.tabs.rowCount() == 1 for controller in controllers)


@pytest.mark.parametrize('running,pid,authorized,expected', [
    (False, 0, False, False), (True, 0, False, False),
    (True, 222, True, True), (True, 222, False, False),
])
def test_emulator_uncover_requires_its_running_engine_identity(monkeypatch, running, pid, authorized, expected):
    from udeck import windows as windows_module
    from udeck.apps.emulator import controller as emulator_module

    events = []
    minimized = []
    class Windows:
        def start(self):
            pass
        def entries(self):
            return [{'id': 'game', 'appId': 'com.libretro.RetroArch'}]
        def allow_managed_window(self, identifier, owner, process_id):
            events.append(('authorize', identifier, owner, process_id))
            return authorized
        def request(self, *args):
            events.append(('activate', *args))
        def activate_confirmed(self, identifier):
            self.request(identifier, 'activate')
            return True
        def close(self):
            pass

    monkeypatch.setattr(windows_module, 'WindowService', Windows)
    monkeypatch.setattr(emulator_module, 'QGuiApplication', SimpleNamespace(platformName=lambda: 'wayland'))
    target = SimpleNamespace(window=SimpleNamespace(showMinimized=lambda: minimized.append(True)), isolated=False,
                             present=SimpleNamespace(emit=lambda: events.append(('present',))),
                             engine=SimpleNamespace(running=lambda: running,
                                                    process=SimpleNamespace(processId=lambda: pid)))
    if running and pid > 0 and not authorized:
        with pytest.raises(RuntimeError):
            EmulatorController.uncover_game(target)
        assert events[-1] == ('present',)
    else:
        EmulatorController.uncover_game(target)
    assert any(event[0] == 'activate' for event in events) is expected
    assert bool(minimized) is expected
    if expected:
        assert events == [('authorize', 'game', 'io.github.zhubby.uDeck.Emulator', 222),
                          ('activate', 'game', 'activate')]


@pytest.mark.parametrize('protocol_error', [False, True])
def test_emulator_keeps_frontend_available_when_activation_is_not_confirmed(monkeypatch, protocol_error):
    from udeck import windows as windows_module
    from udeck.apps.emulator import controller as emulator_module

    events = []

    class Windows:
        def start(self):
            pass
        def entries(self):
            return [{'id': 'game', 'appId': 'com.libretro.RetroArch'}]
        def allow_managed_window(self, *args):
            return True
        def activate_confirmed(self, identifier):
            events.append('confirm')
            if protocol_error:
                raise RuntimeError('compositor disconnected')
            return False
        def close(self):
            events.append('closed')

    monkeypatch.setattr(windows_module, 'WindowService', Windows)
    monkeypatch.setattr(emulator_module, 'QGuiApplication', SimpleNamespace(platformName=lambda: 'wayland'))
    target = SimpleNamespace(window=SimpleNamespace(showMinimized=lambda: events.append('minimized')),
                             present=SimpleNamespace(emit=lambda: events.append('present')),
                             isolated=False, engine=SimpleNamespace(running=lambda: True,
                             process=SimpleNamespace(processId=lambda: 222)))
    with pytest.raises(RuntimeError):
        EmulatorController.uncover_game(target)
    assert 'minimized' not in events
    assert events == ['confirm', 'present', 'closed']
