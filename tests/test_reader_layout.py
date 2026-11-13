import json
from types import SimpleNamespace

import pytest

from udeck.apps.reader.style import normalize_reader_preferences
from udeck.i18n import Message, render


def test_reader_preferences_have_safe_defaults_and_reject_invalid_values():
    assert normalize_reader_preferences({}) == {
        "fontSize": 24,
        "lineHeight": 1.7,
        "fontFamily": "sans",
        "background": "paper",
        "contentWidth": 1000,
        "dark": False,
    }
    assert normalize_reader_preferences({
        "fontSize": 99,
        "lineHeight": "wide",
        "fontFamily": "unknown",
        "background": "unknown",
        "contentWidth": 1,
        "dark": True,
    }) == {
        "fontSize": 24,
        "lineHeight": 1.7,
        "fontFamily": "sans",
        "background": "night",
        "contentWidth": 1000,
        "dark": True,
    }


def test_reader_preferences_accept_supported_layout_values():
    assert normalize_reader_preferences({
        "fontSize": 32,
        "lineHeight": 2.0,
        "fontFamily": "serif",
        "background": "warm",
        "contentWidth": 720,
    }) == {
        "fontSize": 32,
        "lineHeight": 2.0,
        "fontFamily": "serif",
        "background": "warm",
        "contentWidth": 720,
        "dark": False,
    }


@pytest.fixture
def reader_controller(tmp_path):
    pytest.importorskip("PySide6")
    from PySide6.QtCore import QCoreApplication

    from udeck.apps.reader.controller import ReaderController

    application = QCoreApplication.instance() or QCoreApplication([])
    controller = ReaderController(tmp_path, tmp_path / "settings.json")
    yield controller
    controller.current = None  # Layout fixtures do not open an actual document.
    controller.close()
    application.processEvents()


@pytest.mark.parametrize("code,detail,chinese", [
    ("epub-resource", "Files {literal}/音量.xhtml", "无法读取 EPUB 资源：Files {literal}/音量.xhtml"),
    ("mobi-record", "", "无法读取 MOBI 数据记录"),
    ("reader-process", "9", "阅读进程已退出（9）"),
    ("unknown", "", "Unknown backend error {literal}"),
])
def test_reader_errors_keep_identity_arguments_and_session_guards(reader_controller, code, detail, chinese):
    controller = reader_controller
    controller.book = SimpleNamespace(token="active")
    controller.page = "document"
    payload = {"session": "old", "type": "error", "errorCode": code,
               "errorDetail": detail, "error": "Unknown backend error {literal}"}
    try:
        controller.readerEvent(json.dumps(payload))
        assert not controller.error
        payload["session"] = "active"
        controller.readerEvent(json.dumps(payload))
        assert isinstance(controller.error, Message)
        assert chinese in render(controller.error, "zh_CN")
        if code == "epub-resource":
            assert detail in render(controller.error, "en")
    finally:
        controller.book = None


def test_reader_layout_menu_hides_reflow_controls_for_pdf(reader_controller):
    controller = reader_controller
    captured = {}
    controller.current = {"format": "PDF"}
    controller.page = "document"
    controller.menu = lambda title, options, **kwargs: captured.update(title=str(title), options=options() if callable(options) else options)

    controller.layout_menu()

    assert captured["title"] == "Reading layout"
    assert [str(label) for label, *_ in captured["options"]] == ["Background"]


def test_reader_layout_menu_exposes_reflow_controls_for_epub(reader_controller):
    controller = reader_controller
    captured = {}
    controller.current = {"format": "EPUB"}
    controller.page = "document"
    controller.menu = lambda title, options, **kwargs: captured.update(title=str(title), options=options() if callable(options) else options)

    controller.layout_menu()

    assert [str(label) for label, *_ in captured["options"]] == [
        "Line spacing", "Font", "Content width", "Background"
    ]


def test_reading_settings_keep_focus_and_update_parent_values_after_changes(reader_controller):
    controller = reader_controller
    controller.settings()
    parent = controller.menus[-1]
    identifiers = [row["id"] for row in parent["options"]]

    controller.choose(0)
    assert controller.dark and controller.background == "night"
    assert controller.menus == [parent] and parent["index"] == 0
    assert json.loads(controller.snapshotJson)["menu"]["options"][0]["checked"] is True
    controller.dispatch("accept")
    assert not controller.dark and parent["options"][0]["checked"] is False

    controller.choose(2)
    controller.choose(4)  # 32 px, returning to the existing settings panel.
    assert controller.font_size == 32
    assert controller.menus == [parent] and parent["index"] == 2
    assert parent["options"][2]["subtitle"] == "32"
    assert [row["id"] for row in parent["options"]] == identifiers
    assert set(controller._callbacks) == set(identifiers)

    controller.choose(1)
    layout = controller.menus[-1]
    controller.choose(0)
    controller.choose(3)  # 1.8x, returning to the existing layout panel.
    assert controller.line_height == 1.8 and controller.menus == [parent, layout]
    assert layout["options"][0]["subtitle"] == "1.8×"
    controller.dispatch("back")
    assert parent["index"] == 1
