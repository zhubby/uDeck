import json
from copy import deepcopy

import pytest
from PySide6.QtCore import QCoreApplication
from PySide6.QtTest import QTest

from udeck.controller import ShellController
from udeck.core import ConfigStore
from udeck.mock import MockBackend


@pytest.fixture
def controller(tmp_path):
    application = QCoreApplication.instance() or QCoreApplication([])
    instance = ShellController(MockBackend(), config=ConfigStore(tmp_path / "settings.json"), mock=True)
    instance._test_application = application
    yield instance
    instance.close()


def test_key_test_receives_press_release_chords_without_running_actions(controller):
    controller.setPage("settings")
    position = next(i for i, item in enumerate(controller._items()) if item["id"] == "key-test")
    controller.select(position)
    controller.dispatch("accept")
    owner = controller.modal["key"]
    for action in ("accept", "context", "quick-settings", "up", "previous-page"):
        controller.testButton(action, True, "gamepad")
        controller.dispatch(action)
    assert controller.modal["key"] == owner
    assert set(controller.modal["pressed"]) == {"accept", "context", "quick-settings", "up", "previous-page"}
    assert controller.backend.actions == []
    controller.testButton("context", False, "gamepad")
    assert "context" not in controller.modal["pressed"]
    assert "context" in controller.modal["tested"]
    controller.windowActive(False)
    assert not controller.modal["pressed"]
    controller.dispatch("back")
    assert not controller.modal
    assert controller.navigation.index == position


def test_key_test_ignores_events_outside_its_page_and_never_saves_mapping(controller):
    before = deepcopy(controller.config.data)
    controller.testButton("accept", True, "gamepad")
    assert not controller.modal
    controller.activateSetting("key-test")
    controller.testButton("accept", True, "gamepad")
    controller.testButton("accept", True, "gamepad")
    assert controller.modal["pressCount"] == 1
    controller.testButton("accept", True, "keyboard")
    controller.testButton("accept", False, "gamepad")
    assert controller.modal["pressed"] == ["accept"]
    controller.testButton("accept", False, "keyboard")
    assert controller.modal["pressed"] == []
    assert controller.config.data == before


def test_key_test_back_button_can_be_tested_then_held_to_exit(controller):
    controller.activateSetting("key-test")
    owner = controller.modal["key"]
    controller.testButton("back", True, "gamepad")
    QTest.qWait(80)
    assert controller.modal["key"] == owner and "back" in controller.modal["pressed"]
    controller.testButton("back", False, "gamepad")
    QTest.qWait(1250)
    assert controller.modal["key"] == owner
    controller.testButton("back", True, "gamepad")
    QTest.qWait(1300)
    assert not controller.modal
    controller.testButton("back", False, "gamepad")
    assert not controller.modal


def test_key_test_focus_loss_cancels_exit_hold_and_clears_all_pressed_keys(controller):
    controller.activateSetting("key-test")
    controller.testButton("back", True, "gamepad")
    controller.windowActive(False)
    QTest.qWait(1300)
    assert controller.modal["kind"] == "key-test"
    assert not controller.modal["pressed"]


def test_key_test_does_not_record_background_shoulder_events(controller):
    controller.activateSetting("key-test")
    controller.windowActive(False)
    controller.testButton("previous-page", True, "shoulder")
    assert controller.modal["pressCount"] == 0 and not controller.modal["pressed"]
    controller.windowActive(True)
    controller.testButton("previous-page", True, "shoulder")
    assert controller.modal["pressed"] == ["previous-page"]


def test_interrupting_prompt_clears_pressed_keys_and_cancels_exit_timer(controller):
    controller.activateSetting("key-test")
    controller.testButton("back", True, "gamepad")
    controller._push({"kind": "information", "title": "Incoming prompt", "body": "Interrupted"})
    controller.testButton("back", False, "gamepad")
    controller.dispatch("back")
    assert controller.modal["kind"] == "key-test" and not controller.modal["pressed"]
    QTest.qWait(1300)
    assert controller.modal["kind"] == "key-test"


def test_disconnecting_the_gamepad_clears_its_test_state(controller):
    controller.activateSetting("key-test")
    controller.testButton("accept", True, "gamepad")
    assert controller.modal["pressed"] == ["accept"]
    controller.input_status({"available": False, "grabbed": False})
    assert not controller.modal["pressed"]


@pytest.mark.parametrize("language,title", [("en", "Key test"), ("zh_CN", "键位测试")])
def test_key_test_quick_entry_keeps_parent_focus_and_existing_input(controller, language, title):
    controller.setLanguage(language)
    controller.dispatch("search")
    controller.editText("existing draft")
    draft = deepcopy(controller.modal)
    controller.dispatch("quick-settings")
    controller.chooseModal(next(i for i, item in enumerate(controller.modal["options"]) if item.get("id") == "key-test"))
    assert json.loads(controller.snapshotJson)["modal"]["title"] == title
    controller.dispatch("back")
    assert controller.modal["source"] == "quick-settings"
    assert controller.modal["options"][controller.modal["index"]]["id"] == "key-test"
    controller.dispatch("back")
    assert controller.modal == draft
