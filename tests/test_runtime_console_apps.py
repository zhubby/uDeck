"""
[INPUT]: 依赖真实应用控制器及其 D-Bus 适配层。
[OUTPUT]: 验证轻量状态读取和不新增即时存档的有序退出。
[POS]: Console 与原生应用之间的生命周期契约回归。
[PROTOCOL]: Update this header on change, then check AGENTS.md
"""

import json
import time
from types import SimpleNamespace

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
