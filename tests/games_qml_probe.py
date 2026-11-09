"""Exercise Games menus with real Qt key events, in an isolated preview."""

import json
import sys
import time
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickItem
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from shiboken6 import delete
from test_games_catalog import installed

from udeck.apps.games import GamesController
from udeck.core import ConfigStore


def run(root, language, theme):
    root.mkdir(parents=True, exist_ok=True)
    application = QApplication([])
    config = ConfigStore(root / "settings.json")
    config.data["preferences"].update(language=language, theme=theme)
    config.save()
    controller = GamesController(root / "state", root / "settings.json")
    controller.isolated = True
    definitions = {"gambatte": {"supported_extensions": "gb|gbc"},
                   "mgba": {"supported_extensions": "gb|gba|gbc"},
                   "vba_next": {"supported_extensions": "gba"},
                   "nestopia": {"supported_extensions": "nes"}}
    definitions.update({f"example_{i:03}": {"systemid": f"example-{i:03}", "supported_extensions": "rom"}
                        for i in range(100)})
    catalog = installed(root, definitions)
    controller.catalog = controller.library.catalog = catalog
    controller.store.data["preferences"] = catalog.preferences
    rom_root = root / "Games"
    for platform, name in (("gb", "Original stripes.gb"), ("gba", "Original red.gba"), ("nes", "Original tiles.nes")):
        folder = rom_root / platform
        folder.mkdir(parents=True)
        (folder / name).write_bytes(b"Original preview fixture; no commercial game")
    controller.library.configure_root(rom_root)
    engine = QQmlApplicationEngine()
    errors = []
    engine.warnings.connect(lambda warnings: errors.extend(w.toString() for w in warnings))
    engine.rootContext().setContextProperty("controller", controller)
    engine.rootContext().setContextProperty("windowed", True)
    engine.load(QUrl.fromLocalFile(str(Path(__file__).parents[1] / "src/udeck/apps/qml/Main.qml")))
    assert engine.rootObjects(), errors
    window = engine.rootObjects()[0]

    def wait(condition, seconds=8):
        deadline = time.monotonic() + seconds
        while not condition() and time.monotonic() < deadline:
            application.processEvents()
            QTest.qWait(20)
        assert condition(), json.loads(controller.snapshotJson)

    def frame(name):
        controller.publish()
        QTest.qWait(80)
        assert window.grabWindow().save(str(root / (name + ".png")))

    try:
        window.requestActivate()
        wait(lambda: not controller.library.pending)
        controller.tab = 1
        assert len(controller.rows()) == 3
        frame("library")
        controller.settings()
        frame("settings")
        controller.rom_picker()
        QTest.qWait(50)
        before = controller.library.root_path
        QTest.keyClick(window, Qt.Key.Key_Escape)
        assert controller.library.root_path == before and not controller.menus[-1].get("picker")
        wait(lambda: window.findChild(QQuickItem, "appKeys").hasActiveFocus())
        controller.core_management()
        frame("cores")
        menu_list = window.findChild(QQuickItem, "menuList")
        for _ in range(len(controller.menus[-1]["options"]) - 1):
            QTest.keyClick(window, Qt.Key.Key_Down)
        QTest.qWait(100)
        assert menu_list.property("contentY") > 0
        row = menu_list.property("currentItem")
        assert row.y() >= menu_list.property("contentY") - 1
        assert row.y() + row.height() <= menu_list.property("contentY") + menu_list.height() + 1
        controller.prompt("Search cores", controller.core_search)
        QTest.qWait(80)
        draft = window.findChild(QQuickItem, "menuDraft")
        assert draft.hasActiveFocus()
        draft.setProperty("text", "mgba")
        before = dict(catalog.preferences.get("coreEnabled", {}))
        QTest.keyClick(window, Qt.Key.Key_Return)
        QTest.qWait(100)
        assert controller.menus[-1]["title"] == "Search cores"
        assert len(controller.menus[-1]["options"]) == 1
        assert controller.store.data["preferences"].get("coreEnabled", {}) == before
        wait(lambda: window.findChild(QQuickItem, "appKeys").hasActiveFocus())
        controller.core_details("vba_next", "gba")
        QTest.qWait(80)
        QTest.keyClick(window, Qt.Key.Key_Return)
        assert catalog.preferences["coreEnabled"]["vba_next"] is True
        controller.clear_menus()
        controller.core_management()
        translated = json.loads(controller.snapshotJson)["menu"]
        assert translated["title"] == ("核心管理" if language == "zh_CN" else "Core management")
        assert not errors, errors
        print(json.dumps({"qmlErrors": errors, "language": language, "theme": theme,
                          "checks": ["picker-cancel", "focus-restore", "long-list-scroll", "return-consumed", "core-toggle"]}))
    finally:
        delete(engine)
        controller.close()


if __name__ == "__main__":
    run(Path(sys.argv[1]), sys.argv[2], sys.argv[3])
