"""Real Qt events and rendered settings/recorder; all configuration is private."""

import argparse
import json
import tempfile
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine, QQmlEngine, QQmlExpression
from PySide6.QtTest import QTest

from udeck import main
from udeck.controller import ShellController
from udeck.core import ConfigStore
from udeck.mock import MockBackend
from udeck.shortcut_recorder import ShortcutRecorder


def run():
    parser = argparse.ArgumentParser()
    parser.add_argument('output', type=Path)
    parser.add_argument('--width', type=int, default=1280)
    parser.add_argument('--height', type=int, default=720)
    parser.add_argument('--language', default='en')
    parser.add_argument('--theme', default='classic')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    app = QGuiApplication([])
    app.setDesktopFileName('io.github.zhubby.uDeck')
    with tempfile.TemporaryDirectory() as directory:
        controller = ShellController(MockBackend(), config=ConfigStore(Path(directory) / 'settings.json'), mock=True)
        controller.setLanguage(args.language)
        controller.setTheme(args.theme)
        controller.setPage('settings')
        engine = QQmlApplicationEngine()
        errors, captures, bounds = [], [], []
        engine.warnings.connect(lambda values: errors.extend(value.toString() for value in values))
        engine.addImageProvider('desktop', main.IconProvider())
        for key, value in (('controller', controller), ('windowedPreview', True), ('headlessPreview', True)):
            engine.rootContext().setContextProperty(key, value)
        engine.load(QUrl.fromLocalFile(str(Path(main.__file__).parent / 'qml/Main.qml')))
        assert engine.rootObjects(), errors
        window = engine.rootObjects()[0]
        window.resize(args.width, args.height)
        recorder = ShortcutRecorder(controller, engine, window)
        controller.shortcut_recorder = recorder

        def choose(identifier):
            controller.chooseModal(next(i for i, value in enumerate(controller.modal['options']) if value['id'] == identifier))

        def capture(name, target=None):
            QTest.qWait(80)
            target = target or window
            expression = QQmlExpression(QQmlEngine.contextForObject(target), target, '''
                JSON.stringify((function() {
                    const result = []
                    function visit(item) {
                        if (!item.visible) return
                        if (['dialogPanel', 'dialogContent', 'shortcutRecordingTitle', 'recordedShortcut'].includes(item.objectName)) {
                            const point = item.mapToItem(contentItem, 0, 0)
                            result.push({name: item.objectName, x: point.x, y: point.y, width: item.width, height: item.height})
                        }
                        for (const child of item.children) visit(child)
                    }
                    visit(contentItem)
                    return result
                })())
            ''')
            value, undefined = expression.evaluate()
            assert not undefined and not expression.hasError(), expression.error().toString()
            rectangles = json.loads(value)
            assert len(rectangles) == 2
            for rect in rectangles:
                assert rect['x'] >= 0 and rect['y'] >= 0, rect
                assert rect['x'] + rect['width'] <= target.width() + 1, rect
                assert rect['y'] + rect['height'] <= target.height() + 1, rect
            bounds.append({'capture': name, 'rectangles': rectangles})
            assert target.grabWindow().save(str(args.output / (name + '.png')))
            captures.append(name)

        try:
            controller.activateSetting('shortcuts')
            capture('groups')
            choose('power')
            assert all(controller.modal['options'][index]['subtitle'].endswith(('Unbound', '未绑定')) for index in (2, 3, 4))
            capture('unbound-power-actions')
            controller.dispatch('back')
            choose('navigation')
            choose('terminal')
            capture('bindings')
            choose('0')
            assert recorder.window is not None
            capture('recording', recorder.window)
            QTest.keyClick(recorder.window, Qt.Key_VolumeUp)
            assert recorder.sequence == 'XF86AudioRaiseVolume'
            QTest.keyClick(recorder.window, Qt.Key_F24, Qt.ControlModifier)
            assert not recorder.sequence and recorder.error
            QTest.keyClick(recorder.window, Qt.Key_Z)
            assert not recorder.sequence and recorder.error
            QTest.keyClick(recorder.window, Qt.Key_P, Qt.ControlModifier | Qt.AltModifier)
            assert recorder.sequence == 'C-A-p'
            capture('recorded', recorder.window)
            QTest.keyClick(recorder.window, Qt.Key_Return)
            assert recorder.window is None and controller.modal['kind'] == 'confirm'
            assert ('全屏截屏' if args.language == 'zh_CN' else 'Full screen screenshot') in json.loads(controller.snapshotJson)['modal']['body']
            capture('conflict')
            controller.dispatch('right')
            controller.dispatch('accept')
            assert controller.shortcut_store.bindings()['terminal'] == ['C-A-p']
            assert controller.shortcut_store.bindings()['screenshot'] == ['Print']
            choose('clear')
            assert controller.shortcut_store.bindings()['terminal'] == []
            capture('cleared')
            choose('reset')
            assert controller.shortcut_store.bindings()['terminal'] == ['C-A-t']
            choose('0')
            QTest.keyClick(recorder.window, Qt.Key_Escape)
            assert recorder.window is None
            choose('add')
            assert recorder.timeout_timer.interval() == 15000
            recorder.timeout_timer.start(20)
            QTest.qWait(60)
            assert recorder.window is None
            recorder.timeout_timer.setInterval(15000)
            choose('add')
            recorder.activeChanged(False)
            assert recorder.window is None
            controller.dispatch('back')
            controller.dispatch('back')
            choose('reset-all')
            capture('reset-confirmation')
            controller.dispatch('right')
            controller.dispatch('accept')
            assert controller.shortcut_store.overrides == {}
            assert not controller.backend.actions and not errors, errors
            report = {'qmlErrors': errors, 'captures': captures, 'bounds': bounds,
                      'language': args.language, 'theme': args.theme, 'viewport': [args.width, args.height]}
            (args.output / 'report.json').write_text(json.dumps(report, indent=2))
            print(json.dumps(report))
        finally:
            recorder.close()
            window.close()
            controller.close()
            del engine
            app.processEvents()


if __name__ == '__main__':
    run()
