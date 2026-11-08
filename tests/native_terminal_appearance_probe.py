import configparser
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

from PySide6.QtCore import Q_ARG, Q_RETURN_ARG, QEvent, QMetaObject, QPointF, Qt
from PySide6.QtGui import QImage, QInputMethodQueryEvent, QRawFont
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from shiboken6 import delete
from terminal_appearance_probe import check_glyphs, items

from udeck.core import ConfigStore
from udeck.terminal.core import LaunchRequest, TerminalPreferences
from udeck.terminal.main import Coordinator

ROOT = Path(__file__).resolve().parents[1]
CONTENT = "A\ue0b0B\uf07cC\uf120D\U000f0001E中F"


def wait(application, condition, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        application.processEvents()
        if condition():
            return
        QTest.qWait(20)
    raise AssertionError("Native terminal appearance probe timed out")


def run():
    output = Path(sys.argv[1])
    application = QApplication([])
    application.setQuitOnLastWindowClosed(False)
    with tempfile.TemporaryDirectory(prefix="udeck-native-appearance-") as temporary:
        directory = Path(temporary)
        settings = ConfigStore(directory / "settings.json")
        settings.data["preferences"].update(language="en", theme="classic")
        settings.save()
        preferences = TerminalPreferences(directory / "terminal.json")
        coordinator = Coordinator(application, SimpleNamespace(mock=False, no_input=True, windowed=True),
                                  preferences, time.monotonic())
        child = directory / "appearance.py"
        child.write_text(
            "import os, signal\n"
            f"content = {CONTENT!r}\n"
            "normal = ''.join(f'\\x1b[48;5;{index}m  ' for index in range(8)) + '\\x1b[0m'\n"
            "bright = ''.join(f'\\x1b[48;5;{index}m  ' for index in range(8, 16)) + '\\x1b[0m'\n"
            "os.write(1, ('\\x1b[2J\\x1b[2;1H' + normal + '\\x1b[3;1H' + bright "
            "+ '\\x1b[4;1H\\x1b[38;2;18;52;86mRGB\\x1b[0m\\x1b[5;1HA B C D E中F\\x1b[1;1H' + content).encode())\n"
            "while True: signal.pause()\n"
        )
        try:
            coordinator.open(LaunchRequest(temporary, [sys.executable, str(child)], "Nerd / ANSI 16", dict(os.environ), True))
            entry = coordinator.recent
            window, controller = entry["window"], entry["controller"]
            wait(application, lambda: bool(controller.native_sessions))
            session = next(iter(controller.native_sessions.values()))
            wait(application, lambda: CONTENT in session.property("history"))
            terminal = items(window, "nativeTerminal")[0]
            input_focus = window.activeFocusItem()
            assert input_focus is terminal
            identifier = controller.current
            process = QMetaObject.invokeMethod(session, "getShellPID", Q_RETURN_ARG(int))
            output.mkdir(parents=True, exist_ok=True)
            captures = []
            for language in ("en", "zh_CN"):
                for theme in ("classic", "dark"):
                    settings.data["preferences"].update(language=language, theme=theme)
                    settings.save()
                    coordinator.refresh_language()
                    for size in (14, 20, 28, 20):
                        preferences.font_size = size
                        controller.changed.emit()
                        QTest.qWait(100)
                        font = terminal.property("font")
                        assert QRawFont.fromFont(font).familyName() == ("JetBrains Mono" if language == "en" else "LXGW WenKai Mono")
                        assert font.pixelSize() == size
                        check_glyphs(font)
                        assert terminal.property("colorScheme") == ("udeck-dark" if theme == "dark" else "udeck")
                        query = QInputMethodQueryEvent(Qt.ImCursorRectangle | Qt.ImCursorPosition | Qt.ImSurroundingText)
                        application.sendEvent(terminal, query)
                        assert str(query.value(Qt.ImSurroundingText)).startswith(CONTENT)
                        assert query.value(Qt.ImCursorPosition) == len(CONTENT.encode("utf-16-le")) // 2
                        cell = terminal.property("fontMetrics")
                        cursor = query.value(Qt.ImCursorRectangle)
                        margin_x = round(cursor.x() - 12 * cell.width())
                        margin_y = round(cursor.y())
                        assert 0 <= margin_x < cell.width(), (cursor, cell)
                        image = window.grabWindow()
                        origin = terminal.mapToScene(QPointF(0, 0))
                        body = image.copy(round(origin.x()), round(origin.y()), round(terminal.width()), round(terminal.height()))
                        for column, span in ((0, 1), (2, 1), (4, 1), (6, 1), (8, 1), (9, 2), (11, 1)):
                            actual = body.copy(margin_x + column * cell.width(), margin_y, span * cell.width(), cell.height())
                            reference = body.copy(margin_x + column * cell.width(), margin_y + 4 * cell.height(), span * cell.width(), cell.height())
                            if actual != reference:
                                image.save(str(output / "cell-failure-window.png"))
                                actual.save(str(output / "cell-failure-actual.png"))
                                reference.save(str(output / "cell-failure-reference.png"))
                            assert actual == reference, (language, theme, size, column, cell, cursor, origin)
                    palette = configparser.ConfigParser()
                    palette.read(ROOT / "packaging" / ("terminal-dark.colorscheme" if theme == "dark" else "terminal.colorscheme"))
                    rgba = body.convertToFormat(QImage.Format_RGBA8888)
                    pixels = bytes(rgba.constBits())
                    for section in ["Background", "Foreground", *[f"Color{index}{suffix}" for index in range(8) for suffix in ("", "Intense")]]:
                        channels = [int(channel) for channel in palette[section]["Color"].split(",")]
                        assert bytes([*channels, 255]) in pixels, (theme, section)
                    assert bytes([18, 52, 86, 255]) in pixels
                    assert QMetaObject.invokeMethod(terminal, "searchText", Q_RETURN_ARG(bool), Q_ARG(str, CONTENT), Q_ARG(bool, True))
                    assert QMetaObject.invokeMethod(terminal, "selectedHistoryText", Q_RETURN_ARG(str)) == CONTENT
                    QMetaObject.invokeMethod(terminal, "copyClipboard")
                    assert application.clipboard().text() == CONTENT
                    QMetaObject.invokeMethod(terminal, "leaveHistory")
                    QTest.qWait(60)
                    filename = f"native-terminal-{theme}-{language}.png"
                    assert window.grabWindow().save(str(output / filename))
                    captures.append(filename)
                    assert items(window, "nativeTerminal") == [terminal]
                    assert window.activeFocusItem() is input_focus
                    assert controller.current == identifier
                    assert QMetaObject.invokeMethod(session, "getShellPID", Q_RETURN_ARG(int)) == process
            assert not coordinator.errors, coordinator.errors
            print(json.dumps({"nativeAppearance": "passed", "captures": captures, "ansi16": True,
                              "truecolorPreserved": True, "neighborCellsPreserved": True,
                              "unicodeCopyPreserved": True, "sessionPreserved": True}), flush=True)
        finally:
            coordinator.close()
            application.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            delete(coordinator.engine)


if __name__ == "__main__":
    run()
