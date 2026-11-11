import os
import subprocess
import sys

import pytest
from PySide6.QtCore import QCoreApplication

from udeck.apps.browser.controller import BrowserController


@pytest.fixture
def browser(tmp_path):
    application = QCoreApplication.instance() or QCoreApplication([])
    controller = BrowserController(tmp_path, tmp_path / "settings.json")
    controller._test_application = application
    yield controller
    controller.close()


@pytest.mark.parametrize("mode", ["reading", "text", "pointer"])
def test_new_tab_starts_in_navigation_mode(browser, mode):
    browser.web_mode, browser.reading_text = mode, "Previous article"
    browser.command("new-tab")
    assert browser.web_mode == "navigation"
    assert browser.reading_text == ""
    assert browser.active_tab().url == "about:blank"


@pytest.mark.parametrize("last_tab", [False, True])
def test_closing_active_tab_does_not_cover_replacement_with_old_article(browser, last_tab):
    if not last_tab:
        browser.new_tab("https://example.org")
    browser.web_mode, browser.reading_text = "reading", "Closed article"
    browser.closeTab(browser.current_tab)
    assert browser.web_mode == "navigation"
    assert browser.reading_text == ""
    assert len(browser.web_tabs) == 1


def test_closing_background_tab_keeps_current_reading_mode(browser):
    background = browser.current_tab
    browser.new_tab("https://example.org")
    active = browser.current_tab
    browser.web_mode, browser.reading_text = "reading", "Current article"
    browser.closeTab(background)
    assert browser.current_tab == active
    assert browser.web_mode == "reading" and browser.reading_text == "Current article"


def test_new_tab_bookmarks_and_address_are_reachable_with_direction_keys(browser):
    browser.dispatch("down")
    browser.dispatch("accept")
    assert "Bookmarks" == browser.menus[-1]["title"]
    browser.dispatch("back")
    browser.dispatch("up")
    browser.dispatch("accept")
    assert "Address or search" == browser.menus[-1]["title"]


@pytest.mark.parametrize("zoom", [0.8, 1.0, 1.25, 1.5, 2.0])
def test_keyboard_clicks_links_and_inputs_at_page_zoom(tmp_path, zoom):
    result = subprocess.run(
        [sys.executable, "tests/browser_interaction_probe.py", str(tmp_path), "--zoom", str(zoom)],
        env={**os.environ, "PYTHONPATH": "src", "QT_QPA_PLATFORM": "offscreen",
             "QT_QUICK_BACKEND": "software", "QT_QUICK_CONTROLS_STYLE": "Basic"},
        capture_output=True, text=True, timeout=40,
    )
    assert result.returncode == 0, result.stdout + result.stderr
