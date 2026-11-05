import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication

from udeck.controller import ShellController
from udeck.core import ConfigStore
from udeck.mock import MockBackend


def make_controller(tmp_path):
    application = QCoreApplication.instance() or QCoreApplication([])
    backend = MockBackend()
    controller = ShellController(backend, config=ConfigStore(tmp_path / "config.json"), mock=True)
    controller._test_application = application
    return controller


def test_mock_has_all_five_pages_and_no_hardware_actions(tmp_path):
    controller = make_controller(tmp_path)
    for page in ("home", "apps", "windows", "files", "settings"):
        controller.setPage(page)
        snapshot = json.loads(controller.snapshotJson)
        assert snapshot["page"] == page
        assert snapshot["items"]
        assert snapshot["mock"] is True


def test_quick_settings_restores_page_selection(tmp_path):
    controller = make_controller(tmp_path)
    controller.setPage("apps")
    controller.select(3)
    controller.dispatch("quick-settings")
    assert controller.modal["kind"] == "menu"
    controller.dispatch("back")
    assert controller.navigation.index == 3
    assert controller.navigation.page == "apps"


def test_power_confirmation_defaults_to_cancel(tmp_path):
    controller = make_controller(tmp_path)
    controller.activateSetting("poweroff")
    assert controller.modal["kind"] == "confirm"
    assert controller.modal["index"] == 0
    controller.dispatch("accept")
    assert not controller.modal
    assert "poweroff" not in controller.backend.actions


def test_file_context_menu_works_when_directory_is_empty(tmp_path):
    controller = make_controller(tmp_path)
    controller.data["files"] = []
    controller.setPage("files")
    controller.dispatch("context")
    assert any(option["action"] == "mkdir" for option in controller.modal["options"])


def test_nested_dialog_preserves_text_input(tmp_path):
    controller = make_controller(tmp_path)
    controller.dispatch("search")
    controller.editText("中文检索")
    controller.dispatch("quick-settings")
    controller.dispatch("back")
    assert controller.modal["text"] == "中文检索"


def test_paste_while_busy_does_not_open_orphan_progress(tmp_path):
    controller = make_controller(tmp_path)
    controller.mock = False
    controller.busy = True
    controller.clipboard = {"path": "/tmp/example", "move": False}
    controller._paste()
    assert not controller.modal


def test_agent_display_progress_updates_in_place(tmp_path):
    controller = make_controller(tmp_path)
    controller._agent_prompt({"kind": "information", "title": "配对码", "body": "123456", "token": "display"})
    controller._agent_prompt({"kind": "information", "title": "配对码", "body": "123456 · 已输入 1 位", "token": "display"})
    assert len(controller._modals) == 1
    assert controller.modal["body"].endswith("已输入 1 位")


def test_mute_is_available_from_volume_controls(tmp_path):
    controller = make_controller(tmp_path)
    controller.activateSetting("volume")
    assert any(option.get("systemAction") == "mute" for option in controller.modal["options"])


def test_quick_settings_includes_safe_power_menu(tmp_path):
    controller = make_controller(tmp_path)
    controller.dispatch("quick-settings")
    assert any(option["action"] == "power-menu" for option in controller.modal["options"])


def test_storage_failure_is_shown_on_the_current_page(tmp_path, monkeypatch):
    controller = make_controller(tmp_path)
    controller.setPage("apps")

    def denied():
        raise PermissionError("read-only configuration")

    monkeypatch.setattr(controller.config, "save", denied)
    controller._execute_option({"action": "favorite", "id": controller.applications[0]["id"]})
    assert "read-only configuration" in controller.toast
    assert controller.navigation.page == "apps"


def test_return_to_directory_restores_selected_item_not_old_row(tmp_path, monkeypatch):
    controller = make_controller(tmp_path)
    controller.mock = False
    (tmp_path / "a").mkdir()
    selected = tmp_path / "c"
    selected.mkdir()
    controller.data["directory"] = str(tmp_path)
    controller.data["files"] = controller.operations.list_directory(tmp_path)
    controller.setPage("files")
    controller.select(1)
    monkeypatch.setattr(controller, "_run", lambda label, work, success: success(work()))
    controller._browse(selected)
    (tmp_path / "b").mkdir()
    controller._browse(tmp_path)
    assert controller._items()[controller.navigation.index]["path"] == str(selected)


def test_one_failed_system_action_does_not_release_another_pending_action(tmp_path):
    controller = make_controller(tmp_path)
    controller.pending_system.update({"wifi_connect", "volume"})
    controller.backend.operationFailed.emit("volume", "output disappeared")
    assert controller.pending_system == {"wifi_connect"}
    assert controller.toast == "output disappeared"
