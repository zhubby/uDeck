import json
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QFontMetricsF, QRawFont, QTextLayout
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from shiboken6 import delete

from udeck.core import ConfigStore
from udeck.terminal.core import LaunchRequest, TerminalPreferences
from udeck.terminal.main import Coordinator

CODEPOINTS = [0xE0B0, 0xF07C, 0xF120, 0xF0001]


def items(window, name):
    pending = [window.contentItem()]
    found = []
    while pending:
        item = pending.pop()
        if item.objectName() == name:
            found.append(item)
        pending.extend(item.childItems())
    return found


def check_glyphs(font):
    primary = QRawFont.fromFont(font)
    for codepoint in CODEPOINTS:
        text = chr(codepoint)
        layout = QTextLayout(text, font)
        layout.beginLayout()
        line = layout.createLine()
        line.setLineWidth(200)
        layout.endLayout()
        runs = layout.glyphRuns()
        assert runs
        expected = primary.familyName() if primary.supportsCharacter(codepoint) else "Symbols Nerd Font Mono"
        for run in runs:
            assert run.rawFont().familyName() == expected, (hex(codepoint), run.rawFont().familyName())
            assert run.glyphIndexes() and all(run.glyphIndexes()), hex(codepoint)
        assert QFontMetricsF(font).horizontalAdvance(text) > 0, hex(codepoint)


def run():
    output, language, theme = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
    application = QApplication([])
    application.setQuitOnLastWindowClosed(False)
    families = {"zh_CN": "LXGW WenKai Mono", "en": "JetBrains Mono"}
    with tempfile.TemporaryDirectory(prefix="udeck-terminal-appearance-") as temporary:
        directory = Path(temporary)
        path = directory / "terminal.json"
        path.write_text(json.dumps({"version": 1, "fontSize": 20, "colorScheme": "SolarizedLight"}))
        settings = ConfigStore(directory / "settings.json")
        settings.data["preferences"].update(language=language, theme=theme)
        settings.save()
        coordinator = Coordinator(application, SimpleNamespace(mock=True, no_input=True, windowed=True),
                                  TerminalPreferences(path), time.monotonic())
        try:
            request = LaunchRequest(temporary, [], "", {}, True)
            coordinator.open(request)
            entry = coordinator.recent
            window, controller = entry["window"], entry["controller"]
            first = controller.current
            controller.newTab()
            controller.selectTab(first)
            coordinator.open(request)
            coordinator.activate(window)
            QTest.qWait(150)
            content = items(window, "terminalContent")[0]
            for size in (14, 20, 28, 20):
                font = controller.terminalFont(language, size)
                assert font.families() == [families[language], "Symbols Nerd Font Mono",
                                          families["en" if language == "zh_CN" else "zh_CN"]]
                check_glyphs(font)
            assert content.property("font").families() == controller.terminalFont(language, 20).families()
            preserved = [(current, dict(current["controller"].requests), current["controller"].current,
                          items(current["window"], "terminalContent"), current["window"].activeFocusItem())
                         for current in coordinator.windows]
            for selected in ("dark" if theme == "classic" else "classic", theme):
                settings.data["preferences"]["theme"] = selected
                settings.save()
                coordinator.refresh_language()
                QTest.qWait(80)
                scheme = "udeck-dark" if selected == "dark" else "udeck"
                background, foreground = ("#0b0e12", "#f5f2eb") if selected == "dark" else ("#151719", "#f1eee7")
                for current, requests, identifier, terminals, focus in preserved:
                    host = current["controller"]
                    assert host.theme == selected and json.loads(host.snapshotJson)["colorScheme"] == scheme
                    assert host.requests == requests and host.current == identifier
                    assert items(current["window"], "terminalContent") == terminals
                    assert current["window"].activeFocusItem() is focus
                    assert all(item.property("color").name() == foreground for item in terminals)
                    assert all(item.property("color").name() == background
                               for item in items(current["window"], "terminalBackground"))
            controller.command("settings")
            controller.dispatch("down")
            controller.dispatch("accept")
            QTest.qWait(80)
            for current, requests, identifier, terminals, _focus in preserved:
                assert all(item.property("font").pixelSize() == 22 for item in terminals), (
                    "A shared font-size change must update existing windows immediately",
                    [item.property("font").pixelSize() for item in terminals],
                )
                assert current["controller"].requests == requests
                assert current["controller"].current == identifier
                assert items(current["window"], "terminalContent") == terminals
            controller.dispatch("back")
            controller.command("settings")
            controller.dispatch("accept")
            controller.dispatch("back")
            controller.command("settings")
            QTest.qWait(60)
            hint = items(window, "terminalThemeHint")[0]
            assert hint.isVisible() and not hint.hasActiveFocus() and not hint.property("focus")
            assert ("跟随系统" if language == "zh_CN" else "Follow system") in hint.property("text")
            assert len(json.loads(controller.snapshotJson)["options"]) == 3
            output.mkdir(parents=True, exist_ok=True)
            assert window.grabWindow().save(str(output / f"terminal-settings-{theme}-{language}.png"))
            controller.dispatch("back")
            QTest.qWait(60)
            assert window.grabWindow().save(str(output / f"terminal-{theme}-{language}.png"))
            controller.command("search")
            QTest.qWait(60)
            assert window.activeFocusItem().isVisible()
            controller.dispatch("back")
            QTest.qWait(40)
            operations = []
            controller.operate.connect(lambda *arguments: operations.append(arguments))
            controller.preparePaste("alpha\nbeta")
            QTest.qWait(60)
            assert window.activeFocusItem().isVisible(), "A hidden search field must not keep modal focus"
            QTest.keyClick(window, Qt.Key_Down)
            QTest.keyClick(window, Qt.Key_Return)
            QTest.qWait(40)
            assert controller.mode == "input"
            assert operations[-1][1:] == ("paste", "alpha\nbeta")
            assert not coordinator.errors, coordinator.errors
            print(json.dumps({"theme": theme, "language": language, "windows": len(coordinator.windows),
                              "sessions": sum(len(current["controller"].requests) for current in coordinator.windows),
                              "sessionsPreserved": True, "focusPreserved": True,
                              "nerdCodepoints": CODEPOINTS, "qmlErrors": coordinator.errors}), flush=True)
        finally:
            coordinator.close()
            application.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            delete(coordinator.engine)


if __name__ == "__main__":
    run()
