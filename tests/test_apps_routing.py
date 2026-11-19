"""
[INPUT]: 依赖应用输入路由、模拟器控制器与隔离的 Qt 环境。
[OUTPUT]: 验证交接显示、到期队列、断线回退与原生窗口激活。
[POS]: 桌面和独立应用之间的路由回归测试。
[PROTOCOL]: Update this header on change, then check AGENTS.md
"""

import os
import sys
from types import SimpleNamespace
from uuid import uuid4

import pytest
from PySide6.QtCore import QCoreApplication, QEventLoop, QObject, QTimer, Signal
from PySide6.QtDBus import QDBusConnection, QDBusError, QDBusPendingCall, QDBusPendingCallWatcher
from PySide6.QtGui import QWindow

from udeck import input as gamepad_module
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


def test_disconnected_desktop_connection_still_presents_the_application():
    from udeck.apps.runtime import present_after_input_handoff

    application = QCoreApplication.instance() or QCoreApplication([])
    name = 'udeck-handoff-disconnected-' + uuid4().hex
    connection = QDBusConnection.connectToBus('unix:path=/nonexistent/' + name, name)
    assert not connection.isConnected()
    events, parent = [], QObject()
    try:
        present_after_input_handoff(connection, APP_IDS['music'], parent,
            lambda: events.append('present'), prepare=lambda _ready: events.append('prepare'))
        loop = QEventLoop()
        QTimer.singleShot(100, loop.quit)
        loop.exec()
        assert events == ['present']
    finally:
        QDBusConnection.disconnectFromBus(name)
    assert application


def test_immediately_completed_handoff_presents_once_when_finished_also_arrives():
    from udeck.apps.runtime import present_after_input_handoff

    application = QCoreApplication.instance() or QCoreApplication([])
    pending = QDBusPendingCall.fromError(QDBusError(QDBusError.ErrorType.Disconnected, 'Desktop unavailable'))
    events, parent = [], QObject()

    def prepare(ready):
        events.append('prepare')
        ready()

    present_after_input_handoff(SimpleNamespace(asyncCall=lambda *_arguments: pending), APP_IDS['music'],
                               parent, lambda: events.append('present'), prepare=prepare)
    watcher = parent.findChild(QDBusPendingCallWatcher)
    watcher.finished[QDBusPendingCallWatcher].emit(watcher)
    loop = QEventLoop()
    QTimer.singleShot(100, loop.quit)
    loop.exec()
    assert events == ['present']
    assert application


@pytest.mark.parametrize('accepted', [True, False])
def test_app_presentation_waits_for_desktop_input_release(monkeypatch, accepted):
    from udeck.apps import runtime

    application = QCoreApplication.instance() or QCoreApplication([])
    events, watchers = [], []

    class Watcher(QObject):
        finished = Signal(object)

        def __init__(self, pending, parent):
            super().__init__(parent)
            watchers.append(self)

        def isError(self):
            return False

        def isFinished(self):
            return False

        def reply(self):
            return SimpleNamespace(arguments=lambda: [accepted])

    def send(message, timeout):
        events.append((message.member(), message.arguments(), timeout))
        return object()

    monkeypatch.setattr(runtime, 'QDBusPendingCallWatcher', Watcher)
    parent = QObject()
    runtime.present_after_input_handoff(SimpleNamespace(asyncCall=send), APP_IDS['music'], parent,
        lambda: events.append('present'), prepare=lambda ready: events.append(('prepare', ready)))
    assert events == [('PrepareNativeApp', [APP_IDS['music']], 1000)]
    watchers[0].finished.emit(watchers[0])
    if accepted:
        assert len(events) == 2 and events[1][0] == 'prepare'
        events[1][1]()
    assert events[-1] == 'present'
    assert application


def test_desktop_prepares_native_input_through_the_application_router():
    from udeck.main import Control

    application = QCoreApplication.instance() or QCoreApplication([])
    prepared = []
    control = Control(SimpleNamespace(), None)
    control.application_router = SimpleNamespace(prepare_native_activation=lambda aid: prepared.append(aid) or True)
    assert control.PrepareNativeApp(APP_IDS['music'])
    assert prepared == [APP_IDS['music']]
    control.application_router = None
    assert not control.PrepareNativeApp(APP_IDS['music'])
    assert application


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


@pytest.fixture
def prepared_gamepad(monkeypatch, tmp_path):
    application = QCoreApplication.instance()
    quit_on_close = application.quitOnLastWindowClosed()
    application.setQuitOnLastWindowClosed(False)
    actions, devices = [], []

    class Device:
        name, uniq, path = 'ClockworkPI uConsole', '20230713', '/dev/input/event7'
        info = SimpleNamespace(vendor=0x1eaf, product=0x24)

        def __init__(self, _path):
            self.fd, self.writer = os.pipe()
            os.set_blocking(self.fd, False)
            self.events, self.closed = [], False
            devices.append(self)

        def capabilities(self):
            return {1: [288, 289, 290, 291]}

        def active_keys(self):
            return []

        def grab(self):
            pass

        def ungrab(self):
            pass

        def read(self):
            os.read(self.fd, 4096)
            events, self.events = self.events, []
            return events

        def close(self):
            if not self.closed:
                self.closed = True
                os.close(self.fd)
                os.close(self.writer)

    class Remote:
        def __init__(self, *_arguments):
            pass

        def isValid(self):
            return True

        def call(self, *_arguments):
            import json
            return SimpleNamespace(type=lambda: input_module.QDBusMessage.MessageType.ReplyMessage,
                arguments=lambda: [json.dumps({'available': True, 'generation': 1, 'enabled': True})])

    monkeypatch.setattr(gamepad_module, 'sys', SimpleNamespace(platform='linux'))
    monkeypatch.setattr(input_module, 'QDBusInterface', Remote)
    monkeypatch.setitem(sys.modules, 'evdev', SimpleNamespace(InputDevice=Device,
        list_devices=lambda: ['/dev/input/event7'],
        ecodes=SimpleNamespace(EV_KEY=1, EV_SYN=0, EV_ABS=3, SYN_DROPPED=3, BTN_MISC=256)))
    controller, window = QObject(), QWindow()
    controller.window, controller.dispatch = window, actions.append
    inputs = AppInput(controller, APP_IDS['reader'], {})
    inputs.gamepad.sysfs_root = tmp_path

    def pump():
        loop = QEventLoop()
        QTimer.singleShot(20, loop.quit)
        loop.exec()

    def activate():
        window.show()
        window.requestActivate()
        application.processEvents()
        assert window.isActive()

    def back():
        for value in (1, 0):
            device = inputs.gamepad.device
            device.events.append(SimpleNamespace(type=1, code=290, value=value))
            os.write(device.writer, b'x')

    yield SimpleNamespace(inputs=inputs, window=window, actions=actions, devices=devices,
                          activate=activate, back=back, pump=pump)
    inputs.close()
    window.close()
    application.setQuitOnLastWindowClosed(quit_on_close)


@pytest.mark.parametrize('queued_focus_signal', [False, True])
def test_expiring_preparation_keeps_queued_back_for_focus_in_the_same_event_turn(prepared_gamepad, queued_focus_signal):
    context, inputs = prepared_gamepad, prepared_gamepad.inputs
    inputs.prepare_foreground(lambda: None)
    context.pump()
    device = inputs.gamepad.device
    context.back()
    context.activate()
    assert not inputs.foreground
    if queued_focus_signal:
        QTimer.singleShot(0, lambda: inputs.set_foreground(True))
    inputs._expire_preparation()
    assert inputs.gamepad.device is device
    context.pump()
    assert inputs.foreground and inputs.gamepad.grabbed
    assert context.actions == ['back'] and not inputs.preparation.isActive()


def test_unfocused_preparation_releases_after_one_turn_and_never_replays_old_back(prepared_gamepad):
    context, inputs = prepared_gamepad, prepared_gamepad.inputs
    inputs.prepare_foreground(lambda: None)
    context.pump()
    device = inputs.gamepad.device
    context.back()
    inputs._expire_preparation()
    assert inputs.gamepad.device is device
    context.pump()
    assert device.closed and inputs.gamepad.device is None and not context.actions
    context.activate()
    inputs.set_foreground(True)
    context.pump()
    assert inputs.gamepad.device is not device and context.actions == []


def test_unfocused_preparation_releases_without_renewing_its_lease(prepared_gamepad):
    inputs = prepared_gamepad.inputs
    inputs.prepare_foreground(lambda: None)
    ownership = []
    loop = QEventLoop()
    QTimer.singleShot(400, lambda: ownership.append(inputs.gamepad.grabbed))
    QTimer.singleShot(1500, loop.quit)
    loop.exec()
    assert ownership == [True]
    assert inputs.gamepad.device is None and not inputs.preparation.isActive()


@pytest.mark.parametrize('superseded_by', ['close', 'prepare'])
def test_deferred_preparation_release_cannot_outlive_its_generation(prepared_gamepad, superseded_by):
    context, inputs = prepared_gamepad, prepared_gamepad.inputs
    inputs.prepare_foreground(lambda: None)
    context.pump()
    inputs._expire_preparation()
    if superseded_by == 'close':
        inputs.close()
        context.activate()
        inputs.set_foreground(True)
        context.pump()
        assert inputs.gamepad.device is None and not inputs.gamepad.foreground
    else:
        presented = []
        inputs.prepare_foreground(lambda: presented.append('new'))
        context.pump()
        assert inputs.gamepad.grabbed and inputs.preparation.isActive()
        assert presented == ['new']


def test_background_apps_do_not_poll_desktop_input_authorization(native_inputs):
    inputs, queries, _ = native_inputs
    inputs.sync()
    assert not inputs.timer.isActive()
    assert queries == []


def test_prepared_input_expires_without_focus_and_remains_after_confirmed_focus(native_inputs):
    inputs, _, _ = native_inputs
    inputs.controller.window = SimpleNamespace(isActive=lambda: False)
    inputs.gamepad = SimpleNamespace(foreground=False, grabbed=False, device=object(), close=lambda: None)
    inputs.gamepad.set_foreground = lambda active: setattr(inputs.gamepad, 'foreground', active)
    inputs.gamepad.set_delivery_enabled = lambda active: setattr(inputs.gamepad, 'delivery_enabled', active)
    inputs.prepare_foreground()
    assert inputs.gamepad.foreground and not inputs.foreground
    assert not inputs.gamepad.delivery_enabled
    assert inputs.preparation.isActive()
    inputs._expire_preparation()
    QCoreApplication.processEvents()
    assert not inputs.gamepad.foreground
    inputs.prepare_foreground()
    inputs.set_foreground(True)
    assert not inputs.preparation.isActive()
    assert inputs.gamepad.delivery_enabled
    inputs._expire_preparation()
    assert inputs.gamepad.foreground


def test_prepared_window_waits_for_acquisition_and_timeout_falls_back_once(native_inputs):
    inputs, _, _ = native_inputs
    inputs.controller.window = SimpleNamespace(isActive=lambda: False)
    inputs.gamepad = SimpleNamespace(foreground=False, grabbed=False, device=object(), close=lambda: None)
    inputs.gamepad.set_foreground = lambda active: setattr(inputs.gamepad, 'foreground', active)
    inputs.gamepad.set_delivery_enabled = lambda active: setattr(inputs.gamepad, 'delivery_enabled', active)
    presented = []
    inputs.prepare_foreground(lambda: presented.append('ready'))
    assert inputs.gamepad.foreground and presented == []
    inputs._gamepad_status({'grabbed': True})
    QCoreApplication.processEvents()
    assert presented == ['ready']
    inputs._expire_preparation()
    QCoreApplication.processEvents()
    assert presented == ['ready'] and not inputs.gamepad.foreground

    inputs.prepare_foreground(lambda: presented.append('fallback'))
    inputs._expire_preparation()
    QCoreApplication.processEvents()
    QCoreApplication.processEvents()
    assert presented == ['ready', 'fallback'] and not inputs.gamepad.foreground


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


def test_library_back_requests_home_without_racing_window_minimization(tmp_path, monkeypatch):
    from udeck.apps.common import controller as controller_module

    application = QCoreApplication.instance() or QCoreApplication([])
    controller = AppController("browser", tmp_path, tmp_path / "settings.json")
    requests, minimized = [], []
    connection = SimpleNamespace(asyncCall=lambda message: requests.append(message.member()))
    monkeypatch.setattr(controller_module, "QDBusConnection", SimpleNamespace(sessionBus=lambda: connection))
    controller.window = SimpleNamespace(showMinimized=lambda: minimized.append(True))
    try:
        controller.back()
        assert requests == ["Home"]
        assert not minimized and not controller._closed
    finally:
        controller.window = None
        controller.close()
    assert application


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
