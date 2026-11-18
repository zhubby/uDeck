"""
[INPUT]: 依赖隔离桌面控制器和共享状态回调。
[OUTPUT]: 验证共享菜单、后台查询边界和重复状态去重。
[POS]: 共享界面回归；不启动真实共享或修改系统配置。
[PROTOCOL]: Update this header on change, then check AGENTS.md
"""

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


def test_hidden_stopped_shares_do_not_poll_but_running_shares_keep_status(tmp_path, monkeypatch):
    application = QCoreApplication.instance() or QCoreApplication([])
    controller = ShellController(MockBackend(), config=ConfigStore(tmp_path/'settings.json'), mock=True)
    requests = []
    monkeypatch.setattr(controller, '_sharing_request', lambda *args: requests.append(args))
    try:
        controller.mock = False
        for share in controller._shares.values():
            share['loaded'] = True
        controller._network_poll()
        assert requests == []
        controller.network_access['enabled'] = True
        controller._network_poll()
        assert requests == [('web', 'status')]
        requests.clear()
        controller._network_poll(force=True)
        assert requests == [('web', 'status'), ('smb', 'status')]
    finally:
        controller.close()
        application.processEvents()


def test_open_sharing_menu_refreshes_stopped_protocols(tmp_path, monkeypatch):
    application = QCoreApplication.instance() or QCoreApplication([])
    controller = ShellController(MockBackend(), config=ConfigStore(tmp_path/'settings.json'), mock=True)
    requests = []
    monkeypatch.setattr(controller, '_sharing_request', lambda *args: requests.append(args))
    try:
        controller.mock = False
        for share in controller._shares.values():
            share['loaded'] = True
        controller._sharing_menu()
        assert requests == [('web', 'status'), ('smb', 'status')]
        requests.clear()
        controller._network_poll()
        assert requests == [('web', 'status'), ('smb', 'status')]
    finally:
        controller.close()
        application.processEvents()


def test_identical_share_status_does_not_republish_desktop_view(tmp_path):
    application = QCoreApplication.instance() or QCoreApplication([])
    controller = ShellController(MockBackend(), config=ConfigStore(tmp_path/'settings.json'), mock=True)
    updates = []
    try:
        saved = {**controller.network_access, 'state':'running', 'enabled':True, 'networks':['home']}
        controller._network_result(('status', saved, ''))
        controller.viewChanged.connect(lambda: updates.append(True))
        controller._shares['web']['busy'] = True
        controller._network_result(('status', dict(saved), ''))
        assert updates == [] and not controller._shares['web']['busy']
        controller._network_result(('status', {**saved, 'enabled':False, 'state':'stopped'}, ''))
        assert updates == [True]
    finally:
        controller.close()
        application.processEvents()
