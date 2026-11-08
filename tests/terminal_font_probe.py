import json
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

from PySide6.QtCore import QEvent
from PySide6.QtGui import QFont, QFontInfo, QFontMetricsF, QRawFont
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from shiboken6 import delete

from udeck.core import ConfigStore
from udeck.terminal.core import TerminalPreferences, parse_launch
from udeck.terminal.main import Coordinator


def run():
    output = Path(sys.argv[1])
    language = sys.argv[2] if len(sys.argv) > 2 else "zh_CN"
    families = {"zh_CN": "LXGW WenKai Mono", "en": "JetBrains Mono"}
    expected = families[language]
    application = QApplication([])
    application.setQuitOnLastWindowClosed(False)
    with tempfile.TemporaryDirectory(prefix="udeck-terminal-font-") as temporary:
        preferences = TerminalPreferences(Path(temporary) / "preferences.json")
        settings = ConfigStore(preferences.path.with_name("settings.json"))
        settings.data["preferences"].update(language=language, theme="classic")
        settings.save()
        options = SimpleNamespace(mock=True, no_input=True, windowed=True)
        coordinator = Coordinator(application, options, preferences, time.monotonic())
        request, _ = parse_launch(["--mock"])
        try:
            coordinator.open(request)
            window = coordinator.recent["window"]
            controller = coordinator.recent["controller"]
            QTest.qWait(250)
            pending = [window.contentItem()]
            terminal_text = None
            while pending:
                item = pending.pop()
                if item.inherits("QQuickText") and str(item.property("text")).startswith("uDeck Terminal"):
                    terminal_text = item
                    break
                pending.extend(item.childItems())
            assert terminal_text is not None
            assert window.property("fontFamily") not in families.values()
            font_sizes = []
            for size in (20, 14, 28, 20):
                if size != preferences.font_size:
                    controller.command("settings")
                    if size > preferences.font_size:
                        controller.dispatch("down")
                    for _ in range(abs(size - preferences.font_size) // 2):
                        controller.dispatch("accept")
                    controller.dispatch("back")
                QTest.qWait(40)
                font = terminal_text.property("font")
                assert font.family() == expected, font.family()
                assert QRawFont.fromFont(font).familyName() == expected, QFontInfo(font).family()
                assert font.pixelSize() == size
                if language == "en":
                    assert QFontInfo(font).fixedPitch()
                metrics = QFontMetricsF(font)
                advances = [metrics.horizontalAdvance(character) for character in "imW0l1"]
                assert max(advances) - min(advances) < 0.01, advances
                if language == "zh_CN":
                    raw_font = QRawFont.fromFont(font)
                    for character in "你好终端阅读":
                        assert raw_font.supportsCharacter(ord(character)), character
                        assert abs(metrics.horizontalAdvance(character) - 2 * advances[0]) < 0.03
                font_sizes.append(size)
            bold = QFont(font)
            bold.setBold(True)
            assert QRawFont.fromFont(bold).familyName() == expected
            assert QFontInfo(bold).bold()
            if language == "en":
                assert QFontInfo(bold).styleName() == "Bold"
            current = controller.current
            requests = list(controller.requests)
            language_switches = []
            for next_language in ("en" if language == "zh_CN" else "zh_CN", language):
                settings.data["preferences"]["language"] = next_language
                settings.save()
                coordinator.refresh_language()
                QTest.qWait(40)
                assert controller.language == next_language
                assert QRawFont.fromFont(terminal_text.property("font")).familyName() == families[next_language]
                assert controller.current == current and list(controller.requests) == requests
                assert coordinator.recent["window"] is window
                language_switches.append(next_language)
            assert not coordinator.errors, coordinator.errors
            output.parent.mkdir(parents=True, exist_ok=True)
            assert window.grabWindow().save(str(output))
            print(json.dumps({"fontFamily": font.family(), "resolvedFamily": QRawFont.fromFont(font).familyName(),
                              "boldStyle": QFontInfo(bold).styleName(), "fontSizes": font_sizes,
                              "languageSwitches": language_switches, "sessionPreserved": True,
                              "qmlErrors": coordinator.errors, "screenshot": str(output)}), flush=True)
        finally:
            coordinator.close()
            application.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            delete(coordinator.engine)


if __name__ == "__main__":
    run()
