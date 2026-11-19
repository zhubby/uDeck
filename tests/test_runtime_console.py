"""
[INPUT]: 依赖真实 Console 服务、Qt 模型和桌面控制器。
[OUTPUT]: 验证所有者变化去重、实时详情和身份固定的退出。
[POS]: Console 的异步服务与桌面导航集成回归。
[PROTOCOL]: Update this header on change, then check AGENTS.md
"""

import json
from concurrent.futures import Future
from types import SimpleNamespace

import pytest

from udeck.controller import ShellController
from udeck.core import ConfigStore
from udeck.mock import MockBackend
from udeck.runtime_console.model import ConsoleModel
from udeck.runtime_console.processes import Identity, Process, Snapshot
from udeck.runtime_console.service import RuntimeConsole


def window(identifier, app, **values):
    return {"id": identifier, "appId": app, "name": app, "icon": app, "active": False, **values}


def test_mock_console_never_connects_to_session_bus(monkeypatch):
    from udeck.runtime_console import service

    def unexpected_connection():
        raise AssertionError("mock Console must not connect to the live session")

    monkeypatch.setattr(service.QDBusConnection, "sessionBus", unexpected_connection)
    console = RuntimeConsole(mock=True)
    try:
        console.set_windows([window("a", "terminal")])
        console.set_visible(True)
        assert len(console.model.rows) == 1
    finally:
        console.close()


def test_owner_discovery_reconciles_cached_owner_and_ignores_hidden_reply(monkeypatch):
    from udeck.runtime_console import service

    monkeypatch.setattr(service.QDBusConnection, "sessionBus", lambda: None)
    console = RuntimeConsole()
    app = "io.github.zhubby.uDeck.Emulator"
    console._services = {app: app}
    console.owners[app] = ":1.10"
    console.visible = True
    calls = []
    monkeypatch.setattr(console, "_call", lambda *args: calls.append(args))
    polled = []
    monkeypatch.setattr(console, "_poll_info", lambda app: polled.append(app))

    def reply(owner="", error=""):
        return SimpleNamespace(arguments=lambda: [owner] if owner else [],
                               type=lambda: service.QDBusMessage.MessageType.ErrorMessage if error else service.QDBusMessage.MessageType.ReplyMessage,
                               errorName=lambda: error)

    try:
        console._discover()
        assert calls[0][-3] == "GetNameOwner"
        calls.pop()[-1](reply(":1.10"))
        assert polled == [app]
        console._discover()
        calls.pop()[-1](reply(":1.11"))
        assert console.owners[app] == ":1.11"
        console._discover()
        callback = calls.pop()[-1]
        console.set_visible(False)
        callback(reply(error="org.freedesktop.DBus.Error.NameHasNoOwner"))
        assert console.owners[app] == ":1.11"
        console.visible = True
        console._discover()
        calls.pop()[-1](reply(error="org.freedesktop.DBus.Error.NameHasNoOwner"))
        assert app not in console.owners
    finally:
        console.close()


def test_owner_discovery_publishes_only_real_owner_transitions(monkeypatch):
    from udeck.runtime_console import service

    monkeypatch.setattr(service.QDBusConnection, "sessionBus", lambda: None)
    console = RuntimeConsole()
    app = "io.github.zhubby.uDeck.Emulator"
    console._services = {app: app}
    console.visible = True
    calls, summaries = [], []
    monkeypatch.setattr(console, "_call", lambda *args: calls.append(args))
    console.summaryChanged.connect(lambda: summaries.append(console.summary["count"]))

    def discover(owner=""):
        console._discover()
        reply = SimpleNamespace(arguments=lambda: [owner] if owner else [],
                                type=lambda: service.QDBusMessage.MessageType.ReplyMessage if owner else service.QDBusMessage.MessageType.ErrorMessage,
                                errorName=lambda: "" if owner else "org.freedesktop.DBus.Error.NameHasNoOwner")
        calls.pop()[-1](reply)

    try:
        for _ in range(3):
            discover()
        assert summaries == []
        assert console.model.rows == []

        discover(":1.10")
        assert console.owners[app] == ":1.10"
        assert console.row(app)["applicationKey"] == app
        assert summaries == [1]

        discover(":1.11")
        assert console.owners[app] == ":1.11"
        assert summaries == [1, 1]

        discover()
        assert app not in console.owners and console.row(app) is None
        assert summaries == [1, 1, 0]
        for _ in range(3):
            discover()
        assert summaries == [1, 1, 0]
    finally:
        console.close()


def test_failed_pid_query_waits_for_next_refresh_before_retrying(monkeypatch):
    from udeck.runtime_console import service

    monkeypatch.setattr(service.QDBusConnection, "sessionBus", lambda: None)
    console = RuntimeConsole()
    app, owner = "io.github.zhubby.uDeck.Emulator", ":1.10"
    console.owners[app] = owner
    console.visible = True
    calls = []
    monkeypatch.setattr(console, "_call", lambda *args: calls.append(args))
    failed = SimpleNamespace(arguments=lambda: [], type=lambda: service.QDBusMessage.MessageType.ErrorMessage)
    try:
        console._resolve_pid(app, owner)
        assert len(calls) == 1
        calls[0][-1](failed)
        assert len(calls) == 1
        assert app not in console.pids
        console._poll_info(app)
        assert len(calls) == 2
    finally:
        console.close()


def test_unchanged_application_info_does_not_republish_console_summary(monkeypatch):
    from udeck.runtime_console import service

    monkeypatch.setattr(service.QDBusConnection, "sessionBus", lambda: None)
    console = RuntimeConsole()
    app = "io.github.zhubby.uDeck.Emulator"
    console.owners[app], console.pids[app], console.visible = ":1.10", 101, True
    callbacks, summaries = [], []
    monkeypatch.setattr(console, "_call", lambda *args: callbacks.append(args[-1]))
    console.summaryChanged.connect(lambda: summaries.append(True))
    reply = SimpleNamespace(arguments=lambda: ['{"state":"paused","relatedWindows":[]}'],
                            type=lambda: service.QDBusMessage.MessageType.ReplyMessage)
    try:
        console._poll_info(app)
        callbacks.pop()(reply)
        assert console.row(app)["runtimeState"] == "paused"
        assert summaries == [True]
        console._poll_info(app)
        callbacks.pop()(reply)
        assert summaries == [True]
    finally:
        console.close()


@pytest.mark.parametrize("reopened", [False, True])
def test_application_info_from_previous_visibility_cannot_change_current_state(monkeypatch, reopened):
    from udeck.runtime_console import service

    monkeypatch.setattr(service.QDBusConnection, "sessionBus", lambda: None)
    console = RuntimeConsole()
    app = "io.github.zhubby.uDeck.Emulator"
    console.owners[app], console.pids[app], console.visible = ":1.10", 101, True
    callbacks = []
    monkeypatch.setattr(console, "_call", lambda *args: callbacks.append(args[-1]))
    reply = SimpleNamespace(arguments=lambda: ['{"state":"paused","relatedWindows":[]}'],
                            type=lambda: service.QDBusMessage.MessageType.ReplyMessage)
    try:
        console._poll_info(app)
        stale = callbacks.pop()
        console.set_visible(False)
        if reopened:
            monkeypatch.setattr(console, "refresh", lambda: None)
            console.set_visible(True)
        stale(reply)
        assert app not in console.infos
    finally:
        console.close()


@pytest.mark.parametrize("unsupported", [False, True])
def test_native_quit_uses_lifecycle_method_before_runtime_info_arrives(monkeypatch, unsupported):
    from udeck.runtime_console import service

    monkeypatch.setattr(service.QDBusConnection, "sessionBus", lambda: None)
    console = RuntimeConsole()
    app = "io.github.zhubby.uDeck.Emulator"
    console.set_windows([window("game-library", app)])
    console.owners[app] = ":1.10"
    console._rebuild()
    calls, closed = [], []
    monkeypatch.setattr(console, "_call", lambda *args: calls.append(args))
    windows = SimpleNamespace(entries=lambda: console.windows, request=lambda *args: closed.append(args))
    reply = SimpleNamespace(arguments=lambda: [] if unsupported else [""],
                            type=lambda: service.QDBusMessage.MessageType.ErrorMessage if unsupported else service.QDBusMessage.MessageType.ReplyMessage,
                            errorName=lambda: "org.freedesktop.DBus.Error.UnknownMethod" if unsupported else "")
    try:
        console.quit(console.target(app), windows)
        assert calls and calls[0][-3] == "RequestQuit"
        assert closed == []
        calls[0][-1](reply)
        assert closed == ([("game-library", "close")] if unsupported else [])
    finally:
        console.close()


def test_native_quit_waits_until_owner_is_discovered(monkeypatch):
    from udeck.runtime_console import service

    monkeypatch.setattr(service.QDBusConnection, "sessionBus", lambda: None)
    console = RuntimeConsole()
    app = "io.github.zhubby.uDeck.Emulator"
    try:
        console.set_windows([window("game-library", app)])
        assert not console.row(app)["canQuit"]
        console.owners[app] = ":1.10"
        console._rebuild()
        assert console.row(app)["canQuit"]
    finally:
        console.close()


@pytest.mark.parametrize("changed_target", [False, True])
def test_failed_native_quit_never_closes_a_changed_target_or_falls_back_on_timeout(monkeypatch, changed_target):
    from udeck.runtime_console import service

    monkeypatch.setattr(service.QDBusConnection, "sessionBus", lambda: None)
    console = RuntimeConsole()
    app = "io.github.zhubby.uDeck.Emulator"
    console.set_windows([window("game-library", app)])
    console.owners[app] = ":1.10"
    console._rebuild()
    calls, closed, errors = [], [], []
    monkeypatch.setattr(console, "_call", lambda *args: calls.append(args))
    console.failed.connect(errors.append)
    windows = SimpleNamespace(entries=lambda: console.windows, request=lambda *args: closed.append(args))
    reply = SimpleNamespace(arguments=lambda: [], type=lambda: service.QDBusMessage.MessageType.ErrorMessage,
                            errorName=lambda: "org.freedesktop.DBus.Error.UnknownMethod" if changed_target else "org.freedesktop.DBus.Error.NoReply",
                            errorMessage=lambda: "Quit request timed out")
    try:
        console.quit(console.target(app), windows)
        if changed_target:
            console.set_windows([window("replacement", app)])
        calls[0][-1](reply)
        assert closed == [] and errors
        assert app not in console.exiting
    finally:
        console.close()


@pytest.fixture
def shell(tmp_path):
    controller = ShellController(MockBackend(), config=ConfigStore(tmp_path / "settings.json"), mock=True)
    controller._windows_changed([window("a", "terminal"), window("b", "browser"), window("c", "emulator")])
    controller.setPage("windows")
    yield controller
    controller.close()


def test_windows_of_the_same_application_share_one_row(shell):
    shell._windows_changed([window("a", "terminal"), window("b", "terminal"), window("c", "browser")])
    assert [item["id"] for item in shell._items()] == ["terminal", "browser"]
    assert len(shell.runtime_console.row("terminal")["windows"]) == 2


def test_selection_stays_on_application_when_a_row_above_exits(shell):
    shell.select(1)
    shell._windows_changed([window("c", "emulator"), window("b", "browser")])
    assert shell.navigation.index == 0
    assert shell._items()[0]["id"] == "browser"
    assert [item["id"] for item in shell._items()] == ["browser", "emulator"]


def test_exit_button_ends_only_the_selected_application_and_resets_focus(shell):
    shell.dispatch("right")
    assert json.loads(shell.snapshotJson)["consoleExitFocused"]
    shell.dispatch("accept")
    assert [item["id"] for item in shell._items()] == ["browser", "emulator"]
    assert not shell.console_exit_focused


def test_restarted_application_resets_exit_focus_even_when_its_row_stays(shell):
    shell.dispatch("right")
    shell.runtime_console.identities["terminal"] = Identity(101, 1000)
    shell.runtime_console._rebuild()
    assert not shell.console_exit_focused


def test_force_confirmation_defaults_to_cancel_and_pins_original_target(shell):
    shell.dispatch("context")
    shell.chooseModal(2)
    assert shell.modal["kind"] == "confirm" and shell.modal["index"] == 0
    shell.dispatch("accept")
    assert len(shell._items()) == 3
    shell.dispatch("context")
    shell.chooseModal(2)
    shell._windows_changed([window("new", "terminal"), window("b", "browser"), window("c", "emulator")])
    shell.dispatch("right")
    shell.dispatch("accept")
    assert len(shell._items()) == 3
    assert "restarted" in str(shell.toast)


def test_accept_opens_details_and_back_restores_selected_application(shell):
    shell.select(1)
    shell.dispatch("accept")
    assert shell.modal["kind"] == "console-details"
    assert shell.runtime_console.details["applicationKey"] == "browser"
    assert not shell.toast
    shell.dispatch("back")
    assert not shell.modal
    assert shell.navigation.index == 1


@pytest.mark.parametrize("confirm_open", [False, True])
def test_details_back_keeps_application_when_a_row_above_exits(shell, confirm_open):
    shell.select(1)
    shell.dispatch("accept")
    if confirm_open:
        shell.chooseModal(2)
    shell._windows_changed([window("b", "browser"), window("c", "emulator")])
    assert shell.runtime_console.details["applicationKey"] == "browser"
    if confirm_open:
        shell.dispatch("back")
    shell.dispatch("back")
    assert shell._items()[shell.navigation.index]["id"] == "browser"


def test_details_metrics_refresh_without_moving_the_selected_action(shell):
    shell.dispatch("accept")
    assert shell.modal["kind"] == "console-details"
    shell.dispatch("down")
    console = shell.runtime_console
    console.identities["terminal"] = Identity(101, 1000)
    console.metrics["terminal"] = {"members": [Identity(101, 1000), Identity(102, 1100)]}
    console.model.update([dict(row, cpuPercent=42.3, memoryBytes=912 * 1048576,
                              memoryRssBytes=1200 * 1048576, memoryPrivateBytes=700 * 1048576, uptimeSeconds=5432)
                          if row["applicationKey"] == "terminal" else row for row in console.model.rows])
    console.summaryChanged.emit()
    assert console.details["cpuPercent"] == 42.3
    assert console.details["memoryBytes"] == 956301312
    assert console.details["memoryRssBytes"] == 1258291200
    assert console.details["memoryPrivateBytes"] == 734003200
    assert console.details["uptimeSeconds"] == 5432
    assert console.details["mainPid"] == 101
    assert console.details["processCount"] == 2
    assert shell.modal["index"] == 2


def test_collected_memory_metrics_reach_the_details_without_an_rss_fallback():
    console = RuntimeConsole(mock=True)
    console.mock = False
    identity = Identity(101, 1000)
    app = "io.github.zhubby.uDeck.Music"
    console.visible = True
    console.owners[app] = ":1.12"
    console.set_details(app)
    values = {"cpuPercent": 1, "memoryBytes": None, "memoryRssBytes": 200 * 1048576,
              "memoryPrivateBytes": None, "uptimeSeconds": 20, "members": [identity]}
    try:
        console._collected((console.generation, dict(console.owners),
                            (None, {app: identity}, {app: values}, {}), None))
        assert console.details["memoryBytes"] is None
        assert console.details["memoryRssBytes"] == 209715200
        assert console.details["memoryPrivateBytes"] is None
        assert console.details["processCount"] == 1
    finally:
        console.close()


def test_details_open_application_is_an_explicit_action(shell):
    shell.dispatch("accept")
    assert shell.modal["kind"] == "console-details"
    shell.chooseModal(0)
    assert not shell.modal
    assert "terminal" in str(shell.toast).casefold()
    assert len(shell._items()) == 3


def test_details_exit_cannot_target_the_next_application_after_exit(shell):
    shell.dispatch("accept")
    assert shell.modal["kind"] == "console-details"
    shell.chooseModal(1)
    assert [item["id"] for item in shell._items()] == ["browser", "emulator"]
    assert not shell.runtime_console.details["available"]
    shell.chooseModal(1)
    assert [item["id"] for item in shell._items()] == ["browser", "emulator"]
    shell.chooseModal(3)
    assert not shell.modal


def test_details_force_cancel_returns_to_details_and_confirm_pins_target(shell):
    shell.dispatch("accept")
    assert shell.modal["kind"] == "console-details"
    shell.chooseModal(2)
    assert shell.modal["kind"] == "confirm" and shell.modal["index"] == 0
    shell.dispatch("accept")
    assert shell.modal["kind"] == "console-details" and shell.modal["index"] == 2
    assert len(shell._items()) == 3
    shell.dispatch("accept")
    shell._windows_changed([window("new", "terminal"), window("b", "browser"), window("c", "emulator")])
    shell.chooseModal(1)
    assert len(shell._items()) == 3
    assert "restarted" in str(shell.toast)


def test_metric_changes_do_not_reset_or_reinsert_model_rows():
    model = ConsoleModel()
    model.update([{"applicationKey": "browser", "cpuPercent": 1}])
    events = []
    model.modelReset.connect(lambda: events.append("reset"))
    model.rowsInserted.connect(lambda *args: events.append("insert"))
    model.dataChanged.connect(lambda *args: events.append("data"))
    model.update([{"applicationKey": "browser", "cpuPercent": 25}])
    assert events == ["data"]
    assert model.data(model.index(0), next(role for role, name in model.roles.items() if name == "cpuPercent")) == 25


def test_late_hidden_sample_is_discarded_and_sampling_never_overlaps(monkeypatch):
    from udeck.runtime_console import service

    console = RuntimeConsole()
    console.executor.shutdown(wait=False)
    jobs = []
    class Executor:
        def submit(self, function):
            future = Future()
            jobs.append((function, future))
            return future
        def shutdown(self, **kwargs):
            pass
    console.executor = Executor()
    snapshot = Snapshot({101: Process(Identity(101, 1000), 1, service.os.getuid(), 10, 4096, "S")},
                        100, 80, 20, 4096, 2048, 100)
    monkeypatch.setattr(service, "sys", SimpleNamespace(platform="linux"))
    monkeypatch.setattr(service, "read_snapshot", lambda: snapshot)
    console.owners["example.app.Test"] = ":1.1"
    console.pids["example.app.Test"] = 101
    try:
        console.set_visible(True)
        console.refresh()
        assert len(jobs) == 1 and console.timer.isActive()
        console.set_visible(False)
        assert not console.timer.isActive()
        jobs[0][1].set_result(jobs[0][0]())
        assert console.previous is None and not console.metrics and not console.system
        console.refresh()
        assert len(jobs) == 1
    finally:
        console.close()


def test_external_game_window_is_grouped_only_with_verified_child_identity():
    console = RuntimeConsole(mock=True)
    emulator = "io.github.zhubby.uDeck.Emulator"
    console.infos[emulator] = {"state": "playing", "relatedWindows": [{"appId": "com.libretro.RetroArch", "pid": 222}]}
    try:
        console.set_windows([window("front", emulator), window("game", "com.libretro.RetroArch")])
        assert len(console.model.rows) == 2
        console.metrics[emulator] = {"members": [Identity(222, 1000)]}
        console._rebuild()
        assert len(console.model.rows) == 1
        assert console.model.rows[0]["runtimeState"] == "playing"
    finally:
        console.close()
