import json
import time
from copy import deepcopy

import pytest
from PySide6.QtCore import QCoreApplication

from udeck.apps.controller import AppController
from udeck.apps.web import BrowserController
from udeck.controller import ShellController
from udeck.core import ConfigStore
from udeck.mock import MockBackend
from udeck.terminal.controller import TerminalController
from udeck.terminal.core import LaunchRequest, TerminalPreferences


@pytest.fixture
def shell(tmp_path):
    application = QCoreApplication.instance() or QCoreApplication([])
    controller = ShellController(MockBackend(), config=ConfigStore(tmp_path / "settings.json"), mock=True)
    controller._test_application = application
    yield controller
    controller.close()


def capture(controller):
    assert hasattr(controller, "soundRequested"), "Expose semantic interaction feedback"
    events = []
    controller.soundRequested.connect(events.append)
    return events


def test_shell_sounds_follow_real_changes_not_keypresses_or_refreshes(shell):
    events = capture(shell)
    shell.setPage("apps")
    assert events == ["open"]
    events.clear()
    shell.dispatch("left")
    shell.backend.updated.emit(shell.backend.state)
    shell.notify("Background status")
    assert events == []
    shell.dispatch("right")
    assert events == ["navigate"]
    shell.dispatch("accept")
    assert events[-1] == "accept"
    shell.dispatch("context")
    assert events[-1] == "open"
    shell.dispatch("back")
    assert events[-1] == "back"


def test_empty_directory_navigation_does_not_tick_until_focus_really_moves(shell):
    shell.data["files"] = []
    shell.setPage("files")
    events = capture(shell)
    for action in ("left", "right", "down"):
        shell.dispatch(action)
    assert events == []
    shell.dispatch("up")
    assert events == ["navigate"]


def test_user_requested_folder_failures_are_audible_but_background_reads_are_not(shell, tmp_path, monkeypatch):
    def fail(*arguments):
        raise OSError("folder removed")

    monkeypatch.setattr(shell.operations, "list_directory", fail)
    shell.mock = False
    shell.setPage("files")
    shell.data["files"] = [{"id": str(tmp_path), "path": str(tmp_path), "name": "folder", "directory": True}]
    events = capture(shell)

    def wait():
        deadline = time.monotonic() + 2
        while shell.busy and time.monotonic() < deadline:
            QCoreApplication.processEvents()
            time.sleep(0.001)
        assert not shell.busy

    shell.dispatch("accept")
    wait()
    assert "error" in events and "success" not in events
    events.clear()
    shell._browse(tmp_path)
    wait()
    assert events == []


def test_nested_menu_activation_emits_one_open_not_accept_plus_open(shell):
    events = capture(shell)
    shell.dispatch("quick-settings")
    assert events == ["open"]
    events.clear()
    index = next(index for index, option in enumerate(shell.modal["options"]) if option.get("id") == "theme")
    shell.chooseModal(index)
    assert events == ["open"]
    shell.dispatch("back")
    shell.dispatch("back")
    assert events[-2:] == ["back", "back"]


def test_favorite_toggle_reports_its_actual_persisted_state(shell):
    shell.setPage("apps")
    events = capture(shell)
    shell.dispatch("context")
    shell.chooseModal(next(index for index, option in enumerate(shell.modal["options"])
                          if option.get("action") == "favorite"))
    assert events[-1] in ("toggle-on", "toggle-off")
    identifier = shell._items()[shell.navigation.index]["id"]
    enabled = identifier in ConfigStore(shell.config.path).data["favorites"]
    assert events[-1] == ("toggle-on" if enabled else "toggle-off")


def test_text_entry_and_no_op_slider_movement_stay_silent(shell):
    events = capture(shell)
    shell.dispatch("search")
    events.clear()
    shell.editText("中文 abc")
    assert events == []
    shell.dispatch("back")
    shell.activateSetting("volume-level")
    shell.modal["value"] = 1.0
    events.clear()
    shell.dispatch("right")
    assert events == []
    shell.dispatch("left")
    assert events == ["navigate"]


def test_interface_sound_setting_persists_without_changing_system_audio(shell, monkeypatch):
    events = capture(shell)
    shell.activateSetting("ui-sounds")
    assert ConfigStore(shell.config.path).data["preferences"]["uiSounds"] is False
    assert events == ["toggle-off"]
    shell.activateSetting("ui-sounds")
    assert ConfigStore(shell.config.path).data["preferences"]["uiSounds"] is True
    assert events[-1] == "toggle-on"
    assert shell.backend.actions == []

    def fail():
        raise OSError("read-only")

    monkeypatch.setattr(shell.config, "save", fail)
    shell.activateSetting("ui-sounds")
    assert shell.config.data["preferences"]["uiSounds"] is True
    assert events[-1] == "error"
    assert "save" in json.loads(shell.snapshotJson)["toast"].lower()


def test_only_real_requested_results_receive_completion_feedback(shell):
    events = capture(shell)
    shell._system_completed("refresh")
    shell._operation_failed("refresh", "Background service unavailable")
    assert events == []
    shell.pending_system.add("timezone_set")
    shell._system_completed("timezone_set")
    assert events == ["success"]
    shell.pending_system.add("wifi_connect")
    shell._system_completed("wifi_connect")
    assert events == ["success"]
    shell.pending_system.add("audio_output")
    shell._operation_failed("audio_output", "Output removed")
    assert events[-1] == "error"


@pytest.mark.parametrize("status,event", [("connected", "success"), ("failed", "error")])
def test_wifi_feedback_waits_for_the_requested_adapters_real_result(shell, monkeypatch, status, event):
    monkeypatch.setattr(shell.backend, "request", lambda *arguments: None)
    events = capture(shell)
    wifi = deepcopy(shell.data["wifi"])
    device = wifi["devices"][0]
    shell._system("wifi_connect", {"deviceId": device["id"]})
    shell._system_completed("wifi_connect")
    assert events == []
    device["operation"] = {"id": "requested-join", "status": "connecting"}
    device["deviceState"] = 70
    shell._update({"wifi": deepcopy(wifi)})
    assert events == []
    device["operation"]["status"] = status
    device["deviceState"] = 100 if status == "connected" else 120
    shell._update({"wifi": deepcopy(wifi)})
    assert events == [event]
    shell._update({"wifi": deepcopy(wifi)})
    assert events == [event]


@pytest.mark.parametrize("change", ["removed", "epoch", "superseded", "cancelled"])
def test_cancelled_or_replaced_wifi_requests_cannot_report_a_later_connection(shell, monkeypatch, change):
    monkeypatch.setattr(shell.backend, "request", lambda *arguments: None)
    events = capture(shell)
    wifi = deepcopy(shell.data["wifi"])
    device = wifi["devices"][0]
    shell._system("wifi_connect", {"deviceId": device["id"]})
    device["operation"] = {"id": "requested-join", "status": "connecting"}
    device["deviceState"] = 70
    shell._update({"wifi": deepcopy(wifi)})
    if change == "removed":
        shell._update({"wifi": {**deepcopy(wifi), "devices": []}})
    elif change == "epoch":
        wifi["epoch"] = "restarted-service"
    elif change == "superseded":
        device["operation"]["id"] = "another-request"
    else:
        shell._system("wifi_cancel_connect", {"deviceId": device["id"]})
    device["operation"]["status"] = "connected"
    device["deviceState"] = 100
    shell._update({"wifi": deepcopy(wifi)})
    assert events == []
    shell._update({"wifi": deepcopy(wifi)})
    assert events == []


def test_file_completion_cannot_report_success_after_failure_or_cancellation(shell):
    events = capture(shell)
    shell._finish_task((None, None, RuntimeError("failed"), True, True))
    assert events == ["error"]
    shell._finish_task((None, None, InterruptedError(), True, True))
    assert events[-1] == "back"
    shell._finish_task((True, None, None, True, True))
    assert events[-1] == "success"
    events.clear()
    shell._finish_task((True, None, None, False, True))
    assert events == []


def test_native_app_menus_share_feedback_but_polling_and_drafts_do_not(tmp_path):
    application = QCoreApplication.instance() or QCoreApplication([])
    controller = AppController("browser", tmp_path, tmp_path / "settings.json")
    events = capture(controller)
    try:
        controller.command("context")
        assert events == ["open"]
        controller.dispatch("down")
        assert events[-1] == "navigate"
        controller.dispatch("back")
        assert events[-1] == "back"
        controller.command("search")
        events.clear()
        controller.setDraft("hello 中文")
        controller.poll()
        assert events == []
        controller.dispatch("back")
        controller.menu("Failure", [("Fail", lambda: (_ for _ in ()).throw(ValueError("invalid")))])
        events.clear()
        controller.dispatch("accept")
        assert events == ["error"]
    finally:
        controller.close()
        application.processEvents()


def test_terminal_input_is_silent_while_menu_and_tab_actions_have_feedback(tmp_path):
    application = QCoreApplication.instance() or QCoreApplication([])
    terminal = TerminalController(LaunchRequest(str(tmp_path), [], "", {}),
                                  TerminalPreferences(tmp_path / "terminal.json"), mock=True)
    events = capture(terminal)
    operations = []
    terminal.operate.connect(lambda *arguments: operations.append(arguments[1]))
    for action in ("up", "accept", "back", "previous-tab"):
        terminal.dispatch(action)
    assert operations == ["up", "return", "escape"]
    assert events == []
    terminal.command("menu")
    assert events == ["open"]
    terminal.dispatch("up")
    assert events == ["open"]
    terminal.dispatch("down")
    assert events[-1] == "navigate"
    terminal.dispatch("back")
    assert events[-1] == "back"
    terminal.command("new-tab")
    assert events[-1] == "open"
    events.clear()
    terminal.setQuery("not a key click")
    assert events == []
    application.processEvents()


def test_browser_web_input_stays_silent_but_uDeck_address_prompt_is_audible(tmp_path):
    application = QCoreApplication.instance() or QCoreApplication([])
    controller = BrowserController(tmp_path, tmp_path / "settings.json")
    events = capture(controller)
    try:
        controller.active_tab().url = "https://example.invalid"
        controller.set_mode("text")
        for action in ("up", "down", "left", "right", "accept"):
            controller.dispatch(action)
        controller.poll()
        assert events == []
        controller.command("address")
        assert events == ["open"]
        controller.setDraft("ordinary typing")
        assert events == ["open"]
    finally:
        controller.close()
        application.processEvents()
