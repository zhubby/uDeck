"""Exercise real labwc, independent clients, shortcut IPC, isolation and PNG capture.

Run under dbus-run-session in a Linux test environment. The compositor, home,
configurations and all clients belong to this probe. No physical acceptance.
"""

import json
import os
import select
import subprocess
import sys
import tempfile
import time
from pathlib import Path

CLIENT = '''
import json, sys
from PySide6.QtCore import QEvent, QObject, QSocketNotifier
from PySide6.QtWidgets import QApplication, QWidget
app = QApplication([])
window = QWidget()
window.setWindowTitle(sys.argv[1])
window.resize(420, 260)
window.setStyleSheet('background: #238b5c')
keys = []
class Events(QObject):
    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.KeyPress:
            keys.append({'key': event.key(), 'modifiers': event.modifiers().value})
        return False
events = Events(window)
window.installEventFilter(events)
notifier = QSocketNotifier(sys.stdin.fileno(), QSocketNotifier.Type.Read)
def read():
    line = sys.stdin.readline()
    if line.strip() == 'report': print(json.dumps({'keys': keys, 'size': [window.width(), window.height()]}), flush=True)
notifier.activated.connect(read)
window.show()
print(json.dumps({'ready': True}), flush=True)
app.exec()
'''


def run(output_dir):
    from PySide6.QtCore import QUrl
    from PySide6.QtDBus import QDBusConnection
    from PySide6.QtGui import QGuiApplication, QImage
    from PySide6.QtQml import QQmlApplicationEngine

    from udeck.console import ConsolePanel
    from udeck.controller import ShellController
    from udeck.core import ConfigStore
    from udeck.main import CONTROL_INTERFACE, CONTROL_PATH, Control, IconProvider
    from udeck.mock import MockBackend
    from udeck.session_config import DirectionIsolation
    from udeck.shortcut_recorder import ShortcutRecorder
    from udeck.shortcut_session import ShortcutSession
    from udeck.shortcuts import ShortcutStore
    from udeck.virtual_input import VirtualInput
    from udeck.windows import APP_ID, WindowService

    with tempfile.TemporaryDirectory(prefix='udeck-shortcuts-live-') as temporary:
        private = Path(temporary)
        runtime, config = private / 'runtime', private / 'desktop-profile'
        runtime.mkdir(mode=0o700)
        config.mkdir(parents=True)
        os.environ.update({'XDG_RUNTIME_DIR': str(runtime), 'XDG_CONFIG_HOME': str(private / 'config'),
                           'XDG_STATE_HOME': str(private / 'state'), 'HOME': str(private),
                           'QT_QPA_PLATFORM': 'wayland', 'WLR_BACKENDS': 'headless', 'WLR_HEADLESS_OUTPUTS': '1',
                           'WLR_RENDERER': 'pixman', 'WLR_LIBINPUT_NO_DEVICES': '1', 'UDECK_SESSION': '1',
                           'UDECK_CONFIG_DIR': str(config)})
        os.environ['PATH'] = str(Path('packaging/bin').resolve()) + ':' + os.environ['PATH']
        original = '<labwc_config><keyboard><keybind key="W-r"><action name="Execute" command="old-runner"/></keybind></keyboard></labwc_config>'
        (config / 'rc.xml').write_text(original)
        (config / 'base.xml').write_text(original)
        (config / 'autostart').write_text('#!/bin/sh\nexit 0\n')
        (config / 'autostart').chmod(0o700)
        compositor_log = (output_dir / 'labwc.log').open('w')
        compositor = subprocess.Popen(['labwc', '--config-dir', str(config), '-s', '/bin/true'], stdout=compositor_log, stderr=compositor_log)
        os.environ['LABWC_PID'] = str(compositor.pid)
        processes = []
        application = None
        try:
            deadline = time.monotonic() + 8
            while not (runtime / 'wayland-0').exists():
                if compositor.poll() is not None or time.monotonic() > deadline:
                    raise RuntimeError('Disposable compositor failed; see labwc.log')
                time.sleep(0.02)
            os.environ['WAYLAND_DISPLAY'] = 'wayland-0'
            # Xwayland is normally lazy; labwc uses DISPLAY=:0 in this private container.
            os.environ['DISPLAY'] = ':0'
            application = QGuiApplication([])
            application.setDesktopFileName(APP_ID)
            windows, virtual = WindowService(), VirtualInput()
            windows.start()
            virtual.start()
            assert windows.available and virtual.available, virtual.error
            controller = ShellController(MockBackend(), windows, ConfigStore(private / 'config/udeck/settings.json'), mock=True)
            controller.mock = False
            controller.data['sessionInput'] = {'available': True, 'active': True, 'locked': False}
            manager = ShortcutSession(controller.shortcut_store, virtual)
            assert manager.available, manager.error
            controller.attachShortcutSession(manager)
            control = Control(controller, windows)
            control.shortcut_session = manager
            panel = ConsolePanel(controller, windows)
            panel.session_update({'sessionInput': controller.data['sessionInput']})
            control.console_panel = panel
            bus = QDBusConnection.sessionBus()
            assert bus.registerService(APP_ID)
            assert bus.registerObject(CONTROL_PATH, CONTROL_INTERFACE, control, QDBusConnection.RegisterOption.ExportAllSlots)
            engine = QQmlApplicationEngine()
            errors = []
            engine.warnings.connect(lambda values: errors.extend(value.toString() for value in values))
            engine.addImageProvider('desktop', IconProvider())
            for key, value in (('controller', controller), ('windowedPreview', True), ('headlessPreview', False)):
                engine.rootContext().setContextProperty(key, value)
            import udeck.main
            engine.load(QUrl.fromLocalFile(str(Path(udeck.main.__file__).parent / 'qml/Main.qml')))
            shell = engine.rootObjects()[0]
            controller.present.connect(windows.activate_shell)
            recorder = ShortcutRecorder(controller, engine, shell, virtual)
            controller.shortcut_recorder = recorder

            def pump(duration=0.15):
                end = time.monotonic() + duration
                while time.monotonic() < end:
                    application.processEvents()
                    time.sleep(0.005)

            def until(predicate, message, timeout=8):
                end = time.monotonic() + timeout
                while time.monotonic() < end:
                    application.processEvents()
                    if predicate():
                        return
                    time.sleep(0.005)
                raise AssertionError(message + ': ' + str(manager.error))

            def receive(process):
                until(lambda: bool(select.select([process.stdout], [], [], 0)[0]) or process.poll() is not None, 'client response')
                line = process.stdout.readline()
                assert line, process.stderr.read()
                return json.loads(line)

            until(shell.isActive, 'shell focus')
            manager.start()
            until(lambda: manager.applied and not manager.busy, 'initial takeover')
            assert 'old-runner' not in (config / 'rc.xml').read_text()
            assert Path(manager.backup).read_text() == original
            before = (config / 'rc.xml').read_bytes()
            control.shortcut_session = None  # Deliberately withhold the generation receipt.
            manager.apply(manager.store.propose('console', ['Ctrl+Alt+Q']))
            until(lambda: not manager.busy, 'failed reload rollback')
            assert manager.error and (config / 'rc.xml').read_bytes() == before
            assert not manager.store.path.exists()
            control.shortcut_session = manager
            pump()
            virtual.chord((29, 56, 16))
            pump()
            assert not controller.modal
            virtual.chord((29, 42, 1))
            until(lambda: controller.modal.get('source') == 'console', 'original binding restored after timeout')
            virtual.chord((1,))
            until(lambda: not controller.modal, 'dismiss restored console')
            cli = subprocess.Popen(['udeckctl', 'bind-console'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            until(lambda: cli.poll() is not None, 'legacy reload command')
            assert cli.returncode == 0, cli.stderr.read()
            until(lambda: manager.applied and not manager.busy and not manager.error, 'legacy reload confirmation')
            results = []
            for platform in ('wayland', 'xcb'):
                title = 'uDeck shortcut independent ' + platform
                process = subprocess.Popen([sys.executable, '-c', CLIENT, title],
                                           env={**os.environ, 'QT_QPA_PLATFORM': platform},
                                           stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                processes.append(process)
                assert receive(process)['ready']
                until(lambda title=title: any(row['name'] == title and row['active'] for row in windows.entries()), 'independent client focus')
                target = next(row['id'] for row in windows.entries() if row['name'] == title)
                virtual.chord((29, 42, 1))
                until(lambda: controller.modal.get('source') == 'console', 'default shortcut via compositor and CLI')
                virtual.chord((1,))
                until(lambda target=target: not controller.modal and any(row['id'] == target and row['active'] for row in windows.entries()), 'return original focus')
                controller._write_shortcut('console', ['Ctrl+Alt+Q'])
                until(lambda: not manager.busy, 'rebind confirmation')
                assert manager.store.bindings()['console'] == ['C-A-q']
                virtual.chord((29, 42, 1))
                pump()
                assert not controller.modal, 'old global shortcut remained active'
                virtual.chord((29, 56, 16))
                until(lambda: controller.modal.get('source') == 'console', 'new global shortcut')
                virtual.chord((1,))
                until(lambda: not controller.modal, 'dismiss rebound console')
                controller._write_shortcut('console', None)
                until(lambda: not manager.busy, 'restore defaults')
                process.stdin.write('report\n')
                process.stdin.flush()
                report = receive(process)
                assert report['size'] == [420, 260]
                assert any(row['key'] == 16777216 and row['modifiers'] for row in report['keys'])
                virtual.chord((29, 56, 25))
                until(lambda: not controller._capture_pending and 'Screenshot saved:' in str(controller.toast), 'real PNG capture')
                path = Path(str(controller.toast).split('Screenshot saved: ', 1)[1])
                image = QImage(str(path))
                geometry = application.primaryScreen().geometry()
                assert image.width() == geometry.width() and image.height() == geometry.height()
                assert image.width() > 420 and image.height() > 260
                assert any(image.pixelColor(x, y).name() == '#238b5c'
                           for x in range(0, image.width(), 20) for y in range(0, image.height(), 20))
                image.save(str(output_dir / ('desktop-' + platform + '.png')))
                windows.request(target, 'close')
                until(lambda process=process: process.poll() is not None, 'client close')
                results.append({'platform': platform, 'default': True, 'rebound': True, 'oldDisabled': True,
                                'originalFocusRestored': True, 'realDesktopPNG': [image.width(), image.height()]})

            controller.present.emit()
            until(shell.isActive, 'shell focus before recording')
            recorder.open('terminal', 0)
            until(lambda: recorder.ready and recorder.window is not None, 'recording inhibition acknowledgement')
            virtual.chord((56, 62))  # Alt+F4 must be captured, never close the recorder.
            until(lambda: recorder.sequence == 'A-F4', 'record Alt+F4')
            assert recorder.window is not None
            virtual.chord((29, 56, 20))  # Ctrl+Alt+T must not launch a terminal.
            until(lambda: recorder.sequence == 'C-A-t', 'record bound terminal shortcut')
            before = len(list((private / 'Pictures/Screenshots').glob('*.png')))
            virtual.chord((29, 56, 25))
            until(lambda: recorder.sequence == 'C-A-p', 'record screenshot combination')
            pump()
            assert len(list((private / 'Pictures/Screenshots').glob('*.png'))) == before
            virtual.chord((29, 56, 16))
            until(lambda: recorder.sequence == 'C-A-q' and not recorder.pressed, 'record free shortcut')
            recorder.window.grabWindow().save(str(output_dir / 'recorded.png'))
            recorder.confirm()
            until(lambda: not manager.busy, 'save recorded shortcut')
            assert manager.store.bindings()['terminal'] == ['C-A-q']
            recorder.open('terminal', 0)
            until(lambda: recorder.ready, 'recorder ready before cancellation')
            virtual.chord((1,))
            until(lambda: recorder.window is None and shell.isActive(), 'recording cancelled and shell focused')
            recorder.open('terminal', 0)
            until(lambda: recorder.ready, 'recorder ready before timeout')
            until(lambda: recorder.window is None and shell.isActive(), '15 second recording timeout', timeout=17)
            recorder.open('terminal', 0)
            until(lambda: recorder.ready, 'recorder ready before focus loss')
            client = subprocess.Popen([sys.executable, '-c', CLIENT, 'Recording focus loss client'],
                                      stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            processes.append(client)
            assert receive(client)['ready']
            until(lambda: recorder.window is None, 'recorder destroyed after focus loss')
            virtual.chord((29, 42, 1))
            until(lambda: controller.modal.get('source') == 'console', 'global bindings restored after focus loss')
            virtual.chord((1,))
            until(lambda: not controller.modal, 'dismiss console after focus loss')
            client.terminate()
            client.wait(timeout=5)
            controller.present.emit()
            until(shell.isActive, 'shell focus after recording checks')
            isolation = DirectionIsolation(virtual, coordinator=manager)
            isolation.request(True)
            until(lambda: isolation.applied, 'enable direction isolation')
            isolation.request(False)
            until(lambda: not manager.busy and not isolation.applied, 'disable direction isolation')
            assert 'key="C-A-q"' in (config / 'rc.xml').read_text()
            manager.close()
            manager = ShortcutSession(ShortcutStore(controller.shortcut_store.path), virtual)
            controller.attachShortcutSession(manager)
            control.shortcut_session = manager
            manager.start()
            until(lambda: manager.applied and not manager.busy, 'restart persistence')
            assert manager.store.bindings()['terminal'] == ['C-A-q']
            for action in ('logout', 'reboot', 'poweroff'):
                cli = subprocess.Popen(['udeckctl', action])
                until(lambda cli=cli: cli.poll() is not None, 'power action IPC')
                assert cli.returncode == 0 and controller.modal['kind'] == 'confirm' and controller.modal['index'] == 0
                controller.dispatch('accept')
                assert not controller.backend.actions
            assert not errors, errors
            summary = {'passed': True, 'physicalAcceptance': False, 'checks': results,
                       'recordingIsolated': True, 'directionModePreservedBindings': True,
                       'recordingCancel': True, 'recordingTimeoutSeconds': 15, 'recordingFocusLoss': True,
                       'liveRollback': True, 'legacyReload': True,
                       'restartPersistence': True, 'powerConfirmationOnly': True, 'qmlErrors': errors}
            (output_dir / 'report.json').write_text(json.dumps(summary, indent=2))
            print(json.dumps(summary), flush=True)
            recorder.close()
            panel.close()
            controller.close()
            virtual.close()
            windows.close()
            shell.close()
            bus.unregisterObject(CONTROL_PATH)
            bus.unregisterService(APP_ID)
            del engine
            application.processEvents()
            from shiboken6 import delete
            delete(application)
        finally:
            if application is not None:
                from shiboken6 import delete, isValid
                if isValid(application):
                    delete(application)
            for process in processes:
                if process.poll() is None:
                    process.terminate()
                    process.wait(timeout=5)
            compositor.terminate()
            compositor.wait(timeout=5)
            compositor_log.close()


if __name__ == '__main__':
    output = Path(sys.argv[1] if len(sys.argv) > 1 else 'artifacts/system-shortcuts/live').resolve()
    output.mkdir(parents=True, exist_ok=True)
    run(output)
