"""Render both themes and exercise live global changes in all native windows."""

import argparse
import json
import os
import tempfile
import time
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

from PySide6.QtCore import QObject, Qt, QUrl
from PySide6.QtGui import QFont, QFontInfo
from PySide6.QtQml import QQmlApplicationEngine, QQmlEngine, QQmlExpression
from PySide6.QtQuick import QQuickItem
from PySide6.QtTest import QTest
from PySide6.QtWebEngineQuick import QtWebEngineQuick
from PySide6.QtWidgets import QApplication
from shiboken6 import delete

from udeck import main
from udeck.apps.common.state import AppState
from udeck.apps.main import make_controller
from udeck.apps.media.engine import FrameImages
from udeck.apps.reader.controller import PdfImages
from udeck.controller import ShellController
from udeck.core import ConfigStore
from udeck.i18n import Msg, tr
from udeck.mock import MockBackend
from udeck.terminal.core import LaunchRequest, TerminalPreferences
from udeck.terminal.main import Coordinator


def run():
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--language", choices=("en", "zh_CN"), default="en")
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    options = parser.parse_args()
    os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")
    QtWebEngineQuick.initialize()
    application = QApplication([])
    application.setQuitOnLastWindowClosed(False)
    options.output.mkdir(parents=True, exist_ok=True)
    errors, captures, apps = [], [], []

    def wait(condition):
        deadline = time.monotonic() + 8
        while not condition() and time.monotonic() < deadline:
            QTest.qWait(20)
        assert condition(), errors

    def capture(window, name):
        QTest.qWait(80)
        verify_fonts(window, options.language)
        verify_prompts(window)
        assert window.grabWindow().save(str(options.output / (name + ".png")))
        captures.append(name)

    def verify_prompts(window):
        expression = QQmlExpression(QQmlEngine.contextForObject(window), window, """
            JSON.stringify((function() {
                const icons = []
                function visit(item) {
                    if (!item.visible) return
                    if (item.objectName === "inputPromptIcon") {
                        const point = item.mapToItem(contentItem, 0, 0)
                        icons.push({key: item.keyId, status: item.status,
                                    source: item.source.toString(),
                                    x: point.x, y: point.y,
                                    width: item.width, height: item.height})
                    }
                    for (let child of item.children) visit(child)
                }
                visit(contentItem)
                return icons
            })())
        """)
        value, undefined = expression.evaluate()
        assert not undefined and not expression.hasError(), expression.error().toString()
        icons = json.loads(value)
        assert icons, (window.title(), "Missing Kenney input prompts")
        for icon in icons:
            assert icon["status"] == 1, icon
            assert "/assets/input-prompts/" in icon["source"], icon
            assert icon["width"] >= 24 and icon["height"] >= 24, icon
            assert icon["x"] >= -1 and icon["y"] >= -1, icon
            assert icon["x"] + icon["width"] <= window.width() + 1, icon
            assert icon["y"] + icon["height"] <= window.height() + 1, icon
        return icons

    def verify_fonts(window, language):
        expected = "LXGW WenKai Screen" if language == "zh_CN" else "Saira SemiCondensed"
        assert window.property("fontFamily") == expected, (window.title(), window.property("fontFamily"), expected)
        # Walk native Quick/WebEngine items inside QML: creating Python wrappers
        # for private WebEngine visual children crashes PySide 6.8 on macOS.
        expression = QQmlExpression(QQmlEngine.contextForObject(window), window, """
            JSON.stringify((function() {
                const fonts = []
                function visit(item) {
                    if (!item.visible) return
                    if (item.font !== undefined && item.text !== undefined)
                        fonts.push({name: item.objectName, text: String(item.text), family: item.font.family})
                    for (let child of item.children) visit(child)
                }
                visit(contentItem)
                return fonts
            })())
        """)
        value, undefined = expression.evaluate()
        assert not undefined and not expression.hasError(), expression.error().toString()
        families = json.loads(value)
        terminal = [item for item in families if item["name"] == "terminalContent"]
        terminal_family = "LXGW WenKai Mono" if language == "zh_CN" else "JetBrains Mono"
        assert all(item["family"] == terminal_family for item in terminal), terminal
        interface = [item for item in families if item["name"] != "terminalContent" and item["family"] != "monospace"]
        assert interface
        assert all(item["family"] == expected for item in interface), (window.title(), interface, expected)
        assert QFontInfo(QFont(expected)).family() == expected

    def engine_for(controller, path, shell=False):
        engine = QQmlApplicationEngine()
        engine.addImageProvider("desktop", main.IconProvider())
        engine.warnings.connect(lambda warnings: errors.extend(w.toString() for w in warnings))
        context = engine.rootContext()
        context.setContextProperty("controller", controller)
        if shell:
            context.setContextProperty("windowedPreview", True)
            context.setContextProperty("headlessPreview", True)
        else:
            context.setContextProperty("windowed", True)
            if controller.app in ("music", "video"):
                engine.addImageProvider("video", FrameImages(controller))
            elif controller.app == "reader":
                engine.addImageProvider("pdf", PdfImages(controller))
        engine.load(QUrl.fromLocalFile(str(path)))
        assert engine.rootObjects(), errors
        window = engine.rootObjects()[0]
        window.setWidth(options.width)
        window.setHeight(options.height)
        return engine, window

    def text_field(window):
        return next(item for item in window.findChildren(QObject)
                    if item.inherits("QQuickTextField") and item.property("visible"))

    def verify_colors(window, theme):
        expected = "#0b0e12" if theme == "dark" else "#151719" if window.title() == "uDeck" else None
        if expected:
            assert window.color().name() == expected
        colors = window.findChild(QObject, "themeColors")
        assert colors.property("theme") == theme

        # Sample the rendered badge itself, including when a modal covers its
        # header. A fixed-color SVG or a missed theme binding must fail here.
        logos = [item for item in window.findChildren(QQuickItem, "brandLogo") if item.isVisible()]
        assert logos, (window.title(), "Missing visible brand logo")
        foreground = colors.property("text" if theme == "dark" else "accent")
        background = colors.property("background")
        for logo in logos:
            QTest.qWait(40)
            result = logo.grabToImage()
            assert result
            wait(lambda result=result: not result.image().isNull())
            image = result.image()
            for name, expected in (("foreground", foreground), ("background", background)):
                matches = sum(
                    pixel.alpha() > 240 and max(abs(a - b) for a, b in zip(
                        (pixel.red(), pixel.green(), pixel.blue()),
                        (expected.red(), expected.green(), expected.blue()), strict=True)) <= 4
                    for y in range(image.height()) for x in range(image.width())
                    for pixel in (image.pixelColor(x, y),)
                )
                assert matches > image.width() * image.height() * 0.06, (
                    window.title(), theme, name, expected.name(), matches)

        def luminance(color):
            rgb = [color.redF(), color.greenF(), color.blueF()]
            return sum((c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4) * weight
                       for c, weight in zip(rgb, (0.2126, 0.7152, 0.0722), strict=True))

        def contrast(a, b):
            low, high = sorted((luminance(colors.property(a)), luminance(colors.property(b))))
            return (high + 0.05) / (low + 0.05)

        for surface in ("background", "panel", "dialog", "selected"):
            for text in ("text", "muted"):
                assert contrast(text, surface) >= 4.5, (theme, text, surface)
            assert contrast("accent", surface) >= 3
            if theme == "dark":
                assert contrast("border", surface) >= 3

    root = Path(main.__file__).parent
    with tempfile.TemporaryDirectory(prefix="udeck-theme-preview-") as directory:
        path = Path(directory)
        config_path = path / "settings.json"
        shell = ShellController(MockBackend(), config=ConfigStore(config_path), mock=True)
        shell.setLanguage(options.language)
        engine, window = engine_for(shell, root / "qml/Main.qml", shell=True)
        shell.setPage("settings")
        position = next(i for i, item in enumerate(shell._items()) if item["id"] == "theme")
        shell.select(position)
        shell.dispatch("accept")
        QTest.qWait(50)
        owner = shell.modal["key"]
        QTest.keyClick(window, Qt.Key.Key_Down)
        QTest.keyClick(window, Qt.Key.Key_Return)
        assert shell.theme == "dark" and shell.modal["key"] == owner
        verify_colors(window, "dark")
        QTest.keyClick(window, Qt.Key.Key_Escape)
        assert shell.navigation.index == position and not shell.modal
        listing = window.findChild(QObject, "itemList")
        QTest.qWait(30)
        listing.setProperty("contentY", listing.property("contentY") + 30)
        scroll = listing.property("contentY")
        shell.setTheme("classic")
        QTest.qWait(30)
        assert abs(listing.property("contentY") - scroll) < 1, (scroll, listing.property("contentY"))

        coordinator = Coordinator(application, SimpleNamespace(mock=True, no_input=True, windowed=True),
                                  TerminalPreferences(path / "terminal.json"), 0)
        # Production apps are separate processes. The terminal's pointer guard
        # must not wrap foreign WebEngine/Quick Controls objects in this harness.
        application.removeEventFilter(coordinator)
        for _ in range(2):
            coordinator.open(LaunchRequest(str(path), [], "", {}, new_window=True))
        terminal_ids = [entry["controller"].current for entry in coordinator.windows]
        for index, entry in enumerate(coordinator.windows):
            entry["window"].setWidth(options.width)
            entry["window"].setHeight(options.height)
            if index:
                entry["controller"].preparePaste("printf 'keep 中文'\necho done")
            else:
                entry["controller"].command("menu")
        terminal_before = [json.loads(e["controller"].snapshotJson) for e in coordinator.windows]
        for app in ("music", "video", "browser", "reader", "emulator"):
            if app == "emulator":
                # A visual theme test must not scan the host's ROM collection
                # or race the inventory of its installed libretro cores.
                state = AppState(app, path / app)
                state.data["preferences"].update(romRoot=str(path / "Games"),
                                                 coreDirectory=str(path / "cores"))
                state.save()
            controller = make_controller(app, path / app, config_path)
            controller.isolated = True
            app_engine, app_window = engine_for(controller, root / "apps/common/qml/Main.qml")
            controller.window = app_window
            controller.start()
            apps.append((controller, app_engine, app_window))
            if app == "emulator":
                wait(lambda controller=controller: not controller.core_tasks and not controller.library.pending)

        app_before = {}
        for theme in ("classic", "dark"):
            shell.setTheme(theme)
            wait(lambda theme=theme: all(c.theme == theme for c, _, _ in apps) and coordinator.theme == theme)
            for page in ("home", "settings"):
                shell.setPage(page)
                if page == "settings":
                    shell.select(position)
                capture(window, f"shell-{theme}-{page}")
            shell.activateSetting("theme")
            capture(window, f"shell-{theme}-theme")
            shell.dispatch("back")
            shell.activateSetting("poweroff")
            capture(window, f"shell-{theme}-confirmation")
            shell.dispatch("back")
            verify_colors(window, theme)
            for controller, _, app_window in apps:
                if theme == "dark":
                    before = deepcopy(app_before[controller.app])
                    after = controller.snapshot()
                    before.pop("theme")
                    after.pop("theme")
                    assert before == after
                    field = text_field(app_window)
                    assert field.property("text") == "keep 中文 {draft}"
                    assert field.property("cursorPosition") == 4
                    controller.pop_menu()
                verify_colors(app_window, theme)
                capture(app_window, f"{controller.app}-{theme}-library")
                controller.prompt(tr(Msg.FOLDER_PATH), lambda _: None, "keep 中文 {draft}")
                QTest.qWait(30)
                field = text_field(app_window)
                field.setProperty("cursorPosition", 4)
                assert field.property("color").name() == app_window.findChild(QObject, "themeColors").property("text").name()
                capture(app_window, f"{controller.app}-{theme}-input")
                app_before[controller.app] = deepcopy(controller.snapshot())
            for index, entry in enumerate(coordinator.windows):
                terminal, terminal_window = entry["controller"], entry["window"]
                assert terminal.current == terminal_ids[index]
                before, after = deepcopy(terminal_before[index]), json.loads(terminal.snapshotJson)
                before.pop("theme")
                after.pop("theme")
                assert after.pop("colorScheme") == ("udeck-dark" if theme == "dark" else "udeck")
                before.pop("colorScheme")
                assert after.pop("themeLabel")
                before.pop("themeLabel")
                assert before == after
                verify_colors(terminal_window, theme)
                capture(terminal_window, f"terminal-{theme}-{'paste' if index else 'menu'}")

        menu_scrolls = []
        for controller, _, app_window in apps:
            controller.pop_menu()
            controller.menu("Long menu", [(f"Option {index}", lambda: None) for index in range(16)])
            controller.menus[-1]["index"] = 8
            controller.publish()
            QTest.qWait(40)
            menu = app_window.findChild(QObject, "menuList")
            menu.setProperty("contentY", menu.property("contentY") + 15)
            menu_scrolls.append((menu, menu.property("contentY")))
        shell.setTheme("classic")
        wait(lambda: all(c.theme == "classic" for c, _, _ in apps))
        for menu, scroll in menu_scrolls:
            assert abs(menu.property("contentY") - scroll) < 1
        shell.setTheme("dark")
        shell.activateSetting("wifi")
        capture(window, "shell-dark-wifi")
        shell.dispatch("back")
        shell._text_prompt(tr(Msg.WI_FI_PASSWORD), "A very long wireless network name 中文", "wifi", secret=True)
        QTest.qWait(30)
        editor = text_field(window)
        editor.setProperty("text", "keep secret 中文")
        editor.setProperty("cursorPosition", 4)
        capture(window, "shell-dark-password")
        shell.setTheme("classic")
        assert text_field(window) is editor and editor.property("cursorPosition") == 4
        assert editor.property("text") == "keep secret 中文"
        shell.dispatch("back")

        # Existing windows adopt fonts when the shared language changes, without
        # replacing their input fields, content surfaces or Terminal sessions.
        for controller, _, _ in apps:
            controller.pop_menu()
            controller.prompt(tr(Msg.FOLDER_PATH), lambda _: None, "keep 中文 {draft}")
        QTest.qWait(40)
        editors = [text_field(app_window) for _, _, app_window in apps]
        surfaces = [app_window.findChild(QObject, "appSurface") for _, _, app_window in apps]
        assert all(surfaces)
        loaded = [surface.property("item") for surface in surfaces]
        for language in ("zh_CN" if options.language == "en" else "en", options.language):
            shell.setLanguage(language)
            wait(lambda language=language: all(c.language == language for c, _, _ in apps) and coordinator.language == language)
            verify_fonts(window, language)
            for index, (_, _, app_window) in enumerate(apps):
                verify_fonts(app_window, language)
                assert text_field(app_window) is editors[index]
                assert app_window.findChild(QObject, "appSurface") is surfaces[index]
                assert surfaces[index].property("item") is loaded[index]
                assert editors[index].property("text") == "keep 中文 {draft}"
            for index, entry in enumerate(coordinator.windows):
                verify_fonts(entry["window"], language)
                assert entry["controller"].current == terminal_ids[index]
        browser, _, browser_window = next(entry for entry in apps if entry[0].app == "browser")
        browser.pop_menu()
        browser.set_mode("pointer")
        capture(browser_window, "browser-classic-pointer")
        assert any(icon["key"] == "mouse_left" for icon in verify_prompts(browser_window))
        coordinator.windows[0]["controller"].command("history")
        capture(coordinator.windows[0]["window"], "terminal-classic-history")
        for controller, app_engine, app_window in apps:
            controller.close()
            app_window.setProperty("allowClose", True)
            app_window.close()
            delete(app_engine)
        errors.extend(coordinator.errors)
        coordinator.close()
        delete(coordinator.engine)
        delete(engine)
        shell.close()
    assert not errors, errors
    print(json.dumps({"captures": captures, "qmlErrors": errors, "liveWindows": 8,
                      "sessionsPreserved": True, "nativeSessions": False}))


if __name__ == "__main__":
    run()
