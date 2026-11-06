import json
import os
import subprocess
import sys

import pytest


def test_all_qml_pages_render_without_engine_warnings(tmp_path):
    result = subprocess.run(
        [sys.executable, "-m", "udeck.main", "--mock", "--windowed", "--smoke-test",
         "--screenshot", str(tmp_path / "preview.png"), "--quit-after", "1.8"],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen", "PYTHONPATH": "src"},
        text=True, capture_output=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout.strip().splitlines()[-1])
    assert report["smoke"] == "passed"
    assert report["qmlErrors"] == []
    assert "Error" not in result.stderr
    assert (tmp_path / "preview.png").stat().st_size > 10000


@pytest.mark.parametrize(("windowed", "visibility"), [(False, "FullScreen"), (True, "Windowed")])
@pytest.mark.parametrize("present_action", [None, "home", "switcher", "quick-settings"])
def test_session_is_fullscreen_while_preview_stays_windowed(tmp_path, windowed, visibility, present_action):
    probe = """
import json
import sys
from pathlib import Path
from PySide6.QtCore import QTimer, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from udeck import main
from udeck.controller import ShellController
from udeck.core import ConfigStore
from udeck.mock import MockBackend

application = QGuiApplication([])
controller = ShellController(MockBackend(), config=ConfigStore(Path(sys.argv[1])), mock=True)
engine = QQmlApplicationEngine()
engine.addImageProvider('desktop', main.IconProvider())
context = engine.rootContext()
context.setContextProperty('controller', controller)
context.setContextProperty('appFont', application.font().family())
context.setContextProperty('windowedPreview', sys.argv[2] == 'True')
context.setContextProperty('headlessPreview', True)
engine.load(QUrl.fromLocalFile(str(Path(main.__file__).parent / 'qml/Main.qml')))
assert engine.rootObjects()
window = engine.rootObjects()[0]
def report():
    if sys.argv[3] != 'None':
        controller.dispatch(sys.argv[3])
        application.processEvents()
    print(json.dumps({'visibility': window.visibility().name}))
    application.exit(0)
QTimer.singleShot(200, report)
application.exec()
controller.close()
"""
    result = subprocess.run(
        [sys.executable, "-c", probe, str(tmp_path / "settings.json"), str(windowed), str(present_action)],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen", "QT_QUICK_BACKEND": "software", "PYTHONPATH": "src"},
        text=True, capture_output=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["visibility"] == visibility


@pytest.mark.parametrize(("page", "button", "expected"), [
    ("home", "LeftButton", "launch"),
    ("settings", "LeftButton", "menu"),
    ("home", "RightButton", "menu"),
    ("files", "RightButton", "menu"),
    ("files", "LeftButton", "select"),
    ("files", "double", "open"),
    ("home", "typing", "text"),
])
def test_lr_mouse_clicks_activate_items_or_open_context_menus(tmp_path, page, button, expected):
    probe = """
import json
import sys
from pathlib import Path
from PySide6.QtCore import QPoint, Qt, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtTest import QTest
from udeck import main
from udeck.controller import ShellController
from udeck.core import ConfigStore
from udeck.mock import MockBackend

application = QGuiApplication([])
controller = ShellController(MockBackend(), config=ConfigStore(Path(sys.argv[1])), mock=True)
controller.setPage(sys.argv[2])
engine = QQmlApplicationEngine()
engine.addImageProvider('desktop', main.IconProvider())
context = engine.rootContext()
context.setContextProperty('controller', controller)
context.setContextProperty('appFont', application.font().family())
context.setContextProperty('windowedPreview', True)
context.setContextProperty('headlessPreview', True)
engine.load(QUrl.fromLocalFile(str(Path(main.__file__).parent / 'qml/Main.qml')))
assert engine.rootObjects()
window = engine.rootObjects()[0]
initial_directory = controller.data['directory']
QTest.qWait(100)
if sys.argv[3] == 'double':
    QTest.mouseDClick(window, Qt.MouseButton.LeftButton, pos=QPoint(110, 300))
elif sys.argv[3] == 'typing':
    controller.dispatch('search')
    QTest.qWait(100)
    for key in (Qt.Key.Key_J, Qt.Key.Key_K, Qt.Key.Key_U, Qt.Key.Key_I):
        QTest.keyClick(window, key)
else:
    QTest.mouseClick(window, getattr(Qt.MouseButton, sys.argv[3]), pos=QPoint(110, 300))
QTest.qWait(50)
print(json.dumps({'modal': controller.modal.get('kind'), 'recent': controller.config.data['recent'], 'directoryChanged': controller.data['directory'] != initial_directory, 'text': controller.modal.get('text')}))
controller.close()
"""
    result = subprocess.run(
        [sys.executable, "-c", probe, str(tmp_path / "settings.json"), page, button],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen", "QT_QUICK_BACKEND": "software", "QT_QUICK_CONTROLS_STYLE": "Basic", "PYTHONPATH": "src"},
        text=True, capture_output=True, timeout=15,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout)
    if expected == "launch":
        assert report["recent"]
    elif expected == "select":
        assert not report["directoryChanged"]
        assert report["modal"] is None
    elif expected == "open":
        assert report["directoryChanged"]
    elif expected == "text":
        assert report["modal"] == "text"
        assert report["text"] == "jkui"
    else:
        assert report["modal"] == expected
