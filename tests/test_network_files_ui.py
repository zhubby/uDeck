import json

from PySide6.QtCore import QCoreApplication

from udeck.controller import ShellController
from udeck.core import ConfigStore
from udeck.mock import MockBackend


def test_settings_web_menu_has_icons_and_duration_defaults(tmp_path):
    application=QCoreApplication.instance() or QCoreApplication([])
    controller=ShellController(MockBackend(),config=ConfigStore(tmp_path / "settings.json"),mock=True)
    try:
        controller.setPage("files")
        controller.dispatch("context")
        options=controller.modal["options"]
        position=next((i for i,row in enumerate(options) if row.get("command")=="network-access"),None)
        assert position is None, "Sharing moved into system settings"
        controller._cancel_modals()
        controller._network_menu()
        assert controller.modal["source"] == "sharing-web"
        assert all(row.get("icon") for row in controller.modal["options"])
        assert controller.network_draft["duration"] == 0
        controller._network_command("duration")
        options=controller.modal["options"]
        assert [row["value"] for row in options] == [0,3600,21600,43200]
        assert all(row.get("icon") for row in options)
        assert json.loads(controller.snapshotJson)["fileState"]["networkAccess"]["state"] == "stopped"
    finally:
        controller.close()
        application.processEvents()


def test_saved_configuration_loads_into_open_menu_and_preserves_edits(tmp_path):
    application = QCoreApplication.instance() or QCoreApplication([])
    controller = ShellController(MockBackend(), config=ConfigStore(tmp_path / "settings.json"), mock=True)
    try:
        controller.setPage("files")
        controller._network_menu()
        saved = {**controller.network_access, "root": str(tmp_path), "duration": 21600, "networks": ["home"]}
        controller._network_result(("status", saved, ""))
        assert controller.network_draft == {key: saved[key] for key in ("root", "duration", "networks")}
        controller.setLanguage("zh_CN")
        assert json.loads(controller.snapshotJson)["modal"]["options"][0]["checked"] is False
        controller._network_command("toggle", "other")
        controller._network_result(("status", saved, ""))
        assert controller.network_draft["networks"] == ["home", "other"]
        controller._network_command("networks")
        unavailable = next(row for row in controller.modal["options"] if row.get("value") == "home")
        assert unavailable["command"] == "toggle-network"
        controller._network_command("toggle", "home")
        assert controller.network_draft["networks"] == ["other"]
    finally:
        controller.close()
        application.processEvents()
