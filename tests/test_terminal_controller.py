import json

import pytest
from PySide6.QtCore import QCoreApplication

from udeck.terminal.controller import TerminalController
from udeck.terminal.core import LaunchRequest, TerminalPreferences


@pytest.fixture
def terminal(tmp_path):
    app = QCoreApplication.instance() or QCoreApplication([])
    controller = TerminalController(LaunchRequest(str(tmp_path), [], "", {}),
                                    TerminalPreferences(tmp_path / "prefs.json"), mock=True)
    controller._test_app = app
    return controller


def state(terminal):
    return json.loads(terminal.snapshotJson)


def test_physical_actions_do_not_consume_keyboard_letters_or_escape(terminal):
    operations = []
    terminal.operate.connect(lambda *args: operations.append(args))
    terminal.dispatch("accept")
    terminal.dispatch("back")
    assert [entry[1] for entry in operations] == ["return", "escape"]
    terminal.dispatch("context")
    terminal.dispatch("down")
    assert len(operations) == 2


def test_tab_boundaries_and_modal_input_are_isolated(terminal):
    first = terminal.current
    terminal.dispatch("previous-tab")
    assert terminal.current == first


    terminal.newTab()
    second = terminal.current
    terminal.dispatch("next-tab")
    assert terminal.current == second
    terminal.dispatch("context")
    terminal.dispatch("previous-tab")
    assert terminal.current == second
    terminal.dispatch("back")
    terminal.dispatch("previous-tab")
    assert terminal.current == first


@pytest.mark.parametrize("mode", ["menu", "settings", "history", "search", "close", "paste", "error"])
def test_shortcuts_cannot_bypass_modal_context(terminal, mode):
    terminal.mode = mode
    before = terminal.snapshotJson
    for action in ("new-tab", "close-tab", "menu", "search", "paste", "home"):
        terminal.command(action)
    terminal.newTab()
    assert terminal.snapshotJson == before


def test_confirm_close_defaults_to_cancel_and_does_not_touch_process(terminal):
    operations = []
    terminal.operate.connect(lambda *args: operations.append(args))
    terminal.requestCloseWindow()
    assert state(terminal)["index"] == 0
    terminal.dispatch("accept")
    assert not operations
    assert terminal.tabs.rowCount() == 1
    terminal.requestCloseWindow()
    terminal.dispatch("down")
    terminal.dispatch("accept")
    assert operations[-1][1] == "close"


def test_confirmed_window_close_cannot_add_sessions_before_native_exit_arrives(terminal):
    terminal.requestCloseWindow()
    terminal.dispatch("down")
    terminal.dispatch("accept")
    assert terminal.closing_window
    terminal.newTab()
    terminal.command("new-tab")
    assert terminal.tabs.rowCount() == 1
    terminal._test_app.processEvents()
    assert terminal.tabs.rowCount() == 0


def test_natural_exit_removes_only_that_session_then_closes_last_window(terminal):
    closed = []
    terminal.closed.connect(lambda: closed.append(True))
    first = terminal.current
    terminal.newTab()
    terminal.sessionFinished(first)
    assert terminal.tabs.rowCount() == 1
    assert not closed
    terminal.sessionFinished(terminal.current)
    assert closed == [True]


def test_history_requires_anchor_then_copy_and_cancel_returns_to_input(terminal):
    operations = []
    terminal.operate.connect(lambda *args: operations.append(args))
    terminal.command("history")
    terminal.dispatch("up")
    terminal.dispatch("accept")
    assert state(terminal)["anchored"]
    terminal.dispatch("right")
    terminal.dispatch("accept")
    assert state(terminal)["mode"] == "input"
    assert [entry[1] for entry in operations] == ["history", "up", "anchor", "right", "copy-history"]


def test_copy_shortcut_finishes_the_current_history_context(terminal):
    operations = []
    terminal.operate.connect(lambda *args: operations.append(args))
    terminal.command("history")
    terminal.dispatch("accept")
    terminal.dispatch("right")
    terminal.command("copy")
    assert terminal.mode == "input"
    assert operations[-1][1] == "copy-history"


def test_paste_freezes_text_and_cancel_never_sends_it(terminal):
    operations = []
    terminal.operate.connect(lambda *args: operations.append(args))
    terminal.preparePaste("echo 一\necho 二")
    assert state(terminal)["mode"] == "paste"
    terminal.dispatch("back")
    assert not operations
    terminal.preparePaste("echo 一\necho 二")
    terminal.dispatch("down")
    terminal.dispatch("accept")
    assert operations[-1][1:] == ("paste", "echo 一\necho 二")


def test_session_spec_carries_exact_environment_but_public_state_does_not(terminal):
    terminal.requests[terminal.current].environment["TEST_SECRET"] = "private-value"
    assert "private-value" in terminal.sessionSpec(terminal.current)
    assert "private-value" not in terminal.snapshotJson


def test_backgrounding_keeps_sessions_and_returns_home(terminal):
    home = []
    terminal.home.connect(lambda: home.append(True))
    terminal.command("home")
    assert home == [True]
    assert terminal.tabs.rowCount() == 1
