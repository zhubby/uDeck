"""Exercise Games menus with real Qt key events, in an isolated preview."""

import json
import sys
import time
from pathlib import Path

from libretro_fixtures import configure_library
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QImage
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickItem
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from shiboken6 import delete
from test_emulator_playlists import write_playlist
from test_games_catalog import installed

from udeck.apps.emulator.controller import EmulatorController
from udeck.core import ConfigStore
from udeck.i18n import Msg, render, tr
from udeck.icons import IconProvider


def run(root, language, theme):
    root.mkdir(parents=True, exist_ok=True)
    application = QApplication([])
    config = ConfigStore(root / "settings.json")
    config.data["preferences"].update(language=language, theme=theme)
    config.save()
    controller = EmulatorController(root / "state", root / "settings.json")
    controller.isolated = True
    definitions = {"gambatte": {"supported_extensions": "gb|gbc"},
                   "mgba": {"supported_extensions": "gb|gba|gbc"},
                   "vba_next": {"supported_extensions": "gba"},
                   "nestopia": {"supported_extensions": "nes"},
                   "ppsspp": {"supported_extensions": "iso|cso"}}
    definitions.update({f"example_{i:03}": {"systemid": f"example-{i:03}", "supported_extensions": "rom",
                                           "systemname": f"ZZ fixture {i:03}"}
                        for i in range(100)})
    catalog = installed(root, definitions)
    controller.catalog = controller.library.catalog = catalog
    controller.store.data["preferences"] = catalog.preferences
    rom_root = root / "Games"
    for platform, name in (("gb", "Original stripes.gb"), ("gba", "Original red.gba"), ("nes", "Original tiles.nes")):
        folder = rom_root / platform
        folder.mkdir(parents=True)
        (folder / name).write_bytes(b"Original preview fixture; no commercial game")
    for index in range(100):
        write_playlist(root / f"playlists/ZZ fixture {index:03}.lpl", [])
    write_playlist(root / "playlists/Sony - PlayStation Portable.lpl", [])
    configure_library(controller, rom_root)
    engine = QQmlApplicationEngine()
    engine.addImageProvider("desktop", IconProvider())
    errors = []
    engine.warnings.connect(lambda warnings: errors.extend(w.toString() for w in warnings))
    engine.rootContext().setContextProperty("controller", controller)
    engine.rootContext().setContextProperty("windowed", True)
    engine.load(QUrl.fromLocalFile(str(Path(__file__).parents[1] / "src/udeck/apps/common/qml/Main.qml")))
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
        controller.setTab(1)
        assert len(controller.rows()) == 104
        grid = window.findChild(QQuickItem, "appCards")
        panel = window.findChild(QQuickItem, "selectedGamePanel")
        wait(lambda: grid.width() > window.width() * 0.9)
        assert not panel.isVisible()
        def icons():
            # GridView owns delegates through its visual tree, not the window's
            # QObject parent tree.
            found, pending = [], [window.contentItem()]
            while pending:
                item = pending.pop()
                if item.objectName() == "platformIcon":
                    found.append(item)
                pending.extend(item.childItems())
            return found
        wait(lambda: bool(icons()) and all(icon.isVisible() for icon in icons()))
        for title in ("Nintendo - Game Boy Advance", "Nintendo - Nintendo Entertainment System",
                      "Sony - PlayStation Portable"):
            controller.select(next(row["id"] for row in controller.rows() if row["title"] == title))
            QTest.qWait(80)
            card = grid.property("currentItem")
            caption = next(child for child in card.childItems() if child.inherits("QQuickColumn"))
            assert caption.y() + caption.height() <= card.height() - 9, (
                title, caption.y(), caption.height(), card.height())
        controller.select(controller.rows()[0]["id"])
        frame("platforms")
        for _ in range(34):
            QTest.keyClick(window, Qt.Key.Key_Down)
        QTest.qWait(80)
        assert grid.property("contentY") > 0
        selected_platform = controller.selected
        current_card = grid.property("currentItem")
        assert current_card.y() >= grid.property("contentY") - 1
        assert current_card.y() + current_card.height() <= grid.property("contentY") + grid.height() + 1
        QTest.keyClick(window, Qt.Key.Key_Return)
        wait(lambda: controller.platform != "All")
        QTest.keyClick(window, Qt.Key.Key_Escape)
        wait(lambda: controller.platform == "All")
        assert controller.selected == selected_platform and grid.property("contentY") > 0
        controller.search("psp")
        QTest.keyClick(window, Qt.Key.Key_Return)
        wait(lambda: json.loads(controller.snapshotJson)["playlistTitle"] == "Sony - PlayStation Portable")
        assert controller.rows() == []
        frame("empty-platform")
        QTest.keyClick(window, Qt.Key.Key_Escape)
        wait(lambda: controller.platform == "All")
        controller.search("fc")
        QTest.keyClick(window, Qt.Key.Key_Return)
        wait(lambda: json.loads(controller.snapshotJson)["playlistTitle"] == "Nintendo - Nintendo Entertainment System")
        assert [row["title"] for row in controller.rows()] == ["Original tiles"]
        wait(lambda: panel.isVisible() and grid.width() < window.width() * 0.8)
        frame("library")
        QTest.keyClick(window, Qt.Key.Key_Escape)
        wait(lambda: controller.platform == "All")
        assert controller.rows()[0]["title"] == "Nintendo - Nintendo Entertainment System" and controller.filter == "fc"
        controller.search("")
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

        def activate(title):
            rows = json.loads(controller.snapshotJson)["menu"]["options"]
            index = next(i for i, row in enumerate(rows) if row["title"] == title)
            for _ in range((index - controller.menus[-1]["index"]) % len(rows)):
                QTest.keyClick(window, Qt.Key.Key_Down)
            QTest.keyClick(window, Qt.Key.Key_Return)

        # Native save menus use the same window, real key routing and focus stack.
        controller.clear_menus()
        controller.current = next(i for i in controller.library.items if i["platform"] == "gb")
        controller.checks = {"coreId": "gambatte", "coreHash": "a" * 64, "contentHash": "b" * 64,
                             "savestate": True, "ready": True, "errors": []}
        controller.page = "game-details"
        native = rom_root / "外部存档.state7"
        native.write_bytes(b"unchanged RetroArch native bytes")
        controller.detail_menu()
        activate("存档管理" if language == "zh_CN" else "Save management")
        frame("save-management")
        activate("导入原生存档" if language == "zh_CN" else "Import native save")
        activate(native.name)
        QTest.keyClick(window, Qt.Key.Key_Down)  # Target slot 2, regardless of .state7.
        QTest.keyClick(window, Qt.Key.Key_Return)
        wait(lambda: not controller.save_jobs)
        confirmation = json.loads(controller.snapshotJson)["menu"]
        assert "Original stripes" in confirmation["body"] and "gambatte" in confirmation["body"]
        QTest.qWait(80)
        body = next(item for item in window.findChildren(QQuickItem) if item.property("text") == confirmation["body"])
        assert not body.property("truncated"), "Import target and compatibility notice must remain readable"
        assert controller.save_manager.store(controller.save_context()).manifest() == {}
        frame("save-confirmation")
        QTest.keyClick(window, Qt.Key.Key_Escape)
        assert controller.save_manager.store(controller.save_context()).manifest() == {}
        wait(lambda: window.findChild(QQuickItem, "appKeys").hasActiveFocus())
        QTest.keyClick(window, Qt.Key.Key_Return)
        QTest.keyClick(window, Qt.Key.Key_Return)
        wait(lambda: not controller.save_jobs)
        save_store = controller.save_manager.store(controller.save_context())
        assert save_store.load("2", "b" * 64, "a" * 64)[0].read_bytes() == native.read_bytes()
        activate("导出原生存档" if language == "zh_CN" else "Export native save")
        wait(lambda: not controller.save_jobs)
        QTest.keyClick(window, Qt.Key.Key_Return)
        activate("输入路径" if language == "zh_CN" else "Enter path")
        output = root / "导出"
        output.mkdir()
        wait(lambda: window.findChild(QQuickItem, "menuDraft").hasActiveFocus())
        window.findChild(QQuickItem, "menuDraft").setProperty("text", str(output))
        QTest.keyClick(window, Qt.Key.Key_Return)
        wait(lambda: not controller.save_jobs)
        assert (output / "Original stripes.state2").read_bytes() == native.read_bytes()
        activate("存档历史" if language == "zh_CN" else "Save history")
        wait(lambda: not controller.save_jobs)
        frame("save-history")
        QTest.keyClick(window, Qt.Key.Key_Return)
        QTest.keyClick(window, Qt.Key.Key_Escape)
        assert len(controller.save_manager.history.entries()) == 1
        controller.clear_menus()
        controller.settings()
        activate("备份与云同步" if language == "zh_CN" else "Backups and cloud sync")
        frame("save-settings")
        assert json.loads(controller.snapshotJson)["saveSync"]["enabled"] is False
        QTest.keyClick(window, Qt.Key.Key_Escape)
        wait(lambda: window.findChild(QQuickItem, "appKeys").hasActiveFocus())
        controller.clear_menus()

        # Standard images retain their aspect ratio, and menu choices use real keys.
        thumbnails = root / "thumbnails"
        controller.library.thumbnail_path = str(thumbnails)
        kinds = (("Named_Boxarts", 80, 120, 0xFF145766), ("Named_Snaps", 160, 90, 0xFF854322),
                 ("Named_Titles", 120, 90, 0xFF365817))
        for kind, width, height, color in kinds:
            target = thumbnails / "Nintendo - Game Boy" / kind / "Original stripes.png"
            target.parent.mkdir(parents=True)
            image = QImage(width, height, QImage.Format.Format_RGB32)
            image.fill(color)
            assert image.save(str(target))
        controller.library.reload_thumbnails()
        controller.current = next(i for i in controller.library.items if i["platform"] == "gb")
        controller.preview_images()
        activate(render(tr(Msg.EMU_SNAPSHOT), language))
        assert "/Named_Snaps/" in controller.current["cover"]
        frame("thumbnail-snapshot")
        cover = window.findChild(QQuickItem, "gameArtwork").findChild(QQuickItem, "coverImage")
        wait(lambda: cover.property("paintedHeight") > 0)
        assert abs(cover.property("paintedWidth") / cover.property("paintedHeight") - 160 / 90) < 0.02
        controller.preview_images()
        activate(render(tr(Msg.EMU_BOXART), language))
        assert "/Named_Boxarts/" in controller.current["cover"]
        frame("thumbnail-boxart")
        wait(lambda: cover.property("paintedHeight") > 0 and
             abs(cover.property("paintedWidth") / cover.property("paintedHeight") - 80 / 120) < 0.02)
        assert abs(cover.property("paintedWidth") / cover.property("paintedHeight") - 80 / 120) < 0.02

        # A scan is previewed before any list changes, and Back cancels it.
        added = rom_root / "gb/Added preview.gb"
        added.write_bytes(b"original preview only")
        playlist = Path(controller.library.playlist_path) / "Nintendo - Game Boy.lpl"
        before = playlist.read_bytes()
        controller.settings()
        activate(render(tr(Msg.EMU_GENERATE_PLAYLISTS), language))
        wait(lambda: controller.library_task is None)
        assert "Added preview.gb" in str(controller.menus[-1]["body"])
        frame("scan-preview")
        QTest.keyClick(window, Qt.Key.Key_Escape)
        assert playlist.read_bytes() == before
        activate(render(tr(Msg.EMU_GENERATE_PLAYLISTS), language))
        wait(lambda: controller.library_task is None)
        QTest.keyClick(window, Qt.Key.Key_Return)
        wait(lambda: controller.library_task is None and not controller.library.pending)
        assert any(i["label"] == "Added preview" for i in json.loads(playlist.read_text())["items"])

        # The three directory pickers have independent state and restore focus.
        controller.settings()
        for key in ("playlistDirectory", "thumbnailDirectory"):
            before = (controller.library.playlist_path, controller.library.thumbnail_path)
            controller.library_directory_picker(key)
            QTest.keyClick(window, Qt.Key.Key_Escape)
            assert (controller.library.playlist_path, controller.library.thumbnail_path) == before
            wait(lambda: window.findChild(QQuickItem, "appKeys").hasActiveFocus())
        assert not errors, errors
        print(json.dumps({"qmlErrors": errors, "language": language, "theme": theme,
                          "checks": ["platforms", "platform-scroll-back", "empty-platform", "two-level-back", "platform-icons", "picker-cancel",
                                     "focus-restore", "long-list-scroll", "return-consumed", "core-toggle",
                                     "native-import-confirm-cancel", "native-slot-mapping", "native-export",
                                     "save-history-restore-cancel", "save-settings-focus", "thumbnail-aspect-selection",
                                     "scan-preview-cancel-commit", "independent-directory-pickers"]}))
    finally:
        delete(engine)
        controller.close()


if __name__ == "__main__":
    run(Path(sys.argv[1]), sys.argv[2], sys.argv[3])
