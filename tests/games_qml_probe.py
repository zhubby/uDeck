"""Exercise Games menus with real Qt key events, in an isolated preview."""

import json
import sys
import time
from pathlib import Path
from urllib.parse import unquote

from libretro_fixtures import configure_library
from PySide6.QtCore import QEventLoop, QPoint, QPointF, Qt, QTimer, QUrl
from PySide6.QtGui import QImage, QWheelEvent
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickItem
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from shiboken6 import delete
from test_emulator_playlists import entry, write_playlist
from test_games_catalog import installed

from udeck.apps.emulator.controller import EmulatorController
from udeck.core import ConfigStore
from udeck.i18n import Msg, render, tr
from udeck.icons import IconProvider


def pump(milliseconds):
    loop = QEventLoop()
    QTimer.singleShot(milliseconds, loop.quit)
    loop.exec()


def run(root, language, theme, mode="menus"):
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
    if mode == "info":
        (rom_root / "gba/Unplayed.gba").write_bytes(b"Original unplayed preview fixture")
        catalog.preferences["coreEnabled"] = {"vba_next": True}
        write_playlist(root / "playlists/Mixed.lpl", [
            entry(rom_root / "gba/Original red.gba", "Alternative label", "Nintendo - Game Boy Advance.lpl",
                  core_path=str(root / "cores/vba_next_libretro.so")),
            entry(rom_root / "gb/Original stripes.gb", "GB")])
    long_name = "A long adventure - 漫长的冒险旅程\nDeluxe edition"
    title_platforms = (("Nintendo - Game Boy", "gb", "gb"),
                       ("Nintendo - Game Boy Color", "gbc", "gbc"),
                       ("Nintendo - Game Boy Advance", "gba", "gba"),
                       ("Nintendo - Nintendo Entertainment System", "nes", "nes"),
                       ("Sony - PlayStation Portable", "psp", "cso"))
    if mode == "titles":
        for _, platform, extension in title_platforms:
            folder = rom_root / platform
            folder.mkdir(exist_ok=True)
            (folder / (long_name + "." + extension)).write_bytes(b"Original long-name preview fixture")
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
            pump(20)
        assert condition(), json.loads(controller.snapshotJson)

    def frame(name):
        controller.publish()
        pump(80)
        assert window.grabWindow().save(str(root / (name + ".png")))

    def platform_artwork(owner, icon, *, covered=False):
        fallback = owner.findChild(QQuickItem, "fallbackPlatformIcon")
        assert fallback is not None, "Games without artwork must display a platform icon"
        cover = owner.findChild(QQuickItem, "coverImage")
        wait(lambda: fallback.isVisible() != covered and cover.isVisible() == covered)
        if not covered:
            wait(lambda: fallback.property("paintedWidth") > 0)
        assert fallback.property("source").toString().endswith("/platform-icons/" + icon + ".svg")

    try:
        window.requestActivate()
        wait(lambda: not controller.library.pending)
        controller.setTab(1)
        grid = window.findChild(QQuickItem, "appCards")
        panel = window.findChild(QQuickItem, "selectedGamePanel")
        if mode == "info":
            controller.select(next(row["id"] for row in controller.rows() if row["title"] == "Nintendo - Game Boy Advance"))
            QTest.keyClick(window, Qt.Key.Key_Return)
            wait(lambda: not json.loads(controller.snapshotJson)["platformsView"])
            game = next(row for row in controller.rows() if row["title"] == "Original red")
            controller.store.data["positions"][game["gameId"]] = {"seconds": 7380, "lastPlayed": 1794720000}
            controller.store.data["recent"] = [game["gameId"]]
            controller.select(game["id"])
            controller.publish()
            info = panel.findChild(QQuickItem, "selectedGameInfo")
            body = panel.findChild(QQuickItem, "selectedGameBody")
            info_views = {}

            def info_item(name):
                pending = [info]
                while pending:
                    child = pending.pop()
                    if child.objectName() == name:
                        return child
                    pending.extend(child.childItems())

            def field(key):
                view = info_item("gameInfoValue_" + key)
                # Keep the parent wrapper alive while inspecting its Text child.
                info_views[key] = view
                return view.findChild(QQuickItem, "cardTitleText")

            wait(lambda: info_item("gameInfoValue_playTime") is not None)
            wait(lambda: field("playTime").property("text") == ("2 h 3 min" if language == "en" else "2 小时 3 分钟"))
            assert field("system").property("text") == "Game Boy Advance · GBA"
            assert field("core").property("text") == "mgba"
            assert field("lastPlayed").property("text").startswith("2026-11-15")
            wait(lambda: body.height() > body.property("contentHeight"))
            assert field("playTime").mapToScene(QPointF(0, field("playTime").height())).y() <= body.mapToScene(QPointF(0, body.height())).y()
            frame("selected-game-info")
            QTest.keyClick(window, Qt.Key.Key_Right)
            wait(lambda: controller.selectedItem["title"] == "Unplayed")
            assert field("lastPlayed").property("text") == ("Not played yet" if language == "en" else "尚未游玩")
            assert field("playTime").property("text") == ("0 min" if language == "en" else "0 分钟")
            frame("selected-game-unplayed")
            QTest.keyClick(window, Qt.Key.Key_Left)
            wait(lambda: controller.selected == game["id"])
            del controller.store.data["positions"][game["gameId"]]["lastPlayed"]
            controller.publish()
            wait(lambda: field("lastPlayed").property("text") == ("Time not recorded" if language == "en" else "时间未记录"))
            frame("selected-game-legacy-time")
            QTest.keyClick(window, Qt.Key.Key_Return)
            wait(lambda: json.loads(controller.snapshotJson)["page"] == "game-details")
            QTest.keyClick(window, Qt.Key.Key_Escape)
            wait(lambda: json.loads(controller.snapshotJson)["page"] == "library")
            assert controller.selected == game["id"] and window.activeFocusItem().objectName() == "appKeys"
            QTest.keyClick(window, Qt.Key.Key_Escape)
            wait(lambda: json.loads(controller.snapshotJson)["platformsView"])
            assert not panel.isVisible()
            controller.select(next(row["id"] for row in controller.rows() if row["title"] == "Mixed"))
            QTest.keyClick(window, Qt.Key.Key_Return)
            wait(lambda: not json.loads(controller.snapshotJson)["platformsView"])
            controller.select(next(row["id"] for row in controller.rows() if row["title"] == "Alternative label"))
            wait(lambda: field("core").property("text") == "vba_next")
            assert field("playTime").property("text") == ("2 h 3 min" if language == "en" else "2 小时 3 分钟")
            catalog.cores["vba_next"].name = "A very long core name that must stay on a single line"
            controller.publish()
            wait(lambda: field("core").x() < -5)
            assert field("core").property("lineCount") == 1
            QTest.keyClick(window, Qt.Key.Key_F3)
            wait(lambda: field("core").x() == 0)
            QTest.keyClick(window, Qt.Key.Key_Escape)
            for width, height in ((960, 600), (800, 500)):
                window.resize(width, height)
                pump(100)
                if body.property("interactive"):
                    position = body.mapToScene(QPointF(body.width() / 2, body.height() / 2))
                    QTest.mouseMove(window, position.toPoint())
                    pump(80)
                    for _ in range(8):
                        wheel = QWheelEvent(position, window.mapToGlobal(position.toPoint()), QPoint(), QPoint(0, -120),
                                            Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
                                            Qt.ScrollPhase.NoScrollPhase, False)
                        application.sendEvent(window, wheel)
                        pump(150)
                        if body.property("contentY") >= body.property("contentHeight") - body.height() - 1:
                            break
                    try:
                        wait(lambda: body.property("contentY") >= body.property("contentHeight") - body.height() - 1)
                    except AssertionError:
                        frame("scroll-error")
                        raise AssertionError({"width": width, "height": body.height(),
                                              "contentHeight": body.property("contentHeight"),
                                              "contentY": body.property("contentY"),
                                              "originY": body.property("originY"),
                                              "atYEnd": body.property("atYEnd"),
                                              "contentItemHeight": body.property("contentItem").height(),
                                              "position": [position.x(), position.y()]}) from None
                    assert field("playTime").mapToScene(QPointF(0, field("playTime").height())).y() <= body.mapToScene(QPointF(0, body.height())).y() + 1
                else:
                    assert body.property("contentHeight") <= body.height() + 1
                frame(f"selected-game-info-{width}")
                assert window.activeFocusItem().objectName() == "appKeys"
            assert not errors, errors
            print(json.dumps({"qmlErrors": errors, "language": language, "theme": theme,
                              "checks": ["selected-game-metadata", "unplayed-and-legacy-history",
                                         "shared-game-entry-specific-core", "single-line-long-metadata",
                                         "menu-and-back-focus", "compact-viewport-and-wheel-scroll"]}))
            return
        assert len(controller.rows()) == (105 if mode == "titles" else 104)
        if mode == "titles":
            tested_platforms = []
            for database, platform, _ in title_platforms:
                controller.select(next(row["id"] for row in controller.rows() if row["title"] == database))
                QTest.keyClick(window, Qt.Key.Key_Return)
                wait(lambda: not json.loads(controller.snapshotJson)["platformsView"])
                game = next(row for row in controller.rows() if row["title"] == long_name)
                controller.select(game["id"])
                QTest.qWait(80)
                card = grid.property("currentItem")
                icon = "gb" if platform == "gbc" else platform
                platform_artwork(card, icon)
                platform_artwork(panel, icon)
                title_view = card.findChild(QQuickItem, "cardTitleViewport")
                title_text = title_view.findChild(QQuickItem, "cardTitleText")
                wait(lambda label=title_text: label.x() < -5)
                assert title_text.property("lineCount") == 1
                assert "\n" not in title_text.property("text")
                side_title = window.findChild(QQuickItem, "selectedGameTitle")
                side_text = side_title.findChild(QQuickItem, "cardTitleText")
                wait(lambda label=side_text: label.x() < -5)
                assert side_text.property("lineCount") == 1 and "\n" not in side_text.property("text")
                caption = next(child for child in card.childItems() if child.inherits("QQuickColumn"))
                assert caption.y() + caption.height() <= card.height() - 9
                if platform == "gba":
                    frame("game-title-scrolling")
                    wait(lambda label=title_text, view=title_view: label.x() <= view.width() - label.width() + 1,
                         seconds=12)
                    frame("game-title-end")
                    controller.store.data["favorites"] = [game["gameId"]]
                    controller.store.data["recent"] = [game["gameId"]]
                    original = next(row for row in controller.rows() if row["title"] == "Original red")
                    controller.select(original["id"])
                    QTest.qWait(80)
                    assert side_text.x() == 0
                    QTest.qWait(1300)
                    assert side_text.x() == 0 and side_text.property("text") == "Original red"
                    controller.select(game["id"])
                    QTest.qWait(80)
                    assert side_text.x() == 0
                tested_platforms.append(platform)
                QTest.keyClick(window, Qt.Key.Key_Escape)
                wait(lambda: json.loads(controller.snapshotJson)["platformsView"])

            # Custom playlists keep each game's platform, including an unknown
            # platform. Neither the playlist name nor the preceding selection
            # may choose the placeholder for the next game.
            unknown = rom_root / "Mystery.odd"
            unknown.write_bytes(b"Original unknown-system preview fixture")
            mixed = root / "playlists/ZZ fixture 000.lpl"
            write_playlist(mixed, [entry(rom_root / "gb/Original stripes.gb", "GB"),
                                   entry(rom_root / "nes/Original tiles.nes", "NES",
                                         "Nintendo - Nintendo Entertainment System.lpl"),
                                   entry(unknown, "Unknown", "Unregistered system.lpl")])
            controller.library.refresh()
            wait(lambda: not controller.library.pending)
            controller.select(next(row["id"] for row in controller.rows() if row["title"] == "ZZ fixture 000"))
            QTest.keyClick(window, Qt.Key.Key_Return)
            for label, icon in (("GB", "gb"), ("NES", "nes"), ("Unknown", "generic")):
                controller.select(next(row["id"] for row in controller.rows() if row["title"] == label))
                QTest.qWait(80)
                platform_artwork(grid.property("currentItem"), icon)
                platform_artwork(panel, icon)
            frame("mixed-platform-placeholders")

            controller.select(next(row["id"] for row in controller.rows() if row["title"] == "GB"))
            image_path = root / "thumbnails/Nintendo - Game Boy/Named_Boxarts/Original stripes.png"
            image_path.parent.mkdir(parents=True, exist_ok=True)
            image = QImage(80, 120, QImage.Format.Format_RGB32)
            image.fill(0xFF145766)
            assert image.save(str(image_path))
            controller.library.reload_thumbnails()
            wait(lambda: bool(controller.selectedItem.get("cover")))
            platform_artwork(grid.property("currentItem"), "gb", covered=True)
            platform_artwork(panel, "gb", covered=True)
            frame("cover-before-placeholder")
            QTest.keyClick(window, Qt.Key.Key_Return)
            wait(lambda: window.findChild(QQuickItem, "gameArtwork") is not None)
            details = window.findChild(QQuickItem, "gameArtwork")
            platform_artwork(details, "gb", covered=True)
            QTest.keyClick(window, Qt.Key.Key_Escape)

            image_path.write_bytes(b"Intentionally invalid image fixture")
            # Use a fresh URL so Qt's image cache cannot reuse the valid cover.
            broken_path = image_path.with_suffix(".jpg")
            image_path.rename(broken_path)
            controller.library.reload_thumbnails()
            platform_artwork(grid.property("currentItem"), "gb")
            platform_artwork(panel, "gb")
            QTest.keyClick(window, Qt.Key.Key_Return)
            platform_artwork(details, "gb")
            frame("invalid-cover-platform-fallback")
            expected_errors = [error for error in errors if str(broken_path) in unquote(error)]
            assert expected_errors, "The corrupt cover must be attempted before falling back"
            errors[:] = [error for error in errors if error not in expected_errors]
            QTest.keyClick(window, Qt.Key.Key_Escape)
            QTest.keyClick(window, Qt.Key.Key_Escape)
            for tab in (0, 2):
                controller.setTab(tab)
                wait(lambda: len(controller.rows()) == 1)
                QTest.qWait(80)
                card = grid.property("currentItem")
                title_view = card.findChild(QQuickItem, "cardTitleViewport")
                title_text = title_view.findChild(QQuickItem, "cardTitleText")
                side_title = window.findChild(QQuickItem, "selectedGameTitle")
                side_text = side_title.findChild(QQuickItem, "cardTitleText")
                wait(lambda label=title_text, side=side_text: label.x() < -5 and side.x() < -5)
                assert title_text.property("lineCount") == side_text.property("lineCount") == 1
                platform_artwork(card, "gba")
                platform_artwork(panel, "gba")
            QTest.keyClick(window, Qt.Key.Key_F3)
            wait(lambda: title_text.x() == side_text.x() == 0)
            QTest.qWait(1300)
            assert title_text.x() == side_text.x() == 0
            QTest.keyClick(window, Qt.Key.Key_Escape)
            wait(lambda: title_text.x() < -5 and side_text.x() < -5)
            frame("favorite-title-scrolling")
            assert not errors, errors
            print(json.dumps({"qmlErrors": errors, "expectedInvalidImageErrors": len(expected_errors),
                              "language": language, "theme": theme,
                              "platforms": tested_platforms,
                              "checks": ["all-platform-game-title-scroll", "single-line-newline-label",
                                         "selected-sidebar-scroll-reset", "recent-favorite-title-scroll",
                                         "menu-scroll-reset", "platform-placeholders-card-sidebar-details",
                                         "mixed-platform-and-unknown-placeholders", "cover-precedence-invalid-fallback"]}))
            return
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
        card_geometry = []
        for title in ("Nintendo - Game Boy", "Nintendo - Game Boy Advance",
                      "Nintendo - Nintendo Entertainment System", "Sony - PlayStation Portable",
                      "ZZ fixture 000"):
            controller.select(next(row["id"] for row in controller.rows() if row["title"] == title))
            QTest.qWait(80)
            card = grid.property("currentItem")
            caption = next(child for child in card.childItems() if child.inherits("QQuickColumn"))
            assert caption.y() + caption.height() <= card.height() - 9, (
                title, caption.y(), caption.height(), card.height())
            icon = card.findChild(QQuickItem, "platformIcon")
            card_geometry.append((icon.width(), icon.height(), caption.y(), caption.height()))
        assert all(geometry == card_geometry[0] for geometry in card_geometry), card_geometry

        # Long titles reveal their full text without resizing artwork or moving
        # the game count. Selection and menus stop/reset the animation.
        controller.select(next(row["id"] for row in controller.rows()
                               if row["title"] == "Nintendo - Nintendo Entertainment System"))
        QTest.qWait(80)
        card = grid.property("currentItem")
        title_view = card.findChild(QQuickItem, "cardTitleViewport")
        title_text = title_view.findChild(QQuickItem, "cardTitleText")
        assert title_view.clip() and title_text.property("implicitWidth") > title_view.width()
        frame("playlist-title-start")
        QTest.qWait(250)
        assert title_text.x() == 0, "Give the selected title time to be read before scrolling"
        wait(lambda: title_text.x() < -10)
        wait(lambda: title_text.x() <= title_view.width() - title_text.width() + 1, seconds=12)
        frame("playlist-title-end")
        QTest.keyClick(window, Qt.Key.Key_F3)
        wait(lambda: title_text.x() == 0)
        QTest.qWait(1300)
        assert title_text.x() == 0, "Titles must stay still behind menus"
        QTest.keyClick(window, Qt.Key.Key_Escape)
        wait(lambda: title_text.x() < -10)
        QTest.keyClick(window, Qt.Key.Key_Right)
        wait(lambda: title_text.x() == 0)
        QTest.qWait(1300)
        assert title_text.x() == 0, "Only the selected title may scroll"
        controller.select(next(row["id"] for row in controller.rows() if row["title"] == "ZZ fixture 000"))
        QTest.qWait(80)
        short_card = grid.property("currentItem")
        short_view = short_card.findChild(QQuickItem, "cardTitleViewport")
        short_text = short_view.findChild(QQuickItem, "cardTitleText")
        QTest.qWait(1300)
        assert short_text.x() == 0 and short_text.property("implicitWidth") < short_view.width()
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
                          "checks": ["platforms", "playlist-fixed-layout", "selected-title-scroll-reset",
                                     "platform-scroll-back", "empty-platform", "two-level-back", "platform-icons", "picker-cancel",
                                     "focus-restore", "long-list-scroll", "return-consumed", "core-toggle",
                                     "native-import-confirm-cancel", "native-slot-mapping", "native-export",
                                     "save-history-restore-cancel", "save-settings-focus", "thumbnail-aspect-selection",
                                     "scan-preview-cancel-commit", "independent-directory-pickers"]}))
    finally:
        delete(engine)
        controller.close()


if __name__ == "__main__":
    run(Path(sys.argv[1]), sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else "menus")
