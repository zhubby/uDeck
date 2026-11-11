"""Settings stay application-scoped while using the shared desktop icon path."""

import json

import pytest
from PySide6.QtWidgets import QApplication

from udeck.apps.runtime import make_controller
from udeck.controller import ShellController
from udeck.core import ConfigStore
from udeck.mock import MockBackend


@pytest.fixture(scope="module")
def application():
    return QApplication.instance() or QApplication([])


@pytest.mark.parametrize("app", ["music", "video", "browser", "reader", "emulator"])
def test_application_settings_do_not_offer_global_language(application, tmp_path, app, monkeypatch):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    config_path = tmp_path / "settings.json"
    config = ConfigStore(config_path)
    config.data["preferences"]["language"] = "en"
    config.save()
    controller = make_controller(app, tmp_path / app, config_path)
    try:
        controller.command("settings")
        menu = json.loads(controller.snapshotJson)["menu"]
        assert menu["title"] == "Settings"
        assert "Language" not in [row["title"] for row in menu["options"]]
        assert all(row.get("icon") for row in menu["options"])
        controller.dispatch("back")
        assert not controller.menus
        assert ConfigStore(config_path).data["preferences"]["language"] == "en"
    finally:
        controller.close()
        application.processEvents()


def test_global_language_stays_in_system_settings(application, tmp_path):
    controller = ShellController(MockBackend(), config=ConfigStore(tmp_path / "settings.json"), mock=True)
    try:
        controller.setPage("settings")
        controller.select(next(i for i, row in enumerate(controller._items()) if row["id"] == "language"))
        controller.dispatch("accept")
        options = json.loads(controller.snapshotJson)["modal"]["options"]
        assert all(row.get("icon") for row in options)
        controller.chooseModal(next(i for i, row in enumerate(options) if row["id"] == "zh_CN"))
        assert controller.language == "zh_CN"
    finally:
        controller.close()
