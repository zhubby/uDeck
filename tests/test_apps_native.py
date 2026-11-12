import json
import os
import shutil
import subprocess
import sys

import pytest


def test_native_probe_wait_services_python_workers_before_the_wait_finishes():
    code = """
import sys
from threading import Event, Thread
from PySide6.QtCore import QCoreApplication, QTimer
from apps_native_probe import wait_events

application = QCoreApplication([])
released, completed = Event(), Event()
observed = []

def work():
    released.wait()
    completed.set()

worker = Thread(target=work)
worker.start()
observer = QTimer()
observer.setInterval(10)

def observe():
    if completed.is_set():
        observed.append(True)
        observer.stop()

observer.timeout.connect(observe)
observer.start()
QTimer.singleShot(0, released.set)
previous = sys.getswitchinterval()
try:
    sys.setswitchinterval(1000)
    wait_events(1000)
finally:
    sys.setswitchinterval(previous)
    observer.stop()
    released.set()
    worker.join(timeout=1)
assert observed == [True], observed
"""
    result = subprocess.run([sys.executable, "-c", code],
                            env={**os.environ, "PYTHONPATH": os.pathsep.join(("src", "tests"))},
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("app", ["music", "video", "reader", "browser"])
def test_real_engines_with_original_content_and_qml_workflows(tmp_path, app):
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg is required for original native fixtures")
    result = subprocess.run([sys.executable, "tests/apps_native_probe.py", app, str(tmp_path)],
                            env={**os.environ, "QT_QPA_PLATFORM": "offscreen", "QT_QUICK_BACKEND": "software",
                                 "PYTHONPATH": "src"}, capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout.strip().splitlines()[-1])
    assert report["qmlErrors"] == [] and report["checks"]


@pytest.mark.parametrize("app", ["music", "video", "browser", "reader", "emulator"])
@pytest.mark.parametrize("language", ["en", "zh_CN"])
def test_native_app_empty_library_menus_and_translations(tmp_path, app, language):
    result = subprocess.run([sys.executable, "-m", "udeck.apps.main", app, "--isolated", "--smoke-test",
                             "--language", language, "--width", "960", "--height", "600",
                             "--screenshot", str(tmp_path / "screen.png")],
                            env={**os.environ, "QT_QPA_PLATFORM": "offscreen", "QT_QUICK_BACKEND": "software",
                                 "PYTHONPATH": "src"}, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout.strip().splitlines()[-1])
    assert report["qmlErrors"] == []
    names = {"music": "音乐", "video": "视频", "browser": "浏览器", "reader": "阅读器", "emulator": "模拟器"}
    assert report["title"] == "uDeck " + (names[app] if language == "zh_CN" else app.title())
    assert report["appId"] == "io.github.zhubby.uDeck." + app.title()
    assert (tmp_path / "screen.png").stat().st_size > 10000
