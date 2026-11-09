import json

import pytest
from PySide6.QtCore import QCoreApplication

from udeck.controller import ShellController
from udeck.core import ConfigStore
from udeck.mock import MockBackend

HOME_IDS = [
    "io.github.zhubby.uDeck.Terminal.desktop",
    "io.github.zhubby.uDeck.Music.desktop",
    "io.github.zhubby.uDeck.Video.desktop",
    "io.github.zhubby.uDeck.Reader.desktop",
    "io.github.zhubby.uDeck.Emulator.desktop",
    "settings",
]


@pytest.fixture
def controller(tmp_path):
    application = QCoreApplication.instance() or QCoreApplication([])
    shell = ShellController(MockBackend(), config=ConfigStore(tmp_path / "settings.json"), mock=True)
    shell._test_application = application
    yield shell
    shell.close()


def test_home_has_six_fixed_shortcuts_independent_of_favorites_and_recent(controller):
    controller.config.data["favorites"] = ["code.desktop"]
    controller.config.data["recent"] = ["firefox.desktop", "terminal.desktop"]
    controller.applications.reverse()

    state = json.loads(controller.snapshotJson)

    assert [item["id"] for item in state["items"]] == HOME_IDS
    assert [item["name"] for item in state["items"]] == [
        "Terminal", "Music", "Video", "Reader", "Emulator", "Settings"
    ]
    assert state["pages"] == ["home", "apps", "windows", "files"]
    assert state["pageNames"] == ["Home", "Apps", "Running", "Files"]


def test_missing_apps_keep_their_home_slots_and_cannot_launch(controller, monkeypatch):
    controller.applications = []
    launched = []
    monkeypatch.setattr(controller, "_launch", launched.append)

    items = controller._items()
    assert [item["id"] for item in items] == HOME_IDS
    assert all(item["disabled"] for item in items[:5])
    assert not items[-1].get("disabled")
    controller.dispatch("accept")
    assert not launched
    assert controller.toast


def test_home_left_right_visits_every_shortcut_without_wrapping(controller):
    for index in range(6):
        assert controller.navigation.index == index
        controller.dispatch("right")
    assert controller.navigation.index == 5
    controller.dispatch("down")
    assert controller.navigation.index == 5
    for index in reversed(range(6)):
        assert controller.navigation.index == index
        controller.dispatch("left")
    assert controller.navigation.index == 0


@pytest.mark.parametrize("index", range(6))
def test_up_reaches_four_tabs_and_down_restores_home_selection(controller, index):
    controller.select(index)
    controller.dispatch("up")
    assert controller.navigation.zone == "tabs"
    controller.dispatch("down")
    assert controller.navigation.zone == "content"
    assert controller.navigation.index == index


@pytest.mark.parametrize("action", ["right", "next-page"])
def test_settings_is_not_a_fifth_top_level_page(controller, action):
    controller.setPage("files")
    if action == "right":
        controller.select(0)
        controller.dispatch("up")
    controller.dispatch(action)
    assert controller.navigation.page == "files"


def test_settings_opens_from_home_and_back_restores_its_shortcut(controller):
    controller.select(5)
    controller.dispatch("accept")
    assert controller.navigation.page == "settings"
    assert json.loads(controller.snapshotJson)["activeTab"] == "home"
    assert not controller.config.data["recent"]
    controller.dispatch("next-page")
    assert controller.navigation.page == "settings"
    controller.dispatch("back")
    assert controller.navigation.page == "home"
    assert controller.navigation.zone == "content"
    assert controller.navigation.index == 5


def test_settings_up_enters_the_home_tab_without_an_invisible_tab(controller):
    controller.select(5)
    controller.dispatch("accept")
    controller.select(0)
    controller.dispatch("up")
    assert controller.navigation.zone == "tabs"
    assert controller.navigation.page == "home"
    controller.dispatch("down")
    assert controller.navigation.index == 5


def test_home_settings_context_opens_settings_without_launching_an_app(controller):
    controller.select(5)
    controller.dispatch("context")
    assert not any(option.get("action") == "favorite" for option in controller.modal["options"])
    controller.chooseModal(0)
    assert controller.navigation.page == "settings"
    assert not controller.config.data["recent"]


@pytest.mark.parametrize("index", range(5))
def test_home_launches_the_corresponding_native_desktop_entry(controller, index):
    controller.select(index)
    controller.dispatch("accept")
    assert controller.config.data["recent"] == [HOME_IDS[index]]
    assert not controller.backend.actions
    assert controller.navigation.index == index


@pytest.mark.parametrize("index", range(5))
def test_home_dispatches_native_desktop_entries_outside_preview(controller, monkeypatch, index):
    launched = []
    controller.mock = False
    monkeypatch.setattr(controller.catalog, "launch", launched.append)
    monkeypatch.setattr(controller, "_run", lambda label, work, success: success(work()))

    controller.select(index)
    controller.dispatch("accept")

    assert launched == [HOME_IDS[index]]
    assert controller.config.data["recent"] == [HOME_IDS[index]]
    assert not controller.backend.actions


def test_quick_settings_returns_to_the_same_home_shortcut(controller):
    controller.select(4)
    controller.dispatch("quick-settings")
    assert controller.modal.get("source") == "quick-settings"
    controller.dispatch("back")
    assert controller.navigation.page == "home"
    assert controller.navigation.index == 4


def test_language_switch_preserves_home_order_and_focus(controller):
    controller.select(3)
    controller.setLanguage("zh_CN")
    state = json.loads(controller.snapshotJson)
    assert [item["id"] for item in state["items"]] == HOME_IDS
    assert [item["name"] for item in state["items"]] == ["终端", "音乐", "视频", "阅读器", "模拟器", "设置"]
    assert controller.navigation.index == 3
