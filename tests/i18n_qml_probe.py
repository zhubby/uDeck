"""Exercise language switching in the real shell and Terminal QML views."""

import argparse
import json
import os
import tempfile
from pathlib import Path
from types import SimpleNamespace

from PySide6.QtCore import QPointF, Qt, QUrl
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from shiboken6 import delete

from udeck import main
from udeck.controller import ShellController
from udeck.core import ConfigStore
from udeck.mock import MockBackend
from udeck.terminal.core import LaunchRequest, TerminalPreferences
from udeck.terminal.main import Coordinator


def run():
    parser = argparse.ArgumentParser()
    parser.add_argument("language", choices=("en", "zh_CN"))
    parser.add_argument("output", type=Path)
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    options = parser.parse_args()
    os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")
    application = QApplication([])
    family = next((font for font in ("Noto Sans CJK SC", "PingFang SC", "WenQuanYi Micro Hei")
                   if font in QFontDatabase.families()), application.font().family())
    application.setFont(QFont(family))
    application.setQuitOnLastWindowClosed(False)
    with tempfile.TemporaryDirectory(prefix="udeck-i18n-preview-") as directory:
        path = Path(directory)
        controller = ShellController(MockBackend(), config=ConfigStore(path / "settings.json"), mock=True)
        controller.setLanguage(options.language)
        engine = QQmlApplicationEngine()
        errors = []
        engine.warnings.connect(lambda warnings: errors.extend(w.toString() for w in warnings))
        engine.addImageProvider("desktop", main.IconProvider())
        context = engine.rootContext()
        for key, value in (("controller", controller), ("appFont", family),
                           ("windowedPreview", True), ("headlessPreview", True)):
            context.setContextProperty(key, value)
        engine.load(QUrl.fromLocalFile(str(Path(main.__file__).parent / "qml/Main.qml")))
        assert engine.rootObjects(), errors
        window = engine.rootObjects()[0]
        window.setWidth(options.width)
        window.setHeight(options.height)
        options.output.mkdir(parents=True, exist_ok=True)
        captures = []

        def capture(name, target=window):
            QTest.qWait(60)
            if target is window:
                pending = list(window.contentItem().childItems())
                footer = {}
                while pending:
                    item = pending.pop()
                    pending.extend(item.childItems())
                    if item.objectName() in ("footerControls", "footerShortcuts"):
                        footer[item.objectName()] = item
                controls, shortcuts = footer["footerControls"], footer["footerShortcuts"]
                assert controls.x() + controls.width() < shortcuts.x()
                assert shortcuts.property("implicitWidth") <= shortcuts.width() + 1
                assert shortcuts.y() + shortcuts.height() <= window.height()
            assert target.grabWindow().save(str(options.output / (name + ".png")))
            captures.append(name)

        for page in ("home", "apps", "windows", "files", "settings"):
            controller.setPage(page)
            if page == "settings":
                controller.select(next(i for i, item in enumerate(controller._items()) if item["id"] == "language"))
            capture(page)
        controller.activateSetting("language")
        capture("language")
        # Apply the other language using actual QML keyboard handling.
        QTest.keyClick(window, Qt.Key.Key_Down if options.language == "en" else Qt.Key.Key_Up)
        QTest.keyClick(window, Qt.Key.Key_Return)
        other = "zh_CN" if options.language == "en" else "en"
        assert window.property("viewState").toVariant()["language"] == other
        QTest.keyClick(window, Qt.Key.Key_Escape)
        assert controller.navigation.page == "settings" and not controller.modal
        assert controller._items()[controller.navigation.index]["id"] == "language"
        controller.setLanguage(options.language)
        controller.activateSetting("poweroff")
        capture("confirmation")
        pending = list(window.contentItem().childItems())
        panel = None
        while pending:
            item = pending.pop()
            pending.extend(item.childItems())
            if item.objectName() == "dialogPanel":
                panel = item
                break
        assert panel is not None
        origin = panel.mapToItem(window.contentItem(), QPointF(0, 0))
        assert origin.y() >= 0 and origin.y() + panel.height() <= window.height()
        controller.dispatch("back")
        controller.dispatch("search")
        QTest.qWait(30)
        controller.editText("English 中文 {literal}")
        owner = controller.modal["key"]
        controller.dispatch("quick-settings")
        controller.chooseModal(next(i for i, option in enumerate(controller.modal["options"]) if option.get("id") == "language"))
        controller.setLanguage(other)
        controller.dispatch("back")
        assert controller.modal["key"] == owner
        assert controller.modal["text"] == "English 中文 {literal}"
        controller.dispatch("back")
        controller.setLanguage(options.language)

        coordinator = Coordinator(application, SimpleNamespace(mock=True, no_input=True, windowed=True),
                                  TerminalPreferences(path / "terminal.json"), 0)
        coordinator.open(LaunchRequest(directory, [], "", {}))
        terminal = coordinator.recent["controller"]
        terminal_window = coordinator.recent["window"]
        terminal_window.setWidth(options.width)
        terminal_window.setHeight(options.height)
        terminal_id = terminal.current
        operations = []
        terminal.operate.connect(lambda *args: operations.append(args))
        terminal.command("menu")
        capture("terminal-menu", terminal_window)
        controller.setLanguage(other)
        coordinator.refresh_language()
        assert terminal.language == other
        assert terminal.current == terminal_id and not operations
        assert terminal_window.property("state").toVariant()["language"] == other
        controller.setLanguage(options.language)
        coordinator.refresh_language()
        terminal.dispatch("back")
        terminal.preparePaste("printf '设置\\n'\necho done")
        capture("terminal-paste", terminal_window)
        assert terminal.pending_text == "printf '设置\\n'\necho done"
        terminal.dispatch("back")
        terminal.requestCloseWindow()
        capture("terminal-confirmation", terminal_window)
        terminal.dispatch("back")
        terminal.command("history")
        capture("terminal-history", terminal_window)
        terminal_errors = list(coordinator.errors)
        coordinator.close()
        delete(coordinator.engine)
        delete(engine)
        controller.close()
        application.processEvents()
        print(json.dumps({"language": options.language, "captures": captures,
                          "qmlErrors": errors + terminal_errors, "sessionsPreserved": True}))


if __name__ == "__main__":
    run()
