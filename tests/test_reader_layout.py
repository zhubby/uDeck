import pytest

from udeck.apps.reader.style import normalize_reader_preferences


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


def test_reader_layout_menu_hides_reflow_controls_for_pdf(reader_controller):
    controller = reader_controller
    captured = {}
    controller.current = {"format": "PDF"}
    controller.page = "document"
    controller.menu = lambda title, options: captured.update(title=str(title), options=options)

    controller.layout_menu()

    assert captured["title"] == "Reading layout"
    assert [str(label) for label, *_ in captured["options"]] == ["Background"]


def test_reader_layout_menu_exposes_reflow_controls_for_epub(reader_controller):
    controller = reader_controller
    captured = {}
    controller.current = {"format": "EPUB"}
    controller.page = "document"
    controller.menu = lambda title, options: captured.update(title=str(title), options=options)

    controller.layout_menu()

    assert [str(label) for label, *_ in captured["options"]] == [
        "Line spacing", "Font", "Content width", "Background"
    ]
