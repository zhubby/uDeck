import argparse
import json
from pathlib import Path

from PySide6.QtCore import QEvent, Qt, QUrl
from PySide6.QtGui import QGuiApplication, QKeyEvent
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtTest import QTest

from udeck import main
from udeck.console import ConsolePanel, ConsoleShortcut
from udeck.controller import ShellController
from udeck.core import ConfigStore
from udeck.key_test import KeyTestFilter
from udeck.mock import MockBackend


def run():
    parser = argparse.ArgumentParser()
    parser.add_argument('output', type=Path)
    parser.add_argument('--language', default='zh_CN')
    parser.add_argument('--theme', default='classic')
    parser.add_argument('--width', type=int, default=1280)
    parser.add_argument('--height', type=int, default=720)
    options = parser.parse_args()
    options.output.mkdir(parents=True, exist_ok=True)
    application = QGuiApplication([])
    controller = ShellController(MockBackend(), config=ConfigStore(options.output / 'settings.json'), mock=True)
    controller.setLanguage(options.language)
    controller.setTheme(options.theme)
    panel = ConsolePanel(controller)
    engine = QQmlApplicationEngine()
    errors = []
    engine.warnings.connect(lambda rows: errors.extend(row.toString() for row in rows))
    engine.addImageProvider('desktop', main.IconProvider())
    for name, value in (('controller', controller), ('windowedPreview', True), ('headlessPreview', True)):
        engine.rootContext().setContextProperty(name, value)
    engine.load(QUrl.fromLocalFile(str(Path(main.__file__).parent / 'qml/Main.qml')))
    assert engine.rootObjects(), errors
    window = engine.rootObjects()[0]
    window.setWidth(options.width)
    window.setHeight(options.height)
    key_filter = KeyTestFilter(controller, window)
    shortcut = ConsoleShortcut(panel, window)
    try:
        QTest.qWait(100)
        controller.activateSetting('key-test')
        modifiers = Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier
        QTest.keyClick(window, Qt.Key.Key_Escape, modifiers)
        QTest.qWait(100)
        assert controller.modal['source'] == 'console'
        assert len(controller.modal['options']) == 5
        assert not controller.backend.actions
        assert window.grabWindow().save(str(options.output / 'console.png'))
        application.sendEvent(window, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, modifiers, '', True))
        assert len(controller._modals) == 1
        for _ in range(4):
            QTest.keyClick(window, Qt.Key.Key_Down)
        QTest.keyClick(window, Qt.Key.Key_Return)
        assert controller.modal['kind'] == 'confirm' and controller.modal['index'] == 0
        QTest.qWait(100)
        assert window.grabWindow().save(str(options.output / 'restart-confirm.png'))
        QTest.keyClick(window, Qt.Key.Key_Escape)
        assert controller.modal['source'] == 'console'
        QTest.keyClick(window, Qt.Key.Key_Escape)
        assert not controller.modal
        QTest.keyClick(window, Qt.Key.Key_Escape, modifiers)
        for _ in range(2):
            QTest.keyClick(window, Qt.Key.Key_Down)
        QTest.keyClick(window, Qt.Key.Key_Return)
        assert controller.navigation.page == 'settings' and not controller.modal
        assert not controller.backend.actions
        assert not errors, errors
        print(json.dumps({'qmlErrors': errors, 'actions': 5, 'shortcutFromKeyTest': True, 'repeatIgnored': True,
                          'powerConfirmation': True, 'settingsRoute': True}))
    finally:
        shortcut.close()
        window.removeEventFilter(key_filter)
        panel.close()
        controller.close()


if __name__ == '__main__':
    run()
