import json
import time

import pytest
from PySide6.QtCore import QCoreApplication, QTimer

from udeck.apps.books import BookServer
from udeck.apps.controller import AppController
from udeck.apps.games import GamesController
from udeck.apps.main import AppControl
from udeck.apps.web import BrowserController


@pytest.fixture
def application():
    return QCoreApplication.instance() or QCoreApplication([])


def test_normal_second_launcher_request_presents_existing_app(application, tmp_path):
    controller = AppController("browser", tmp_path, tmp_path / "settings.json")
    shown = []
    control = AppControl(controller, lambda: shown.append(True), [], time.monotonic())
    try:
        # argparse's default is serialized as JSON null by the 0.1.0 launcher.
        assert control.Open(json.dumps({"command": None, "files": []})) == ""
        assert shown == [True]
        assert control.Open(json.dumps({"command": 42, "files": []}))
        assert shown == [True]
    finally:
        controller.close()


def test_canceled_browser_reading_result_cannot_restore_reading_mode(application, tmp_path):
    controller = BrowserController(tmp_path, tmp_path / "settings.json")
    try:
        controller.set_mode("reading")
        controller.set_mode("navigation")
        controller.readingReady(controller.current_tab, "A late reading extraction")
        assert controller.web_mode == "navigation"
        assert not controller.reading_text
    finally:
        controller.close()


@pytest.mark.parametrize("cancel", ["mode", "navigate", "tab", "back", "reload"])
def test_browser_discards_old_reading_generation(application, tmp_path, cancel):
    controller = BrowserController(tmp_path, tmp_path / "settings.json")
    try:
        identifier = controller.current_tab
        controller.set_mode("reading")
        generation = controller.web_generation
        if cancel == "mode":
            controller.set_mode("pointer")
        elif cancel == "navigate":
            controller.navigate("https://example.org")
        elif cancel == "tab":
            controller.new_tab()
        elif cancel == "back":
            controller.active_tab().can_back = True
            controller.dispatch("back")
        else:
            controller.context()
            controller.choose(6)
        controller.clear_menus()
        controller.readingReady(identifier, "Stale text", generation)
        assert controller.web_mode != "reading" and controller.reading_text == ""
        controller.clear_menus()
        controller.set_mode("reading")
        current_generation = controller.web_generation
        controller.readingReady(controller.current_tab, "Current text", current_generation)
        assert controller.web_mode == "reading" and controller.reading_text == "Current text"
        controller.readingReady(controller.current_tab, "Duplicate text", current_generation)
        assert controller.reading_text == "Current text"
    finally:
        controller.close()


@pytest.mark.parametrize("cancel", ["back", "clear", "tab", "close"])
def test_download_confirmation_can_be_canceled_without_writing(application, tmp_path, monkeypatch, cancel):
    target = tmp_path / "downloads"
    monkeypatch.setattr("PySide6.QtCore.QStandardPaths.writableLocation", lambda _: str(target))
    controller = BrowserController(tmp_path / "state", tmp_path / "settings.json")
    def dismiss():
        if cancel == "back":
            controller.dispatch("back")
        elif cancel == "clear":
            controller.clear_menus()
            controller.publish()
        elif cancel == "tab":
            controller.new_tab()
        else:
            controller.close()
    QTimer.singleShot(0, dismiss)
    try:
        assert not controller.confirmDownload("original.txt", "https://example.org/file", controller.current_tab)
        assert not target.exists() and not controller.menus
    finally:
        controller.close()


def test_malformed_epub_reports_a_format_error(tmp_path):
    path = tmp_path / "broken.epub"
    path.write_bytes(b"This file is not a ZIP archive")
    with pytest.raises(ValueError, match="Invalid EPUB"):
        BookServer({"path": str(path), "format": "EPUB", "title": "Broken"}, {}, {})


def test_download_acceptance_confines_name_and_rejects_overlapping_prompt(application, tmp_path, monkeypatch):
    target = tmp_path / "downloads"
    monkeypatch.setattr("PySide6.QtCore.QStandardPaths.writableLocation", lambda _: str(target))
    controller = BrowserController(tmp_path / "state", tmp_path / "settings.json")
    overlapping = []
    def decide():
        overlapping.append(controller.confirmDownload("other.txt", "https://example.org/other", controller.current_tab))
        controller.choose(0)
    QTimer.singleShot(0, decide)
    try:
        result = controller.confirmDownload("..\\outside.txt", "https://example.org/file", controller.current_tab)
        assert result == {"directory": str(target), "name": "outside.txt"}
        assert overlapping == [{}] and not controller.menus and list(target.iterdir()) == []
    finally:
        controller.close()


def test_finishing_download_removes_only_its_own_menu(application, tmp_path):
    controller = BrowserController(tmp_path, tmp_path / "settings.json")
    canceled = []
    controller.cancelDownload.connect(canceled.append)
    try:
        controller.downloadStarted(7, str(tmp_path / "download.txt"))
        controller.choose(0)
        assert canceled == [7]
        controller.settings()
        settings = controller.menus[-1]
        controller.downloadFinished(7, 3, "")
        assert controller.menus == [settings] and not controller.downloads
        assert set(controller._callbacks) == {row["id"] for row in settings["options"]}
    finally:
        controller.close()


def test_new_open_request_cannot_replace_identity_of_running_game(application, tmp_path):
    controller = GamesController(tmp_path, tmp_path / "settings.json")
    first = {"id": "running", "title": "Running game"}
    controller.current = first
    controller.library.require = lambda identifier: {
        "id": identifier, "title": "Another game", "path": "/missing.gb", "platform": "GB", "format": "GB"}
    controller.engine.running = lambda: True
    try:
        controller.attempt(lambda: controller.open_item("second"))
        assert controller.current is first
        assert controller.error
    finally:
        controller.engine.running = lambda: False
        controller.close()


def test_rejected_save_and_exit_does_not_exit_after_inflight_manual_save(application, tmp_path):
    controller = GamesController(tmp_path, tmp_path / "settings.json")
    controller.current = {"id": "original"}
    controller.library.require = lambda identifier: controller.current
    controller.engine.status = "paused"
    controller.engine.pending = {"kind": "save", "slot": "1"}
    controller.engine.running = lambda: True
    quits = []
    controller.engine.quit = lambda: quits.append(True)
    try:
        controller.attempt(controller.save_exit)
        assert not controller.exit_after_save
        controller.engine.pending = None
        controller.save_done("1")
        assert not quits and controller.menus
    finally:
        controller.engine.running = lambda: False
        controller.close()


def test_pending_load_keeps_game_paused_and_keeps_menu(application, tmp_path):
    controller = GamesController(tmp_path, tmp_path / "settings.json")
    controller.engine.status = "paused"
    controller.engine.pending = {"kind": "load"}
    sent = []
    controller.engine.send = sent.append
    controller.menu("Loading", [("Wait", lambda: None)])
    try:
        controller.attempt(controller.resume_game)
        assert not sent
        assert controller.menus and controller.error
    finally:
        controller.close()


def test_game_exit_clears_save_and_return_intent(application, tmp_path):
    controller = GamesController(tmp_path, tmp_path / "settings.json")
    controller.exit_after_save = True
    try:
        # The user can confirm "Return without saving" while an auto-save is pending.
        controller.game_exited(0)
        assert not controller.exit_after_save
    finally:
        controller.close()
