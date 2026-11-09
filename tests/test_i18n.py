import ast
import json
import re
from copy import deepcopy
from pathlib import Path
from string import Formatter
from threading import Thread

import pytest
from PySide6.QtCore import QCoreApplication, Qt

from udeck.controller import ShellController
from udeck.core import ConfigStore
from udeck.desktop import DesktopCatalog
from udeck.i18n import LANGUAGES, Message, catalog, error_text, render, tr
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


def snapshot(controller):
    return json.loads(controller.snapshotJson)


@pytest.mark.parametrize("preferences", [None, {}, {"language": "fr"}, {"language": []},
                                         {"language": {}}, {"language": False}, {"language": ""}])
def test_missing_and_invalid_language_defaults_to_english(tmp_path, monkeypatch, preferences):
    monkeypatch.setenv("LANG", "zh_CN.UTF-8")
    path = tmp_path / "settings.json"
    if preferences is not None:
        path.write_text(json.dumps({"preferences": preferences}))
    assert ConfigStore(path).data["preferences"]["language"] == "en"


def test_default_shell_and_settings_are_english(controller):
    state = snapshot(controller)
    assert state["language"] == "en"
    assert state["pageNames"] == ["Home", "Apps", "Running", "Files"]
    assert state["title"] == "Start here"
    controller.setPage("settings")
    settings = {item["id"]: item for item in snapshot(controller)["items"]}
    assert settings["volume"]["name"] == "Volume"
    assert settings["language"]["name"] == "Language"
    assert settings["language"]["subtitle"] == "English"


def test_setting_selection_updates_immediately_persists_and_restores_focus(controller):
    controller.setPage("settings")
    position = next(i for i, item in enumerate(controller._items()) if item["id"] == "language")
    controller.select(position)
    controller.dispatch("accept")
    key = controller.modal["key"]
    assert [option["label"] for option in controller.modal["options"]] == ["English", "简体中文"]
    controller.dispatch("down")
    controller.dispatch("accept")
    state = snapshot(controller)
    assert state["language"] == "zh_CN"
    assert state["modal"]["key"] == key
    assert state["modal"]["index"] == 1
    assert state["modal"]["title"] == "界面语言"
    assert state["pageNames"] == ["主页", "应用", "运行中", "文件"]
    assert state["activeTab"] == "home"
    assert ConfigStore(controller.config.path).data["preferences"]["language"] == "zh_CN"
    controller.dispatch("back")
    assert controller.navigation.index == position
    assert controller.navigation.page == "settings"
    controller.activateSetting("language")
    assert controller.modal["index"] == 1
    controller.dispatch("up")
    controller.dispatch("accept")
    assert snapshot(controller)["modal"]["title"] == "Interface language"
    assert ConfigStore(controller.config.path).data["preferences"]["language"] == "en"


def test_language_is_also_reachable_from_quick_settings(controller):
    controller.dispatch("quick-settings")
    controller.chooseModal(next(i for i, option in enumerate(controller.modal["options"]) if option.get("id") == "language"))
    assert controller.modal["source"] == "language"


def test_failed_save_keeps_previous_language_and_other_preferences(controller, monkeypatch):
    controller.config.data["favorites"] = ["keep.desktop"]
    controller.config.data["input"] = {"buttons": {"1": "accept"}}
    controller.config.save()
    before = controller.config.path.read_bytes()

    def deny():
        raise PermissionError("read-only settings")

    monkeypatch.setattr(controller.config, "save", deny)
    assert not controller.setLanguage("zh_CN")
    assert controller.language == "en"
    assert controller.config.data["preferences"]["language"] == "en"
    assert controller.config.path.read_bytes() == before
    assert "Could not save language" in snapshot(controller)["toast"]
    assert controller.config.data["favorites"] == ["keep.desktop"]
    assert controller.config.data["input"] == {"buttons": {"1": "accept"}}


def test_unknown_language_does_not_write_configuration(controller):
    assert not controller.setLanguage("fr")
    assert not controller.setLanguage([])
    assert controller.language == "en"
    assert not controller.config.path.exists()


def test_live_backend_messages_and_password_input_keep_their_ownership(controller):
    controller.backend.prompt.emit({"kind": "text", "title": tr("Wi-Fi 密码"),
                                    "body": tr("连接 ") + "设置", "token": "wifi-test",
                                    "deviceId": "usb", "purpose": "agent", "secret": True})
    controller.editText("secret{}中文")
    key = controller.modal["key"]
    assert snapshot(controller)["modal"]["title"] == "Wi-Fi password"
    assert snapshot(controller)["modal"]["body"] == "Connect 设置"
    controller.backend.operationFailed.emit("wifi_scan", tr("目标无线网卡已移除"))
    assert snapshot(controller)["toast"] == "The target Wi-Fi adapter was removed"
    assert controller.setLanguage("zh_CN")
    state = snapshot(controller)
    assert state["modal"]["title"] == "Wi-Fi 密码"
    assert state["modal"]["text"] == ""
    assert json.loads(controller.viewSnapshotJson)["modal"]["text"] == "secret{}中文"
    assert state["modal"]["key"] == key
    assert state["modal"]["token"] == "wifi-test"
    assert state["modal"]["deviceId"] == "usb"
    assert state["toast"] == "目标无线网卡已移除"
    assert controller.backend.actions == []


def test_queued_service_updates_detach_mutable_data_and_keep_translations(controller):
    from udeck.backend import SystemBackend

    backend = SystemBackend()
    backend.updated.connect(controller._update)
    value = {"available": True, "powered": True,
             "devices": [{"id": "external", "name": "用户设备"}], "error": tr("蓝牙适配器不可用")}

    def publish_then_mutate():
        backend.publish("bluetooth", value)
        value["devices"].clear()

    worker = Thread(target=publish_then_mutate)
    worker.start()
    worker.join()
    controller._test_application.processEvents()
    backend.loop.close()
    state = snapshot(controller)["bluetooth"]
    assert state["devices"][0]["name"] == "用户设备"
    assert state["error"] == "Bluetooth adapter unavailable"
    controller.setLanguage("zh_CN")
    assert snapshot(controller)["bluetooth"]["error"] == "蓝牙适配器不可用"


def test_wifi_updates_and_user_names_are_not_translated(controller):
    values = deepcopy(controller.backend.state)
    values["wifi"]["devices"][1]["networks"][0]["name"] = "音量 {literal}"
    controller.backend.updated.emit(values)
    controller.activateSetting("wifi")
    assert snapshot(controller)["modal"]["options"][1]["label"].startswith("Built-in Wi-Fi adapter")
    controller.chooseModal(2)
    english = snapshot(controller)["modal"]["options"]
    assert english[2]["label"] == "音量 {literal}"
    assert english[-1]["subtitle"].endswith("Open network")
    controller.setLanguage("zh_CN")
    chinese = snapshot(controller)["modal"]["options"]
    assert chinese[2]["label"] == "音量 {literal}"
    assert chinese[-1]["subtitle"].endswith("开放网络")
    assert [item["id"] for item in english] == [item["id"] for item in chinese]


def test_marked_messages_survive_concatenation_copy_and_nested_errors():
    message = tr("操作失败：{value0}", value0=ValueError(tr("Wi-Fi 密码")))
    assert render(deepcopy(message), "en") == "Operation failed: Wi-Fi password"
    assert isinstance(error_text(ValueError(tr("文件夹"))), Message)
    assert render("音量" + tr(" · 链接"), "en") == "音量 · Link"
    assert render(tr("连接 ") + "音量 {foo}", "en") == "Connect 音量 {foo}"
    assert render(tr("音量"), "unsupported") == "Volume"


def test_desktop_language_switch_preserves_selected_app_under_modal(controller, tmp_path):
    directory = tmp_path / "applications"
    directory.mkdir()
    (directory / "a.desktop").write_text("[Desktop Entry]\nType=Application\nName=Alpha\nName[zh_CN]=最后\nComment=English note\nComment[zh_CN]=中文说明\nExec=true\n")
    (directory / "z.desktop").write_text("[Desktop Entry]\nType=Application\nName=Zulu\nName[zh_CN]=首先\nExec=true\n")
    controller.mock = False
    controller.catalog = DesktopCatalog([directory], locale="en")
    controller.applications = controller.catalog.entries()
    controller.setPage("apps")
    controller.select(1)
    controller.dispatch("quick-settings")
    controller.chooseModal(next(i for i, option in enumerate(controller.modal["options"]) if option.get("id") == "language"))
    controller.setLanguage("zh_CN")
    controller.dispatch("back")
    assert controller._items()[controller.navigation.index]["id"] == "z.desktop"
    assert controller.catalog.by_id["a.desktop"]["subtitle"] == "中文说明"


def test_terminal_switches_chrome_without_restarting_sessions_or_translating_titles(controller, tmp_path):
    terminal = TerminalController(LaunchRequest(str(tmp_path), [], "", {}),
                                  TerminalPreferences(tmp_path / "terminal.json"), mock=True)
    identifier = terminal.current
    operations = []
    terminal.operate.connect(lambda *args: operations.append(args))
    assert snapshot(terminal)["tabs"][0]["title"] == "Local shell"
    terminal.preparePaste("echo 设置\necho done")
    terminal.setLanguage("zh_CN")
    assert terminal.current == identifier
    assert snapshot(terminal)["tabs"][0]["title"] == "本地 shell"
    assert snapshot(terminal)["pastePreview"] == "echo 设置\necho done"
    assert terminal.tabs.rowCount() == 1
    assert operations == []
    terminal.updateTitle(identifier, "设置")
    terminal.setLanguage("en")
    assert snapshot(terminal)["tabs"][0]["title"] == "设置"
    assert terminal.tabs.data(terminal.tabs.index(0), Qt.UserRole + 2) == "设置"
    terminal.componentFailed()
    assert snapshot(terminal)["message"].startswith("Could not load the native terminal component")
    terminal.setLanguage("zh_CN")
    assert snapshot(terminal)["message"] == "终端原生组件加载失败，请检查 udeck-terminal 安装和 Qt 版本。"


def test_catalogs_cover_every_marked_message_and_preserve_format_fields():
    root = Path(__file__).parents[1] / "src/udeck"
    sources = set()
    for path in root.rglob("*.py"):
        if path.name == "i18n.py":
            continue
        for node in ast.walk(ast.parse(path.read_text())):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "tr"
                    and node.args and isinstance(node.args[0], ast.Constant)):
                sources.add(node.args[0].value)
    for path in root.rglob("*.qml"):
        sources.update(ast.literal_eval(value) for value in re.findall(r'(?:window|root).tr\(("(?:[^"\\]|\\.)*")\)', path.read_text()))
    formatter = Formatter()

    def fields(value):
        return {(field, spec, conversion) for _, field, spec, conversion in formatter.parse(value) if field is not None}

    for language in LANGUAGES:
        messages = catalog(language)
        assert sources <= messages.keys(), sources - messages.keys()
        for source, translated in messages.items():
            assert fields(source) == fields(translated), (language, source)
