import pytest

from udeck.apps.reader_style import normalize_reader_preferences


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


def test_reader_layout_menu_hides_reflow_controls_for_pdf():
    pytest.importorskip("PySide6")
    from udeck.apps.reader import ReaderController

    controller = object.__new__(ReaderController)
    captured = {}
    controller.current = {"format": "PDF"}
    controller.page = "document"
    controller.menu = lambda title, options: captured.update(title=str(title), options=options)

    controller.layout_menu()

    assert captured["title"] == "Reading layout"
    assert [str(label) for label, _ in captured["options"]] == ["Background"]


def test_reader_layout_menu_exposes_reflow_controls_for_epub():
    pytest.importorskip("PySide6")
    from udeck.apps.reader import ReaderController

    controller = object.__new__(ReaderController)
    captured = {}
    controller.current = {"format": "EPUB"}
    controller.page = "document"
    controller.menu = lambda title, options: captured.update(title=str(title), options=options)

    controller.layout_menu()

    assert [str(label) for label, _ in captured["options"]] == [
        "Line spacing", "Font", "Content width", "Background"
    ]
