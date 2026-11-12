"""Real native-plugin/PTY probe, run in its own QApplication process."""

import json
import os
import signal
import sys
import time
from pathlib import Path

from PySide6.QtCore import Q_ARG, Q_RETURN_ARG, QEvent, QMetaObject, QObject, Qt, QUrl
from PySide6.QtGui import QInputMethodEvent, QInputMethodQueryEvent
from PySide6.QtQml import QQmlComponent, QQmlEngine
from PySide6.QtQuick import QQuickWindow  # noqa: F401
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

plugin, directory = map(Path, sys.argv[1:])
app = QApplication([])
engine = QQmlEngine()
engine.addImportPath(str(plugin))
component = QQmlComponent(engine)
component.setData(b'''import QtQuick
import QtQuick.Window
import QMLTermWidget 2.0
Window {
    width: 640; height: 360; visible: true
    property alias terminal: display
    property alias session: ptySession
    function start(spec) {
        ptySession.shellProgram = spec.program
        ptySession.shellProgramArgs = spec.arguments
        ptySession.initialWorkingDirectory = spec.cwd
        ptySession.configureEnvironment(spec.environment)
        ptySession.startShellProgram()
    }
    QMLTermSession { id: ptySession; objectName: "probeSession"; historySize: 10000 }
    QMLTermWidget { id: display; objectName: "probeDisplay"; anchors.fill: parent; session: ptySession; font.pixelSize: 20; blinkingCursor: false; useFBORendering: false }
}''', QUrl())
assert not component.isError(), [e.toString() for e in component.errors()]
window = component.create()
assert window is not None
terminal = window.findChild(QObject, "probeDisplay")
session = window.findChild(QObject, "probeSession")


def invoke(obj, name, *args, result=None):
    arguments = [Q_ARG(type(value), value) for value in args]
    if result:
        return QMetaObject.invokeMethod(obj, name, Q_RETURN_ARG(result), *arguments)
    return QMetaObject.invokeMethod(obj, name, *arguments)


def until(condition, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if condition():
            return
        QTest.qWait(20)
    raise AssertionError("Native PTY probe timed out: " + str(session.property("history")))


child = directory / "中文 程序.py"
child.write_text('''import json, os, signal, sys, time, tty, subprocess
from pathlib import Path
from tempfile import NamedTemporaryFile
directory = Path(sys.argv[1])
def write_json(name, value):
    with NamedTemporaryFile("w", dir=directory, delete=False) as pending:
        json.dump(value, pending)
    os.replace(pending.name, directory / name)
def size(*args):
    write_json("size.json", list(os.get_terminal_size(0)))
signal.signal(signal.SIGWINCH, size)
tty.setraw(0)
size()
p = subprocess.Popen(["/bin/sh", "-c", "trap '' HUP; exec sleep 600"], start_new_session=False, process_group=0 if sys.platform == "linux" else None)
write_json("launch.json", {"argv": sys.argv[2:], "cwd": os.getcwd(), "env": os.environ.get("CALLER_VALUE"), "leak": os.environ.get("PRIVATE_PRIMARY_MARKER"), "child": p.pid})
os.write(1, "\\x1b[2J\\x1b[HA中e\\u0301B [a.*]\\r\\nREADY\\r\\n\\x1b[?2004h\\x1b[1;4H".encode())
data = b""
while not data.endswith(b"\\x1b[201~"):
    data += os.read(0, 4096)
write_json("paste.json", data.hex())
time.sleep(600)
''')
argv = ["", "  ", "$HOME", "$(literal)", "中文 空格", '引"号']
spec = {"program": sys.executable, "arguments": [str(child), str(directory), *argv], "cwd": str(directory),
        "environment": ["PATH=" + os.environ.get("PATH", os.defpath), "LANG=C.UTF-8", "CALLER_VALUE=来自窗口 B"]}
os.environ["PRIVATE_PRIMARY_MARKER"] = "must-not-leak"
QTest.qWait(100)
assert QMetaObject.invokeMethod(window, "start", Q_ARG("QVariant", spec))
until(lambda: (directory / "launch.json").is_file() and "A中" in session.property("history"))
launch = json.loads((directory / "launch.json").read_text())
pid = invoke(session, "getShellPID", result=int)
try:
    assert launch["argv"] == argv, launch
    assert launch["cwd"] == str(directory)
    assert launch["env"] == "来自窗口 B"
    assert launch["leak"] is None
    assert session.property("historySize") == 10000
    query = QInputMethodQueryEvent(Qt.ImEnabled | Qt.ImCursorRectangle | Qt.ImFont | Qt.ImCursorPosition | Qt.ImSurroundingText)
    def image_ready():
        QApplication.sendEvent(terminal, query)
        return str(query.value(Qt.ImSurroundingText)).startswith("A中")
    until(image_ready)
    assert query.value(Qt.ImEnabled) is True
    cursor = query.value(Qt.ImCursorRectangle)
    assert cursor is not None and cursor.width() > 0 and cursor.height() > 0, cursor
    assert query.value(Qt.ImCursorPosition) == 2, (query.value(Qt.ImCursorPosition), cursor, session.property("history"))
    preedit = QInputMethodEvent("拼音", [])
    QApplication.sendEvent(terminal, preedit)
    app.processEvents()
    commit = QInputMethodEvent()
    commit.setCommitString("中文e\u0301")
    QApplication.sendEvent(terminal, commit)
    assert invoke(terminal, "searchText", "[a.*]", True, result=bool)
    assert invoke(terminal, "selectedHistoryText", result=str) == "[a.*]"
    assert invoke(terminal, "searchText", "中e\u0301", True, result=bool)
    assert invoke(terminal, "selectedHistoryText", result=str) == "中e\u0301"
    invoke(terminal, "leaveHistory")
    invoke(terminal, "beginHistory")
    invoke(terminal, "moveHistory", 0, 0)
    invoke(terminal, "anchorHistory")
    invoke(terminal, "moveHistory", 1, 0)
    invoke(terminal, "moveHistory", 1, 0)
    assert invoke(terminal, "selectedHistoryText", result=str) == "A中e\u0301"
    invoke(terminal, "copyClipboard")
    assert app.clipboard().text() == "A中e\u0301"
    invoke(terminal, "leaveHistory")
    before = json.loads((directory / "size.json").read_text())
    window.setWidth(960)
    until(lambda: json.loads((directory / "size.json").read_text()) != before)
    invoke(terminal, "pasteText", "一\n二\x03")
    until(lambda: (directory / "paste.json").is_file())
    pasted = bytes.fromhex(json.loads((directory / "paste.json").read_text()))
    assert pasted == "中文e\u0301".encode() + b"\x1b[200~" + "一\r二\x03".encode() + b"\x1b[201~", pasted
    invoke(session, "close")
    def exited(target):
        if sys.platform == "linux":
            path = Path(f"/proc/{target}/stat")
            return not path.exists() or path.read_text().split(") ", 1)[1].startswith("Z")
        try:
            os.kill(target, 0)
            return False
        except ProcessLookupError:
            return True
    until(lambda: exited(pid) and exited(launch["child"]))
    print(json.dumps({"native": "passed", "argv": True, "environment": True, "cjkSelection": True,
                      "imeCommitAndCursorQuery": True, "bracketedPaste": True, "resize": True, "processGroupsReaped": True}))
finally:
    for target in (pid, launch["child"]):
        try:
            os.kill(target, signal.SIGKILL)
        except ProcessLookupError:
            pass
    window.close()
    window.deleteLater()
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
