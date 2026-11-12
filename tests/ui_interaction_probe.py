"""Real Qt Quick input, playback, pointer and layout regression scenarios."""

import json
import math
import struct
import subprocess
import sys
import time
import wave
from pathlib import Path
from types import SimpleNamespace

from PySide6.QtCore import QEvent, QObject, QPoint, QPointF, Qt, QUrl
from PySide6.QtGui import QInputMethodEvent, QKeyEvent
from PySide6.QtQml import QQmlApplicationEngine, QQmlEngine, QQmlExpression
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from shiboken6 import delete

import udeck
from udeck.core import ConfigStore
from udeck.icons import IconProvider

directory, surface_name, scenario, *arguments = sys.argv[1:]
directory = Path(directory)
if surface_name == "browser":
    from PySide6.QtWebEngineQuick import QtWebEngineQuick

    QtWebEngineQuick.initialize()
application = QApplication([])
application.setQuitOnLastWindowClosed(False)
errors = []
config = ConfigStore(directory / "settings.json")
if scenario == "layout":
    config.data["preferences"]["language"] = arguments[2]
    config.save()
elif scenario == "pointer-resize":
    config.data["preferences"].update(language=arguments[0], theme=arguments[1])
    config.save()
coordinator = None
if surface_name == "terminal":
    from udeck.terminal.core import LaunchRequest, TerminalPreferences
    from udeck.terminal.main import Coordinator

    coordinator = Coordinator(application, SimpleNamespace(mock=True, no_input=True, windowed=True),
                              TerminalPreferences(directory / "terminal.json"), time.monotonic())
    coordinator.open(LaunchRequest(str(directory), [], "", {}, True))
    window = coordinator.recent["window"]
    controller = coordinator.recent["controller"]
    engine = coordinator.engine
    coordinator.activate(window)
else:
    engine = QQmlApplicationEngine()
    engine.addImageProvider("desktop", IconProvider())
    engine.warnings.connect(lambda warnings: errors.extend(item.toString() for item in warnings))
    if surface_name == "shell":
        from udeck.controller import ShellController
        from udeck.mock import MockBackend

        controller = ShellController(MockBackend(), config=config, mock=True)
        engine.rootContext().setContextProperty("windowedPreview", True)
        engine.rootContext().setContextProperty("headlessPreview", True)
        source = "qml/Main.qml"
    else:
        from udeck.apps.main import make_controller

        controller = make_controller(surface_name, directory / "state", config.path)
        controller.isolated = True
        controller.poller.stop()
        engine.rootContext().setContextProperty("windowed", True)
        source = "apps/common/qml/Main.qml"
        if surface_name in ("music", "video"):
            from udeck.apps.media.engine import FrameImages

            engine.addImageProvider("video", FrameImages(controller))
    engine.rootContext().setContextProperty("controller", controller)
    engine.load(QUrl.fromLocalFile(str(Path(udeck.__file__).parent / source)))
    assert engine.rootObjects(), errors
    window = engine.rootObjects()[0]
    if surface_name != "shell":
        controller.window = window
window.requestActivate()
QTest.qWait(150)


def settle():
    QTest.qWait(50)


def wait_for(predicate, message):
    deadline = time.monotonic() + 8
    while not predicate() and time.monotonic() < deadline:
        QTest.qWait(20)
    assert predicate(), message


def key(name, modifiers=Qt.KeyboardModifier.NoModifier):
    QTest.keyClick(window, getattr(Qt.Key, "Key_" + name), modifiers)
    settle()


def type_text(text):
    for character in text:
        QTest.keyClick(window, character)
    settle()


def playback():
    from udeck.apps.common.library import Source, scan

    content = directory / "content"
    content.mkdir()
    if surface_name == "video":
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi",
                        "-i", "testsrc2=duration=12:size=160x90:rate=12", "-y",
                        str(content / "audit.mp4")], check=True, timeout=15)
    else:
        with wave.open(str(content / "audit.wav"), "wb") as audio:
            audio.setparams((1, 2, 8000, 0, "NONE", "not compressed"))
            audio.writeframes(b"".join(struct.pack("<h", int(1500 * math.sin(index / 8)))
                                       for index in range(8000 * 12)))
    source = Source.create(content)
    controller.library.sources = [source]
    controller.library.items = scan(source, surface_name)
    controller.media.output.setMuted(True)
    controller.play(controller.library.items[0])
    deadline = time.monotonic() + 8
    loader = window.findChild(QObject, "appSurface")
    while time.monotonic() < deadline:
        if (loader.property("item") is not None and not controller.media.loading
                and controller.media.player.position() > 100):
            settle()
            return loader.property("item")
        QTest.qWait(20)
    raise AssertionError("The original media fixture did not start playback")


def buttons(item):
    return [child for child in item.findChildren(QObject)
            if child.metaObject().indexOfSignal("activated()") >= 0
            and child.metaObject().indexOfProperty("selected") >= 0]


def position(item, horizontal=0.5, vertical=0.5):
    return item.mapToScene(QPointF(item.width() * horizontal, item.height() * vertical)).toPoint()


def assert_contained(item, surface):
    ancestor = item.parentItem()
    while ancestor is not None:
        if ancestor is surface or ancestor.property("clip"):
            point = item.mapToItem(ancestor, QPointF())
            assert 0 <= point.x() and point.x() + item.width() <= ancestor.width() + 1
            assert 0 <= point.y() and point.y() + item.height() <= ancestor.height() + 1, (
                f"Interactive item is clipped by {ancestor.metaObject().className()}: "
                f"{point.y()} + {item.height()} > {ancestor.height()}")
        ancestor = ancestor.parentItem()


def test_address():
    navigations = []
    controller.webAction.connect(lambda action, payload: navigations.append(json.loads(payload)["url"])
                                 if action == "navigate" else None)
    key("L", Qt.KeyboardModifier.ControlModifier)
    type_text("http://127.0.0.1:9/audit")
    original = controller.menus[-1]
    key("L", Qt.KeyboardModifier.ControlModifier)
    field = window.findChild(QObject, "menuDraft")
    assert len(controller.menus) == 1, "Repeated Ctrl+L stacked address prompts"
    assert controller.menus[-1] is original
    assert field.property("text") == original["draft"] == "http://127.0.0.1:9/audit"
    if arguments[0] == "escape":
        key("Escape")
        assert not controller.menus, "One Escape left a second address prompt"
        assert not navigations
    else:
        if arguments[0] == "enter":
            key("Return")
        else:
            controller.dispatch("accept")
            settle()
        assert navigations == ["http://127.0.0.1:9/audit"]
        assert not controller.menus
        wait_for(lambda: controller.active_tab().url == "http://127.0.0.1:9/audit",
                 "WebEngine did not acknowledge the submitted address")


def test_prompt_identity():
    submitted = []
    controller.prompt("Same title", submitted.append, "first")
    settle()
    field = window.findChild(QObject, "menuDraft")
    key("End")
    type_text("-edited")
    field.setProperty("cursorPosition", 2)
    controller.publish()
    settle()
    assert field.property("cursorPosition") == 2
    assert field.property("text") == "first-edited"
    controller.prompt("Same title", submitted.append, "second")
    settle()
    assert field.property("text") == "second", "A same-title prompt showed a previous dialog's draft"
    controller.dispatch("accept")
    settle()
    assert submitted == ["second"]
    assert field.property("text") == "first-edited", "Popping the nested prompt lost its parent's draft"
    controller.dispatch("accept")
    assert submitted == ["second", "first-edited"]


def test_composition():
    submitted, operations, navigations = [], [], []
    if surface_name == "shell":
        controller.setPage("apps")
        settle()
        key("F", Qt.KeyboardModifier.ControlModifier)
        type_text("before")
    elif surface_name == "terminal":
        controller.operate.connect(lambda identifier, action, text: operations.append(action))
        key("F", Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier)
        type_text("before")
    elif surface_name == "browser":
        controller.webAction.connect(lambda action, payload: navigations.append(json.loads(payload)["url"])
                                     if action == "navigate" else None)
        key("L", Qt.KeyboardModifier.ControlModifier)
    else:
        controller.prompt("Composition regression", submitted.append, "before")
        settle()
    field = window.activeFocusItem()
    assert field is not None and field.metaObject().indexOfProperty("inputMethodComposing") >= 0
    QApplication.sendEvent(field, QInputMethodEvent("zhong", []))
    assert field.property("inputMethodComposing")
    controller.changed.emit()
    settle()
    assert field.property("inputMethodComposing"), "An unrelated update reset the active composition"
    if scenario == "composition-action":
        controller.dispatch(arguments[0])
        settle()
    else:
        key(arguments[0])
    if surface_name == "shell":
        assert controller.modal, "A composing key closed the shell's input dialog"
        assert controller.query == ""
    elif surface_name == "terminal":
        assert controller.mode == "search", "A composing key dismissed Terminal search"
        assert not any(action.startswith("search-") for action in operations), (
            "A composing key started a terminal search")
    else:
        assert controller.menus and not submitted, "A composing key submitted or dismissed input"
    commit = QInputMethodEvent()
    commit.setCommitString("localhost" if surface_name == "browser" else "中文")
    QApplication.sendEvent(field, commit)
    settle()
    committed = field.property("text")
    assert not field.property("inputMethodComposing")
    if scenario == "composition-action":
        controller.dispatch("accept")
        settle()
    else:
        key("Return")
    if surface_name == "shell":
        assert not controller.modal and controller.query == committed
    elif surface_name == "terminal":
        assert "search-next" in operations and controller.query == committed
        key("Escape")
        assert controller.mode == "input"
    elif surface_name == "browser":
        assert not controller.menus and navigations == ["https://localhost"]
    else:
        assert not controller.menus and submitted == [committed]


def test_repeat():
    playback()
    states = []
    controller.media.player.playbackStateChanged.connect(lambda state: states.append(state.name))
    QTest.keyPress(window, Qt.Key.Key_Return)
    settle()
    for _unused in range(5):
        QApplication.sendEvent(window, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Return,
                                                 Qt.KeyboardModifier.NoModifier, "", True, 1))
        settle()
    QTest.keyRelease(window, Qt.Key.Key_Return)
    assert states == ["PausedState"], f"A held Enter toggled playback repeatedly: {states}"
    for direction, expected in (("Up", 0), ("Down", 1)):
        QApplication.sendEvent(window, QKeyEvent(QEvent.Type.KeyPress, getattr(Qt.Key, "Key_" + direction),
                                                 Qt.KeyboardModifier.NoModifier, "", True, 1))
        assert controller.controls == expected, "Directional auto-repeat stopped navigating"


def test_shortcut_repeat():
    modifiers = Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier
    QTest.keyPress(window, Qt.Key.Key_T, modifiers)
    settle()
    for _unused in range(5):
        QApplication.sendEvent(window, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_T,
                                                 modifiers, "T", True, 1))
        settle()
    QTest.keyRelease(window, Qt.Key.Key_T, modifiers)
    assert len(controller.requests) == 2, f"A held shortcut created {len(controller.requests) - 1} sessions"
    key("T", modifiers)
    assert len(controller.requests) == 3, "Releasing and pressing the shortcut no longer opened a session"


def test_composition_owner():
    from udeck.apps.main import make_controller

    controller.prompt("Foreground input", lambda value: None, "foreground")
    settle()
    field = window.activeFocusItem()
    QApplication.sendEvent(field, QInputMethodEvent("zhong", []))
    assert field.property("inputMethodComposing")
    background = make_controller("reader", directory / "background-state", config.path)
    submitted = []
    try:
        background.prompt("Background input", submitted.append, "background")
        background.dispatch("accept")
        assert submitted == ["background"]
        assert controller.menus and field.property("inputMethodComposing")
    finally:
        background.close()


def test_history_repeat():
    operations = []
    controller.operate.connect(lambda identifier, action, text: operations.append(action))
    controller.command("history")
    settle()
    QTest.keyPress(window, Qt.Key.Key_Return)
    settle()
    for _unused in range(5):
        QApplication.sendEvent(window, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Return,
                                                 Qt.KeyboardModifier.NoModifier, "", True, 1))
        settle()
    QTest.keyRelease(window, Qt.Key.Key_Return)
    assert controller.mode == "history", "A held confirmation copied history and left selection mode"
    assert operations == ["history", "anchor"]
    QApplication.sendEvent(window, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Down,
                                             Qt.KeyboardModifier.NoModifier, "", True, 1))
    assert operations == ["history", "anchor", "down"]
    key("Return")
    assert controller.mode == "input" and operations[-1] == "copy-history"


def test_pointer_resize():
    surface = window.findChild(QObject, "appSurface").property("item")
    ready = QQmlExpression(QQmlEngine.contextForObject(surface), surface,
                          "pages.count > 0 && pages.itemAt(0).loadProgress === 100 && !pages.itemAt(0).loading")
    wait_for(lambda: ready.evaluate()[0], "The initial Browser page did not finish loading")
    assert not ready.hasError()
    controller.active_tab().url = "https://layout.invalid/pointer"
    controller.set_mode("pointer")
    settle()
    expression = QQmlExpression(QQmlEngine.contextForObject(surface), surface, "pointer")
    pointer, undefined = expression.evaluate()
    assert not expression.hasError() and pointer is not None
    for _unused in range(50):
        controller.dispatch("right")
        controller.dispatch("down")
    settle()
    viewport = pointer.parentItem()
    assert controller.active_tab().url == "https://layout.invalid/pointer"
    assert pointer.x() == viewport.width() - pointer.width()
    assert pointer.y() == viewport.height() - pointer.height()
    assert_contained(pointer, viewport)
    window.setWidth(800)
    window.setHeight(500)
    QTest.qWait(100)
    assert window.grabWindow().save(str(directory / "pointer-resized.png"))
    assert_contained(pointer, viewport)
    controller.dispatch("left")
    controller.dispatch("up")
    settle()
    assert_contained(pointer, viewport)
    window.setWidth(1280)
    window.setHeight(720)
    settle()
    assert_contained(pointer, viewport)


def test_settings_repeat():
    controller.command("settings")
    settle()
    initial_size = controller.preferences.font_size
    QTest.keyPress(window, Qt.Key.Key_Return)
    settle()
    for _unused in range(5):
        QApplication.sendEvent(window, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Return,
                                                 Qt.KeyboardModifier.NoModifier, "", True, 1))
        settle()
    QTest.keyRelease(window, Qt.Key.Key_Return)
    assert controller.preferences.font_size == initial_size - 2, (
        f"A held confirmation changed font size from {initial_size} to {controller.preferences.font_size}")
    key("Down")
    key("Return")
    assert controller.preferences.font_size == initial_size


def test_input_cycles():
    def change_preferences(language, theme):
        if surface_name in ("shell", "terminal"):
            controller.setLanguage(language)
            controller.setTheme(theme)
        else:
            preferences = ConfigStore(config.path)
            preferences.data["preferences"].update(language=language, theme=theme)
            preferences.save()
            controller.poll()
        settle()

    for iteration in range(4):
        if surface_name == "shell":
            controller.setPage("apps")
            key("F", Qt.KeyboardModifier.ControlModifier)
        elif surface_name == "terminal":
            key("F", Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier)
        elif surface_name == "browser":
            key("L", Qt.KeyboardModifier.ControlModifier)
        else:
            controller.command("search")
            settle()
        field = window.activeFocusItem()
        key("A", Qt.KeyboardModifier.ControlModifier)
        text = f"draft-{iteration}"
        type_text(text)
        QTest.keyClick(window, Qt.Key.Key_Home)
        QTest.keyClick(window, Qt.Key.Key_Right)
        for _unused in range(3):
            QTest.keyClick(window, Qt.Key.Key_Right, Qt.KeyboardModifier.ShiftModifier)
        settle()
        assert field.property("selectedText") == "raf"
        change_preferences("zh_CN", "dark")
        assert window.activeFocusItem() is field and field.property("text") == text
        assert field.property("selectedText") == "raf" and field.property("cursorPosition") == 4
        key("Right")
        QApplication.sendEvent(field, QInputMethodEvent("zhong", []))
        assert field.property("inputMethodComposing")
        change_preferences("en", "classic")
        assert window.activeFocusItem() is field and field.property("text") == text
        assert field.property("inputMethodComposing")
        controller.dispatch("accept")
        settle()
        assert field.isVisible() and field.property("inputMethodComposing")
        QApplication.sendEvent(field, QInputMethodEvent("", []))
        key("Escape")
        if surface_name == "shell":
            assert not controller.modal
        elif surface_name == "terminal":
            assert controller.mode == "input"
        else:
            assert not controller.menus


def test_pointer_hold():
    surface = playback()
    slider = next(child for child in surface.findChildren(QObject)
                  if child.metaObject().indexOfSignal("moved()") >= 0)
    point = position(slider, 0.3)
    QTest.mouseMove(window, point)
    QTest.mousePress(window, Qt.MouseButton.LeftButton, pos=point)
    settle()
    assert slider.property("pressed") and controller.media.snapshot()["playing"]
    controller.inactive = 4
    controller.poll()
    settle()
    assert window.grabWindow().save(str(directory / "video-held-slider.png"))
    assert controller.controls_visible and slider.property("pressed"), (
        "The idle timer hid controls and canceled a held slider gesture")
    QTest.mouseRelease(window, Qt.MouseButton.LeftButton, pos=point)
    settle()
    assert controller.inactive == 0, "Releasing the pointer did not restart the idle interval"
    controller.poll()
    assert controller.controls_visible
    for _unused in range(4):
        controller.poll()
        QTest.qWait(10)
    assert not controller.controls_visible, "Controls no longer hid after the released pointer became idle"
    controller.dispatch("down")
    settle()
    QTest.mousePress(window, Qt.MouseButton.LeftButton, pos=point)
    settle()
    assert controller.pointer_pressed
    controller.dispatch("back")
    settle()
    try:
        assert controller.page == "library", f"Back did not leave playback: {controller.page}"
        assert not controller.pointer_pressed, (
            "Leaving playback retained the old pointer grab state: "
            f"surface visible={surface.isVisible()}"
        )
        assert not any("PointHandler" in child.metaObject().className()
                       for child in surface.findChildren(QObject)), "The hidden surface retained its observer"
        assert not slider.property("pressed"), "The hidden slider retained its grab"
    finally:
        QTest.mouseRelease(window, Qt.MouseButton.LeftButton, pos=point)
    controller.command("now-playing")
    controller.command("play-pause")
    settle()
    assert surface.isVisible() and controller.media.snapshot()["playing"]
    assert not controller.pointer_pressed
    QTest.mouseMove(window, QPoint(100, 200))
    settle()
    idle_counts = []
    for _unused in range(5):
        controller.poll()
        QTest.qWait(10)
        idle_counts.append(controller.inactive)
    assert not controller.controls_visible, (
        f"Returning to playback retained an obsolete pointer grab: {idle_counts}, "
        f"pressed={controller.pointer_pressed}, menus={controller.menus}, "
        f"media={controller.media.snapshot()}"
    )


def test_pointer():
    surface = playback()
    QTest.mouseMove(window, QPoint(100, 200))
    settle()
    controller.inactive = 4
    controller.poll()
    settle()
    assert not controller.controls_visible, "Playing video did not hide its idle controls"
    QTest.mouseMove(window, QPoint(200, 200))
    settle()
    assert controller.controls_visible, "Mouse movement did not restore hidden controls"
    assert controller.inactive == 0
    controller.inactive = 4
    QTest.mouseMove(window, QPoint(300, 200))
    settle()
    controller.poll()
    assert controller.controls_visible and controller.inactive == 1
    controller.controls_visible = False
    controller.publish()
    settle()
    QTest.mouseClick(window, Qt.MouseButton.LeftButton, pos=QPoint(300, 200))
    settle()
    assert controller.controls_visible, "A click without movement did not restore controls"
    pause = buttons(surface)[1]
    QTest.mouseClick(window, Qt.MouseButton.LeftButton, pos=position(pause))
    settle()
    assert not controller.media.snapshot()["playing"], "Pointer monitoring consumed a playback button click"
    slider = next(child for child in surface.findChildren(QObject)
                  if child.metaObject().indexOfSignal("moved()") >= 0)
    QTest.mousePress(window, Qt.MouseButton.LeftButton, pos=position(slider, 0.25))
    QTest.mouseMove(window, position(slider, 0.5))
    QTest.mouseRelease(window, Qt.MouseButton.LeftButton, pos=position(slider, 0.5))
    settle()
    assert controller.media.player.position() > 4000, "Pointer monitoring consumed a slider drag"


def test_layout():
    window.setWidth(int(arguments[0]))
    window.setHeight(int(arguments[1]))
    controller.current = {"id": "layout", "title": "audit", "format": "WAV",
                          "artist": "Original artist", "album": "Original album"}
    controller.page = "player"
    controller.publish()
    loader = window.findChild(QObject, "appSurface")
    deadline = time.monotonic() + 5
    while loader.property("item") is None and time.monotonic() < deadline:
        settle()
    surface = loader.property("item")
    assert surface is not None
    QTest.qWait(150)
    playback_buttons = buttons(surface)
    assert len(playback_buttons) == 3
    shuffle_label = controller.translate(controller.messageKeys["SHUFFLE"], controller.language) + ":"
    status = next(child for child in surface.findChildren(QObject)
                  if str(child.property("text") or "").startswith(shuffle_label))
    assert window.grabWindow().save(str(directory / "music-short-title.png"))
    for button in [*playback_buttons, status]:
        assert_contained(button, surface)
    controller.current.update(title="Long original album title " * 20,
                              artist="Long artist metadata " * 20, album="Original album")
    controller.publish()
    settle()
    key("Up")
    for button in playback_buttons:
        assert_contained(button, surface)
    scroll = next((child for child in surface.findChildren(QObject)
                   if child.metaObject().indexOfProperty("contentY") >= 0), None)
    if scroll is not None:
        scroll.setProperty("contentY", max(0, scroll.property("contentHeight") - scroll.height()))
        settle()
    for button in [*playback_buttons, status]:
        assert_contained(button, surface)
    assert window.grabWindow().save(str(directory / "music-long-title.png"))


try:
    {"address": test_address, "prompt-identity": test_prompt_identity,
     "composition": test_composition, "composition-action": test_composition,
     "composition-owner": test_composition_owner,
     "history-repeat": test_history_repeat, "pointer-resize": test_pointer_resize,
     "settings-repeat": test_settings_repeat,
     "input-cycles": test_input_cycles,
     "pointer-hold": test_pointer_hold,
     "shortcut-repeat": test_shortcut_repeat, "repeat": test_repeat,
     "pointer": test_pointer, "layout": test_layout}[scenario]()
    assert not errors, errors
    if coordinator:
        assert not coordinator.errors, coordinator.errors
    print(json.dumps({"surface": surface_name, "scenario": scenario, "qmlErrors": errors}))
finally:
    window.hide()
    if coordinator:
        coordinator.close()
        delete(engine)
    else:
        delete(engine)
        controller.close()
