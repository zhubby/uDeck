"""
[INPUT]: 依赖应用输入路由、模拟器控制器与隔离的 Qt 环境。
[OUTPUT]: 验证输入归属、会话恢复与原生命令的窗口激活。
[POS]: 桌面和独立应用之间的路由回归测试。
[PROTOCOL]: Update this header on change, then check AGENTS.md
"""

from types import SimpleNamespace

import pytest
from PySide6.QtCore import QCoreApplication, QObject, Signal

from udeck.app_routing import APP_IDS
from udeck.apps.common import input as input_module
from udeck.apps.common.controller import AppController
from udeck.apps.common.input import AppInput
from udeck.apps.common.library import Source, scan
from udeck.apps.emulator.controller import EmulatorController, content_hash
from udeck.compatibility import application_profile
from udeck.terminal_routing import SuiteInputBroker


class Windows(QObject):
    changed = Signal(list)
    failed = Signal(str)


class Pointer(QObject):
    shoulder = Signal(str)


def test_suite_routes_shoulders_only_to_compositor_owner_and_invalidates_focus():
    application = QCoreApplication.instance() or QCoreApplication([])
    windows, pointer = Windows(), Pointer()
    suite = SuiteInputBroker(windows, pointer)
    sent = {identifier: [] for identifier in APP_IDS.values()}
    for identifier, broker in suite.brokers.items():
        broker.sender = lambda method, args, identifier=identifier: sent[identifier].append((method, args))
    music, reader = APP_IDS["music"], APP_IDS["reader"]
    windows.changed.emit([{"id": "1", "appId": music, "active": True}])
    pointer.shoulder.emit("next-page")
    assert sent[music][-1] == ("Shoulder", [1, "next-tab"])
    assert not sent[reader]
    windows.changed.emit([{"id": "1", "appId": music, "active": False},
                          {"id": "2", "appId": reader, "active": True}])
    pointer.shoulder.emit("previous-page")
    assert sent[music][-1] == ("Route", [2, False])
    assert sent[reader][-1] == ("Shoulder", [1, "previous-tab"])
    windows.failed.emit("compositor gone")
    assert not suite.state(reader)["enabled"]
    assert not suite.state("unrecognized.app")["available"]
    assert all(application_profile(identifier)["mode"] == "native" for identifier in APP_IDS.values())
    assert application


def test_app_input_rechecks_window_focus_and_rejects_stale_generations():
    application = QCoreApplication.instance() or QCoreApplication([])
    actions, active = [], True
    controller = QObject()
    controller.window = SimpleNamespace(isActive=lambda: active)
    controller.dispatch = actions.append
    inputs = AppInput(controller, APP_IDS["reader"], {})
    inputs.foreground = True
    inputs.route(5, True)
    inputs.shoulder(4, "next-tab")
    assert not actions
    inputs.shoulder(5, "next-tab")
    active = False
    inputs.shoulder(5, "previous-tab")
    inputs.route(6, False)
    inputs.route(5, True)
    assert actions == ["next-tab"] and not inputs.routed
    inputs.close()
    assert application


@pytest.fixture
def native_inputs(monkeypatch):
    application = QCoreApplication.instance() or QCoreApplication([])
    queries = []
    state = {'available': True, 'generation': 2, 'enabled': True}

    class Remote:
        def __init__(self, *args):
            queries.append('interface')

        def isValid(self):
            return True

        def call(self, *args):
            import json
            queries.append('state')
            return SimpleNamespace(type=lambda: input_module.QDBusMessage.MessageType.ReplyMessage,
                                   arguments=lambda: [json.dumps(state)])

    monkeypatch.setattr(input_module, 'QDBusInterface', Remote)
    controller = QObject()
    controller.window = SimpleNamespace(isActive=lambda: True)
    controller.dispatch = lambda action: None
    inputs = AppInput(controller, APP_IDS['reader'], {})
    yield inputs, queries, state
    inputs.close()
    assert application


def test_background_apps_do_not_poll_desktop_input_authorization(native_inputs):
    inputs, queries, _ = native_inputs
    inputs.sync()
    assert not inputs.timer.isActive()
    assert queries == []


def test_foreground_app_uses_broker_pushes_after_authorization(native_inputs):
    inputs, queries, state = native_inputs
    inputs.set_foreground(True)
    assert inputs.routed and queries == ['interface', 'state']
    assert not inputs.timer.isActive()
    inputs.set_foreground(False)
    inputs.sync()
    assert queries == ['interface', 'state'] and not inputs.routed


def test_input_broker_restart_invalidates_generation_without_background_queries(native_inputs):
    inputs, queries, _ = native_inputs
    inputs.set_foreground(True)
    inputs.set_foreground(False)
    inputs.watcher.serviceOwnerChanged.emit('io.github.zhubby.uDeck', ':1.1', ':1.2')
    assert inputs.generation == -1 and not inputs.routed
    assert queries == ['interface', 'state']
    inputs.set_foreground(True)
    assert inputs.generation == 2 and inputs.routed


def test_foreground_focus_race_retries_until_broker_pushes_route(native_inputs):
    inputs, _, state = native_inputs
    state['enabled'] = False
    inputs.set_foreground(True)
    assert inputs.timer.isActive() and not inputs.routed
    inputs.route(3, True)
    assert inputs.routed and not inputs.timer.isActive()


def test_standalone_fallback_retries_only_while_foreground(native_inputs, monkeypatch):
    inputs, queries, state = native_inputs
    state['available'] = False
    pointer = []
    monkeypatch.setattr(inputs.pointer, 'start', lambda: pointer.append('start'))
    inputs.set_foreground(True)
    assert pointer == ['start'] and inputs.timer.isActive()
    inputs.set_foreground(False)
    inputs.sync()
    assert not inputs.timer.isActive() and queries == ['interface', 'state']


def test_nested_menus_skip_disabled_rows_and_preserve_parent_focus_and_draft(tmp_path):
    application = QCoreApplication.instance() or QCoreApplication([])
    controller = AppController("browser", tmp_path, tmp_path / "settings.json")
    called = []
    controller.menu("Parent", [("Disabled", None), ("Child", lambda: controller.menu("Child", []))])
    controller.choose(0)
    assert len(controller.menus) == 1
    controller.choose(1)
    assert controller.menus[-1]["title"] == "Child"
    controller.dispatch("back")
    assert controller.menus[-1]["title"] == "Parent" and controller.menus[-1]["index"] == 1
    controller.prompt("Text", called.append, "abxy 中文")
    controller.set_language("zh_CN")
    assert controller.menus[-1]["draft"] == "abxy 中文"
    controller.dispatch("next-tab")
    assert controller.menus[-1]["draft"] == "abxy 中文"
    controller.submit("hello")
    assert called == ["hello"] and controller.menus[-1]["title"] == "Parent"
    controller.close()
    assert application


def test_library_refresh_retains_stable_focus_and_removed_item_selects_neighbor(tmp_path):
    application = QCoreApplication.instance() or QCoreApplication([])
    controller = AppController("reader", tmp_path, tmp_path / "settings.json")
    controller.library.items = [{"id": key, "sourceId": "card", "title": key, "format": "TXT", "folder": "/books"}
                                for key in ("a", "b", "c")]
    controller.selected = "b"
    assert controller.snapshot()["selected"] == "b"
    controller.library.items.insert(0, {**controller.library.items[0], "id": "z"})
    assert controller.snapshot()["selected"] == "b"
    controller.library.items = [i for i in controller.library.items if i["id"] != "b"]
    assert controller.snapshot()["selected"] == "c"
    controller.close()
    assert application


def test_loaded_game_resumes_and_source_loss_disables_save_and_load(tmp_path):
    application = QCoreApplication.instance() or QCoreApplication([])
    controller = EmulatorController(tmp_path, tmp_path / "settings.json")
    commands, minimized = [], []
    controller.engine.status = "paused"
    controller.engine.send = commands.append
    controller.window = SimpleNamespace(showMinimized=lambda: minimized.append(True))
    controller.menu("Confirm load", [("Confirm", lambda: None)])
    controller.load_done()
    assert commands == ["PAUSE_TOGGLE"] and minimized == [True] and not controller.menus
    controller.engine.running = lambda: True
    controller.source_missing = True
    controller.pause_menu()
    assert [row["disabled"] for row in controller.menus[-1]["options"]][:3] == [True, True, True]
    controller.engine.running = lambda: False
    controller.close()
    assert application


@pytest.mark.parametrize("operation", ["save", "load", "save-exit", "pause"])
def test_game_commands_uncover_wayland_frontend_until_confirmation(tmp_path, operation):
    application = QCoreApplication.instance() or QCoreApplication([])
    controller = EmulatorController(tmp_path, tmp_path / "settings.json")
    events = []
    controller.window = SimpleNamespace(showMinimized=lambda: events.append("uncovered"))
    controller.require_current = lambda: {}
    controller.engine.save = lambda slot: events.append(("save", slot))
    controller.engine.load = lambda slot: events.append(("load", slot))
    controller.engine.send = lambda command: events.append(command)
    try:
        if operation == "pause":
            controller.engine.status = "playing"
            controller.command("pause-game")
            assert events == ["uncovered", "PAUSE_TOGGLE"]
        elif operation == "save-exit":
            controller.save_exit()
            assert events == [("save", "auto"), "uncovered"] and controller.exit_after_save
        else:
            controller.slot_action("3", operation == "load")
            assert events == [(operation, "3"), "uncovered"]
    finally:
        controller.close()
    assert application


def test_game_pause_activates_retroarch_after_leaving_home(tmp_path, monkeypatch):
    application = QCoreApplication.instance() or QCoreApplication([])
    controller = EmulatorController(tmp_path, tmp_path / "settings.json")
    events = []

    class GameWindows:
        def start(self):
            events.append("connect")

        def entries(self):
            return [{"id": "reader", "appId": APP_IDS["reader"]},
                    {"id": "game", "appId": "com.libretro.RetroArch"}]

        def request(self, identifier, action):
            events.append((identifier, action))

        def close(self):
            events.append("disconnect")

    monkeypatch.setattr("PySide6.QtGui.QGuiApplication.platformName", lambda: "wayland")
    monkeypatch.setattr("udeck.windows.WindowService", GameWindows)
    controller.window = SimpleNamespace(showMinimized=lambda: events.append("uncovered"))
    controller.engine.status = "playing"
    controller.engine.send = events.append
    try:
        controller.command("pause-game")
        assert events == ["uncovered", "connect", ("game", "activate"), "disconnect", "PAUSE_TOGGLE"]
    finally:
        controller.close()
    assert application


def test_reconnecting_same_game_source_reenables_resume_without_starting_new_game(tmp_path):
    application = QCoreApplication.instance() or QCoreApplication([])
    card = tmp_path / "card"
    card.mkdir()
    (card / "original.gb").write_bytes(b"original fixture content")
    source = Source.create(card)
    controller = EmulatorController(tmp_path / "state", tmp_path / "settings.json")
    controller.library.sources = [source]
    controller.library.items = scan(source, "emulator")
    controller.current = controller.library.items[0]
    controller.engine.metadata = {"contentHash": content_hash(controller.current)}
    controller.engine.status = "paused"
    controller.engine.running = lambda: True
    detached = tmp_path / "detached"
    card.rename(detached)
    controller.library.check_sources()
    assert controller.source_missing and controller.menus[-1]["options"][0]["disabled"]
    detached.rename(card)
    controller.poll()
    assert not controller.source_missing and not controller.menus[-1]["options"][0]["disabled"]
    assert controller.engine.status == "paused"
    controller.engine.running = lambda: False
    controller.close()
    assert application
