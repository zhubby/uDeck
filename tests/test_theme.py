import json
from copy import deepcopy

import pytest
from PySide6.QtCore import QCoreApplication

from udeck.apps.common.controller import AppController
from udeck.controller import ShellController
from udeck.core import ConfigStore
from udeck.mock import MockBackend
from udeck.terminal.controller import TerminalController
from udeck.terminal.core import LaunchRequest, TerminalPreferences


@pytest.fixture
def controller(tmp_path):
    application = QCoreApplication.instance() or QCoreApplication([])
    instance = ShellController(MockBackend(), config=ConfigStore(tmp_path / "settings.json"), mock=True)
    instance._test_application = application
    yield instance
    instance.close()


@pytest.mark.parametrize("value", [None, "", "light", "DARK", [], {}, False, 1])
def test_old_and_invalid_theme_preferences_keep_classic(tmp_path, value):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"preferences": {"theme": value}}))
    assert ConfigStore(path).data["preferences"]["theme"] == "classic"


@pytest.mark.parametrize("language,names,current", [
    ("en", ["Classic", "Dark"], "Current theme"),
    ("zh_CN", ["经典", "黑暗"], "当前主题"),
])
def test_theme_menu_applies_persists_and_restores_focus(controller, language, names, current):
    controller.setLanguage(language)
    controller.setPage("settings")
    settings = controller._items()
    position = next(i for i, item in enumerate(settings) if item["id"] == "theme")
    assert settings[position - 1]["id"] == "language"
    controller.select(position)
    controller.dispatch("accept")
    owner = controller.modal["key"]
    state = json.loads(controller.snapshotJson)
    assert state["theme"] == "classic"
    assert [o["label"] for o in state["modal"]["options"]] == names
    assert state["modal"]["options"][0]["subtitle"] == current
    controller.dispatch("down")
    controller.dispatch("accept")
    assert controller.theme == "dark"
    assert controller.modal["key"] == owner and controller.modal["index"] == 1
    assert ConfigStore(controller.config.path).data["preferences"]["theme"] == "dark"
    assert json.loads(controller.snapshotJson)["modal"]["options"][1]["subtitle"] == current
    controller.backend.updated.emit(controller.backend.state)
    assert controller.modal["index"] == 1
    controller.dispatch("back")
    assert not controller.modal
    assert (controller.navigation.page, controller.navigation.index) == ("settings", position)
    controller.activateSetting("theme")
    assert controller.modal["index"] == 1
    controller.dispatch("up")
    controller.dispatch("accept")
    assert controller.theme == "classic"
    assert controller.backend.actions == []


def test_theme_quick_settings_returns_through_parent_to_existing_draft(controller):
    controller.dispatch("search")
    controller.editText("keep 中文 {draft}")
    owner = deepcopy(controller.modal)
    controller.dispatch("quick-settings")
    controller.chooseModal(next(i for i, o in enumerate(controller.modal["options"]) if o.get("id") == "theme"))
    controller.dispatch("down")
    controller.dispatch("accept")
    assert controller.theme == "dark"
    controller.dispatch("back")
    assert controller.modal["source"] == "quick-settings"
    state = json.loads(controller.snapshotJson)
    assert next(o for o in state["modal"]["options"] if o.get("id") == "theme")["subtitle"] == "Dark"
    controller.dispatch("back")
    assert controller.modal == owner


@pytest.mark.parametrize("language,expected", [("en", "Could not save theme settings"), ("zh_CN", "主题设置保存失败")])
def test_theme_save_failure_keeps_previous_ui_and_configuration(controller, monkeypatch, language, expected):
    controller.setLanguage(language)
    controller.config.data["favorites"] = ["keep.desktop"]
    controller.config.data["input"] = {"verified": True}
    controller.config.save()
    before = controller.config.path.read_bytes()
    controller.activateSetting("theme")
    owner = controller.modal["key"]

    def deny():
        raise PermissionError("read-only")

    monkeypatch.setattr(controller.config, "save", deny)
    assert not controller.setTheme("dark")
    state = json.loads(controller.snapshotJson)
    assert state["theme"] == "classic" and state["modal"]["key"] == owner
    assert expected in state["toast"]
    assert controller.config.data["preferences"]["theme"] == "classic"
    assert controller.config.path.read_bytes() == before


def test_invalid_or_unchanged_theme_does_not_save(controller):
    for value in ([], {}, False, "light"):
        assert not controller.setTheme(value)
    assert controller.setTheme("classic")
    assert not controller.config.path.exists()


def test_cached_saves_preserve_shared_preferences_and_unrelated_settings(tmp_path):
    path = tmp_path / "settings.json"
    shell = ConfigStore(path)
    shell.data["input"] = {"keep": True}
    shell.data["preferences"]["theme"] = "dark"
    shell.save()
    app = ConfigStore(path)
    app.data["preferences"]["language"] = "zh_CN"
    app.save()
    shell.favorite("keep.desktop", True)
    saved = ConfigStore(path)
    assert saved.data["preferences"]["language"] == "zh_CN"
    assert saved.data["preferences"]["theme"] == "dark"
    assert saved.data["input"] == {"keep": True}
    assert saved.data["favorites"] == ["keep.desktop"]
    shell.data["preferences"]["theme"] = "classic"
    shell.save()
    app.data["preferences"]["language"] = "en"
    app.save()
    assert ConfigStore(path).data["preferences"]["theme"] == "classic"


def test_app_follows_theme_without_replacing_state_or_its_input(controller, tmp_path):
    app = AppController("browser", tmp_path / "browser", controller.config.path)
    try:
        app.prompt("Address", lambda _: None, "typed 中文")
        before = deepcopy(app.snapshot())
        controller.setTheme("dark")
        app.poll()
        after = app.snapshot()
        assert after.pop("theme") == "dark"
        before.pop("theme")
        assert after == before
        app.set_language("zh_CN")
        assert ConfigStore(controller.config.path).data["preferences"]["theme"] == "dark"
    finally:
        app.poller.stop()


def test_terminal_theme_updates_ansi_palette_without_changing_sessions(controller, tmp_path):
    preferences = TerminalPreferences(tmp_path / "terminal.json")
    terminal = TerminalController(LaunchRequest(str(tmp_path), [], "", {}), preferences, mock=True)
    operations = []
    terminal.operate.connect(lambda *args: operations.append(args))
    terminal.preparePaste("printf 'keep'\necho 中文")
    before = json.loads(terminal.snapshotJson)
    controller.setTheme("dark")
    terminal.setTheme("dark")
    after = json.loads(terminal.snapshotJson)
    assert after.pop("theme") == "dark"
    before.pop("theme")
    assert after.pop("colorScheme") == "udeck-dark"
    assert before.pop("colorScheme") == "udeck"
    assert after.pop("themeLabel") == "Theme: Dark · Follow system"
    before.pop("themeLabel")
    assert after == before
    assert not operations
    restarted = TerminalController(LaunchRequest(str(tmp_path), [], "", {}), preferences, mock=True)
    assert restarted.theme == "dark"
