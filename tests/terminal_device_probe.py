"""Run synthetic keyboard/TUI acceptance against the installed GUI on a device.

Run separately with QT_QPA_PLATFORM=wayland and xcb. This does not count as
physical-button or input-method-engine acceptance.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import tomllib
from pathlib import Path
from types import SimpleNamespace

from PySide6.QtCore import Q_ARG, Q_RETURN_ARG, QMetaObject, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from udeck.terminal import main
from udeck.terminal.core import LaunchRequest, TerminalPreferences

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--output", type=Path, required=True)
parser.add_argument("--allow-source", action="store_true")
options = parser.parse_args()
options.output.parent.mkdir(parents=True, exist_ok=True)
installed = str(Path(main.__file__).resolve()).startswith("/usr/lib/python3/dist-packages/")
assert installed or options.allow_source, main.__file__
app = QApplication([])
app.setQuitOnLastWindowClosed(False)
app.setDesktopFileName("io.github.zhubby.uDeck.Terminal.DeviceProbe")
report = {"backend": app.platformName(), "input": "synthetic Qt keyboard events",
          "installed": installed, "moduleSource": main.__file__, "checks": {},
          "buildId": json.loads(Path("/usr/share/udeck-terminal/build-info.json").read_text())["buildId"] if installed else None}


def wait(condition, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if condition():
            return
        QTest.qWait(30)
    raise AssertionError(f"Device probe timed out: {coordinator.diagnostics()}")


def invoke(obj, name, *args, result=None):
    arguments = [Q_ARG(type(value), value) for value in args]
    if result:
        return QMetaObject.invokeMethod(obj, name, Q_RETURN_ARG(result), *arguments)
    return QMetaObject.invokeMethod(obj, name, *arguments)


def key(window, code, modifiers=Qt.NoModifier):
    QTest.keyClick(window, code, modifiers)
    QTest.qWait(40)


def text(window, value):
    for character in value:
        QTest.keyClick(window, character, delay=5)
    app.processEvents()


with tempfile.TemporaryDirectory(prefix="udeck-terminal-device-") as temporary:
    directory = Path(temporary)
    coordinator = main.Coordinator(app, SimpleNamespace(mock=False, no_input=True, windowed=True),
                                   TerminalPreferences(directory / "preferences"), time.monotonic())

    def launch(argv, title):
        coordinator.open(LaunchRequest(str(directory), argv, title, dict(os.environ), True))
        entry = coordinator.recent
        wait(lambda: bool(entry["controller"].native_sessions))
        items = [entry["window"].contentItem()]
        terminal = None
        while items:
            item = items.pop()
            if item.objectName() == "nativeTerminal":
                terminal = item
                break
            items.extend(item.childItems())
        assert terminal is not None
        QTest.qWait(700)
        return entry["window"], terminal

    def visible(terminal, value):
        found = invoke(terminal, "searchText", value, True, result=bool)
        invoke(terminal, "leaveHistory")
        return found

    try:
        # Exercise real QQuickWindow -> focused native item -> PTY key delivery.
        capture = directory / "keys.py"
        capture.write_text("import os,tty\nfrom pathlib import Path\ntty.setraw(0)\nos.write(1,b'KEYS_READY\\r\\n')\ndata=b''\nwhile not data.endswith(b'__END__'):\n data+=os.read(0,4096)\nPath('keys.hex').write_text(data.hex())\n")
        window, terminal = launch([sys.executable, str(capture)], "原生键盘验证")
        wait(lambda: visible(terminal, "KEYS_READY"))
        controller = coordinator.recent["controller"]
        modifiers = Qt.ControlModifier | Qt.ShiftModifier
        key(window, Qt.Key_M, modifiers)
        wait(lambda: controller.mode == "menu")
        key(window, Qt.Key_T, modifiers)
        assert len(controller.requests) == 1 and controller.mode == "menu"
        key(window, Qt.Key_Escape)
        key(window, Qt.Key_T, modifiers)
        wait(lambda: len(controller.native_sessions) == 2)
        key(window, Qt.Key_W, modifiers)
        wait(lambda: controller.mode == "close")
        key(window, Qt.Key_Return)
        assert len(controller.requests) == 2 and controller.mode == "input"
        key(window, Qt.Key_W, modifiers)
        key(window, Qt.Key_Down)
        key(window, Qt.Key_Return)
        wait(lambda: len(controller.native_sessions) == 1)
        report["checks"]["qml-shortcuts-modal-isolation-close-cancel"] = "passed"
        for code in (Qt.Key_Up, Qt.Key_Down, Qt.Key_Left, Qt.Key_Right, Qt.Key_Escape,
                     Qt.Key_F1, Qt.Key_F10, Qt.Key_PageUp, Qt.Key_PageDown):
            key(window, code)
        key(window, Qt.Key_A, Qt.ControlModifier)
        text(window, "abxy")
        invoke(terminal, "pasteText", "__END__")
        wait(lambda: (directory / "keys.hex").exists())
        expected = b"\x1b[A\x1b[B\x1b[D\x1b[C\x1b\x1bOP\x1b[21~\x1b[5~\x1b[6~\x01abxy__END__"
        assert bytes.fromhex((directory / "keys.hex").read_text()) == expected
        wait(lambda: not coordinator.windows)
        report["checks"]["keyboard-escape-function-arrows-ctrl-letters"] = "passed"

        edited = directory / "vim 中文.txt"
        window, terminal = launch([shutil.which("vim"), "-u", "NONE", "-N", str(edited)], "Vim 实机验证")
        text(window, "iVim terminal probe")
        key(window, Qt.Key_Escape)
        text(window, ":wq")
        key(window, Qt.Key_Return)
        wait(lambda: not coordinator.windows)
        assert edited.read_text() == "Vim terminal probe\n"
        report["checks"]["vim-edit-save-exit"] = "passed"

        document = directory / "less 中文.txt"
        document.write_text("".join(f"line{line:04d} 中文 English\n" for line in range(400)))
        window, terminal = launch([shutil.which("less"), str(document)], "less 实机验证")
        text(window, "G")
        wait(lambda: visible(terminal, "line0399"))
        text(window, "g/line0020")
        key(window, Qt.Key_Return)
        wait(lambda: visible(terminal, "line0020"))
        key(window, Qt.Key_PageDown)
        key(window, Qt.Key_PageUp)
        text(window, "q")
        wait(lambda: not coordinator.windows)
        report["checks"]["less-scroll-search-exit"] = "passed"

        socket = f"udeck-terminal-probe-{os.getpid()}"
        tmux = shutil.which("tmux")
        try:
            window, terminal = launch([tmux, "-L", socket, "-f", "/dev/null", "new-session", "-s", "probe", "/bin/sh"], "tmux 实机验证")
            text(window, "printf tmux-ok > tmux-marker")
            key(window, Qt.Key_Return)
            wait(lambda: (directory / "tmux-marker").exists())
            assert (directory / "tmux-marker").read_text() == "tmux-ok"
            key(window, Qt.Key_B, Qt.ControlModifier)
            text(window, "d")
            wait(lambda: not coordinator.windows)
            report["checks"]["tmux-shell-detach"] = "passed"
        finally:
            subprocess.run([tmux, "-L", socket, "kill-server"], check=False, capture_output=True)

        codex = shutil.which("codex")
        assert codex, "The actual Codex CLI must be installed for this probe"
        report["codexVersion"] = subprocess.check_output([codex, "--version"], text=True).strip()
        codex_arguments = [codex, "--no-alt-screen"]
        codex_home = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
        try:
            config = tomllib.loads((codex_home / "config.toml").read_text())
            if config.get("projects", {}).get(str(Path.home()), {}).get("trust_level") == "trusted":
                codex_arguments.extend(["--cd", str(Path.home())])
        except (OSError, ValueError):
            pass
        window, terminal = launch(codex_arguments, "Codex 实机验证")
        wait(lambda: any(visible(terminal, word) for word in ("OpenAI Codex", "Do you trust")), timeout=20)
        assert window.grabWindow().save(str(options.output.with_suffix(".codex.png")))
        if visible(terminal, "Do you trust"):
            key(window, Qt.Key_Down)
            key(window, Qt.Key_Return)
            report["codexScope"] = "Rendered trust dialog; selected No and exited without changing trust settings"
        else:
            key(window, Qt.Key_C, Qt.ControlModifier)
            QTest.qWait(700)
            key(window, Qt.Key_C, Qt.ControlModifier)
            report["codexScope"] = "Rendered interactive editor; interrupted without submitting a prompt"
        wait(lambda: not coordinator.windows)
        report["checks"]["codex-tui-startup-keyboard-exit"] = "passed"

        coordinator.open(LaunchRequest(str(directory), ["/bin/sh", "-c", "kill -TERM $$"],
                                       "异常退出验证", dict(os.environ), True))
        wait(lambda: not coordinator.windows)
        report["checks"]["abnormal-exit-removes-window"] = "passed"
        assert not coordinator.errors, coordinator.errors
        report["qmlErrors"] = coordinator.errors
        report["result"] = "passed"
    finally:
        if coordinator.recent:
            coordinator.recent["window"].grabWindow().save(str(options.output.with_suffix(".last.png")))
        coordinator.close()
        options.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
print(json.dumps(report, ensure_ascii=False))
