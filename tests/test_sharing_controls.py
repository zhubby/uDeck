import json

import pytest
from PySide6.QtCore import QCoreApplication

from udeck.controller import ShellController
from udeck.core import ConfigStore
from udeck.mock import MockBackend


@pytest.fixture
def controller(tmp_path):
    application = QCoreApplication.instance() or QCoreApplication([])
    value = ShellController(MockBackend(), config=ConfigStore(tmp_path / "settings.json"), mock=True)
    yield value
    value.close()
    application.processEvents()


def test_sharing_entry_migrates_to_settings_and_quick_menu(controller):
    assert any(row["id"] == "sharing" for row in controller._settings())
    assert any(row.get("id") == "sharing" for row in controller._quick_options())
    controller.setPage("files")
    controller.dispatch("context")
    assert not any(row.get("command") == "network-access" for row in controller.modal["options"])
    controller._cancel_modals()
    controller.activateSetting("sharing")
    assert controller.modal["source"] == "sharing"
    assert [row["value"] for row in controller.modal["options"]] == ["web", "smb"]
    controller.chooseModal(0)
    assert controller.modal["source"] == "sharing-web"
    assert all(row.get("icon") and row.get("singleLine") for row in controller.modal["options"])
    assert [row["id"] for row in controller.modal["options"]] == ["enabled", "root", "networks", "duration", "addresses"]
    assert controller.modal["options"][0]["checked"] is False
    controller.dispatch("back")
    assert controller.modal["source"] == "sharing"
    controller.chooseModal(1)
    assert controller.smb_draft == {"root": "", "duration": 0, "networks": []}


def test_saved_web_configuration_and_legacy_calls(controller, tmp_path):
    controller._network_menu()
    assert controller.modal["source"] == "sharing-web"
    saved = {**controller.network_access, "root": str(tmp_path), "duration": 21600, "networks": ["home"]}
    controller._network_result(("status", saved, ""))
    assert controller.network_draft == {key: saved[key] for key in ("root", "duration", "networks")}
    assert json.loads(controller.snapshotJson)["fileState"]["networkAccess"]["root"] == str(tmp_path)
    controller._network_command("duration")
    assert [row["value"] for row in controller.modal["options"]] == [0, 3600, 21600, 43200]


def test_protocol_drafts_focus_and_polling_are_independent(controller, tmp_path, monkeypatch):
    controller._sharing_open("web")
    controller.chooseModal(2)
    controller._sharing_command("web", "toggle-network", "home")
    controller._network_result(("status", {**controller.network_access, "root": str(tmp_path)}, ""))
    assert controller.network_draft["networks"] == ["home"]
    assert controller.smb_draft["networks"] == []
    controller._sharing_command("web", "done")
    assert controller.modal["source"] == "sharing-web" and controller.modal["index"] == 2
    assert len(controller._modals) == 1
    controller.network_access.update(enabled=True, state="running")
    controller._network_result(("stop", None, "disk full"))
    assert controller.network_access["enabled"] is True
    assert controller.modal["index"] == 2
    assert "disk full" in controller.modal["body"]
    assert controller.smb_access["errors"] == []
    calls = []
    monkeypatch.setattr(controller, "_sharing_request", lambda protocol, operation, value=None: calls.append((protocol, operation)))
    controller.mock = False
    controller._cancel_modals()
    controller.setPage("home")
    controller._network_poll()
    assert calls == [("web", "status"), ("smb", "status")]


def test_switch_operation_keeps_menu_and_focus(controller, tmp_path):
    controller._sharing_open("smb")
    controller.smb_draft.update(root=str(tmp_path), networks=["home"])
    controller._sharing_refresh()
    key = controller.modal["key"]
    controller.chooseModal(0)
    assert controller.modal["key"] == key and controller.modal["index"] == 0
    assert controller.smb_access["enabled"] is True
    assert controller.network_access["enabled"] is False
    controller.chooseModal(0)
    assert controller.smb_access["enabled"] is False
    assert controller.modal["key"] == key


def test_action_queued_behind_status_immediately_shows_progress(controller):
    controller._sharing_open("smb")
    share = controller._shares["smb"]
    share.update(busy=True)
    share["state"].update(enabled=True, state="running")
    controller._sharing_refresh()
    key = controller.modal["key"]

    controller._sharing_request("smb", "stop")

    assert share["queued"] == ("stop", None)
    assert share["pending"] is True
    assert controller.modal["key"] == key and controller.modal["index"] == 0
    assert all(row["disabled"] for row in controller.modal["options"])
    assert controller.modal["options"][0]["checked"] is True
    assert "Applying" in str(controller.modal["options"][0]["subtitle"])
    assert controller._shares["web"]["pending"] is False


def test_open_sharing_body_tracks_language_changes(controller):
    controller._sharing_open("smb")
    controller.setLanguage("zh_CN")
    assert "无需密码" in json.loads(controller.snapshotJson)["modal"]["body"]
    controller.setLanguage("en")
    assert "Passwordless" in json.loads(controller.snapshotJson)["modal"]["body"]


def test_recovered_status_clears_poll_errors_but_preserves_action_errors(controller):
    controller._sharing_open("smb")
    controller._sharing_result(("smb", "status", None, "service unavailable"))
    assert "service unavailable" in controller.modal["body"]
    controller._sharing_result(("smb", "status", controller.smb_access, ""))
    assert "service unavailable" not in controller.modal["body"]
    controller._sharing_result(("smb", "start", None, "port conflict"))
    controller._sharing_result(("smb", "status", controller.smb_access, ""))
    assert "port conflict" in controller.modal["body"]
