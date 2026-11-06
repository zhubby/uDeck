"""Check live foreground ownership in both desktop modes; no physical key claim.

Temporarily stops the udeck-fullscreen service, restores it, then leaves one
installed terminal/local shell open for performance and physical acceptance.
"""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from PySide6.QtCore import QCoreApplication

from udeck.windows import WindowService

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--output", type=Path, required=True)
options = parser.parse_args()
app = QCoreApplication([])
terminal_unit = "udeck-terminal-validation.service"
desktop_unit = "udeck-fullscreen.service"
report = {"physicalInput": "pending", "checks": {},
          "buildId": json.loads(Path("/usr/share/udeck-terminal/build-info.json").read_text())["buildId"]}
environment = {key: os.environ[key] for key in ("XDG_RUNTIME_DIR", "DBUS_SESSION_BUS_ADDRESS", "WAYLAND_DISPLAY", "DISPLAY")}
environment.update(QT_QPA_PLATFORM="wayland", QT_IM_MODULE="fcitx", XMODIFIERS="@im=fcitx",
                   XDG_CURRENT_DESKTOP="labwc:wlroots", QT_WAYLAND_DISABLE_WINDOWDECORATION="1")


def run(*arguments):
    return subprocess.run(arguments, check=True, capture_output=True, text=True)


def start(unit, program, *arguments):
    run("systemd-run", "--user", "--unit=" + unit, "--collect",
        *["--setenv=" + key + "=" + value for key, value in environment.items()], program, *arguments)


def doctor():
    return json.loads(run("/usr/bin/udeck-terminal", "--doctor").stdout)


def wait(condition, timeout=12):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if condition():
            return
        time.sleep(0.15)
    raise AssertionError("Input ownership timed out: " + json.dumps(doctor()))


def foreground():
    return doctor().get("input", {}).get("foreground", False)


def activate_terminal():
    windows = WindowService()
    try:
        windows.start()
        terminal = next(entry for entry in windows.entries() if entry["appId"] == "io.github.zhubby.uDeck.Terminal")
        windows.request(terminal["id"], "activate")
    finally:
        windows.close()
    wait(foreground)


assert doctor().get("running") is False, "Close existing terminal windows first"
assert run("systemctl", "--user", "is-active", desktop_unit).stdout.strip() == "active"
stopped = False
try:
    run("systemctl", "--user", "stop", desktop_unit)
    stopped = True
    start(terminal_unit, "/usr/bin/udeck-terminal")
    wait(foreground)
    state = doctor()
    assert state["input"]["broker"] is False, state
    assert state["input"]["pointer"]["blockedDevices"] == 1, state
    assert state["input"]["grabbed"] is True, state
    report["originalForeground"] = state
    report["checks"]["original-desktop-foreground-stock-grabs"] = "passed"
    helper = subprocess.Popen([sys.executable, "-c",
                              "from PySide6.QtWidgets import QApplication,QWidget;from PySide6.QtCore import QTimer;"
                              "a=QApplication([]);a.setApplicationName('udeck-input-focus-probe');w=QWidget();"
                              "w.setWindowTitle('uDeck input focus probe');w.resize(360,180);w.show();"
                              "QTimer.singleShot(4000,a.quit);a.exec()"])
    try:
        wait(lambda: not foreground())
        state = doctor()
        assert state["input"]["pointer"]["blockedDevices"] == 0 and state["input"]["grabbed"] is False, state
        report["originalBlurred"] = state
        report["checks"]["original-desktop-blur-releases-grabs"] = "passed"
    finally:
        helper.wait(timeout=8)
    activate_terminal()
    assert doctor()["input"]["pointer"]["blockedDevices"] == 1
    run("systemctl", "--user", "stop", terminal_unit)
    start(desktop_unit, "/usr/bin/udeck")
    stopped = False
    wait(lambda: subprocess.run(["systemctl", "--user", "is-active", desktop_unit], capture_output=True).returncode == 0)
    time.sleep(1)
    start(terminal_unit, "/usr/bin/udeck-terminal")
    wait(lambda: foreground() and doctor()["input"].get("routed"))
    state = doctor()
    assert state["input"]["broker"] is True and state["input"]["grabbed"] is True, state
    assert state["input"]["pointer"]["blockedDevices"] == 0, state
    report["udeckForeground"] = state
    report["checks"]["udeck-foreground-broker-owns-pointer"] = "passed"
    run("/usr/bin/udeckctl", "home")
    wait(lambda: not foreground())
    assert doctor()["input"]["grabbed"] is False
    report["udeckBlurred"] = doctor()
    report["checks"]["udeck-home-releases-gamepad-keeps-session"] = "passed"
    activate_terminal()
    wait(lambda: doctor()["input"].get("routed"))
    report["result"] = "passed"
finally:
    if stopped:
        start(desktop_unit, "/usr/bin/udeck")
    options.output.parent.mkdir(parents=True, exist_ok=True)
    options.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
print(json.dumps(report, ensure_ascii=False))
