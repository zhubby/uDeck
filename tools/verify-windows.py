import argparse
import json
import os
import select
import subprocess
import sys
import time
import uuid
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QTimer

from udeck.windows import WindowService


def test_window(title):
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlApplicationEngine

    application = QGuiApplication([sys.argv[0]])
    application.setApplicationName("udeck-window-probe")
    application.setDesktopFileName("io.github.zhubby.uDeck.WindowProbe")
    engine = QQmlApplicationEngine()
    engine.loadData(b'import QtQuick\nimport QtQuick.Window\nWindow { width: 420; height: 240; visible: true; color: "#25292c"; Text { anchors.centerIn: parent; text: "uDeck window protocol test"; color: "#edb866"; font.pixelSize: 24 } }')
    if not engine.rootObjects():
        return 2
    window = engine.rootObjects()[0]
    window.setTitle(title)
    ready = {"sent": False, "frame": {}}

    def first_frame():
        ready["frame"] = {"width": window.width(), "height": window.height(), "visibility": str(window.visibility())}
        if not ready["sent"]:
            ready["sent"] = True
            print(json.dumps({"ready": True}), flush=True)

    window.frameSwapped.connect(first_frame)
    application.aboutToQuit.connect(lambda: print(json.dumps(ready["frame"]), flush=True))
    QTimer.singleShot(20000, application.quit)
    return application.exec()


def main():
    parser = argparse.ArgumentParser(description="Only creates, activates and closes its own Wayland/Xwayland test windows")
    parser.add_argument("--window", help=argparse.SUPPRESS)
    parser.add_argument("--check-maximized", action="store_true", help="Additionally check foreign-protocol maximization and rendered geometry")
    options = parser.parse_args()
    if options.window:
        return test_window(options.window)
    application = QCoreApplication([])
    windows = WindowService()
    windows.start()
    if not windows.available:
        print(json.dumps({"passed": False, "error": "window protocol unavailable"}))
        return 1
    processes = []
    results = []

    def until(predicate, timeout=8):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            application.processEvents()
            if predicate():
                return
            time.sleep(0.02)
        raise RuntimeError("Timed out waiting for owned test window state")

    try:
        for platform in ("wayland", "xcb"):
            title = f"uDeck owned probe {platform} {uuid.uuid4().hex}"
            process = subprocess.Popen(
                [sys.executable, str(Path(__file__).resolve()), "--window", title],
                env={**os.environ, "QT_QPA_PLATFORM": platform},
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            )
            processes.append(process)
            until(lambda title=title, process=process: any(entry["name"] == title for entry in windows.entries()) or process.poll() is not None)
            entry = next((entry for entry in windows.entries() if entry["name"] == title), None)
            if entry is None:
                raise RuntimeError(f"{platform} failed: {process.communicate()[1]}")
            until(lambda process=process: bool(select.select([process.stdout], [], [], 0)[0]) or process.poll() is not None)
            if not json.loads(process.stdout.readline()).get("ready"):
                raise RuntimeError("Owned window did not render its first frame")
            identifier = entry["id"]
            windows.request(identifier, "activate")
            until(lambda identifier=identifier: windows.handles.get(identifier, {}).get("active"))
            if options.check_maximized:
                windows.request(identifier, "maximize")
                until(lambda identifier=identifier: windows.handles.get(identifier, {}).get("maximized"))
                time.sleep(2)
            windows.request(identifier, "close")
            until(lambda identifier=identifier, process=process: identifier not in windows.handles and process.poll() is not None)
            output, errors = process.communicate()
            errors = errors.strip()
            if process.returncode:
                raise RuntimeError(f"{platform}: {errors}")
            geometry = json.loads(output)
            if options.check_maximized and (geometry.get("width", 0) <= 420 or geometry.get("height", 0) <= 240):
                raise RuntimeError(f"{platform}: compositor reported maximized, but rendered geometry was {geometry}")
            results.append({"platform": platform, "enumerated": True, "activated": True, "maximizationChecked": options.check_maximized, "closed": True, "geometry": geometry, "warnings": errors.splitlines()})
        print(json.dumps({"passed": True, "windows": results}, ensure_ascii=False))
        return 0
    except RuntimeError as error:
        print(json.dumps({"passed": False, "windows": results, "error": str(error)}, ensure_ascii=False))
        return 1
    finally:
        for process in processes:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=5)
        windows.close()


if __name__ == "__main__":
    raise SystemExit(main())
