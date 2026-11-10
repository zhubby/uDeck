"""Synthetic input through a real, disposable labwc and independent Qt clients.

Run inside a private D-Bus/Wayland session with the packaged labwc config and
udeckctl on PATH. This does not claim physical trackball acceptance.
"""

import json
import os
import runpy
import select
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from PySide6.QtCore import QObject, Signal
from PySide6.QtDBus import QDBusConnection
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine

from udeck.console import ConsolePanel
from udeck.controller import ShellController
from udeck.core import ConfigStore
from udeck.main import CONTROL_INTERFACE, CONTROL_PATH, Control, IconProvider
from udeck.mock import MockBackend
from udeck.trackball import TrackballInput
from udeck.virtual_input import VirtualInput
from udeck.windows import APP_ID, WindowService


class Pointer(QObject):
    middleButton = Signal(bool)
    middleButtonTimed = Signal(bool, float)
    reset = Signal()
    motion = Signal(int, int)

    def __init__(self):
        super().__init__()
        self.middleButton.connect(lambda pressed: self.middleButtonTimed.emit(pressed, time.monotonic()))


def main():
    application = QGuiApplication([])
    application.setDesktopFileName(APP_ID)
    windows, output, pointer = WindowService(), VirtualInput(), Pointer()
    windows.start()
    output.start()
    assert windows.available and output.available, output.error
    probe = runpy.run_path(str(Path(__file__).with_name('verify-application-input.py')))['PROBE']
    processes, checks = [], []

    def until(predicate, timeout=8):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            application.processEvents()
            if predicate():
                return
            time.sleep(0.01)
        raise RuntimeError('Trackball/console probe timed out')

    def pump(seconds=0.15):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            application.processEvents()
            time.sleep(0.01)

    def receive(process):
        until(lambda: bool(select.select([process.stdout], [], [], 0)[0]) or process.poll() is not None)
        line = process.stdout.readline()
        assert line, process.stderr.read()
        return json.loads(line)

    def report(process):
        process.stdin.write('report\n')
        process.stdin.flush()
        return receive(process)

    with tempfile.TemporaryDirectory(prefix='udeck-console-probe-') as directory:
        controller = ShellController(MockBackend(), windows, ConfigStore(Path(directory) / 'settings.json'), mock=True)
        panel = ConsolePanel(controller, windows)
        trackball = TrackballInput(pointer, controller, windows, output)
        control = Control(controller, windows)
        control.console_panel = panel
        bus = QDBusConnection.sessionBus()
        assert bus.registerService(APP_ID)
        assert bus.registerObject(CONTROL_PATH, CONTROL_INTERFACE, control, QDBusConnection.RegisterOption.ExportAllSlots)
        engine = QQmlApplicationEngine()
        engine.addImageProvider('desktop', IconProvider())
        for name, value in (('controller', controller), ('windowedPreview', True), ('headlessPreview', False)):
            engine.rootContext().setContextProperty(name, value)
        import udeck.main

        engine.load(str(Path(udeck.main.__file__).parent / 'qml/Main.qml'))
        assert engine.rootObjects()
        shell = engine.rootObjects()[0]
        shell.activeChanged.connect(lambda: controller.windowActive(shell.isActive()))
        controller.present.connect(windows.activate_shell)
        try:
            until(shell.isActive)
            for platform in ('wayland', 'xcb'):
                title = 'uDeck trackball check ' + platform
                process = subprocess.Popen([sys.executable, '-c', probe, title],
                                           env={**os.environ, 'QT_QPA_PLATFORM': platform},
                                           stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                processes.append(process)
                assert receive(process)['ready']
                until(lambda title=title: any(entry['name'] == title and entry['active'] for entry in windows.entries()))
                target = next(entry['id'] for entry in windows.entries() if entry['name'] == title)
                until(lambda target=target: not trackball.foreground and trackball.target and trackball.target[0] == target)
                output.move(0, 0)
                pointer.motion.emit(0, 12)
                pointer.motion.emit(1, 3)
                pointer.middleButton.emit(True)
                pump(0.05)
                pointer.middleButton.emit(False)
                pointer.middleButton.emit(True)
                pump(2.15)
                pointer.middleButton.emit(False)
                pump()
                inputs = report(process)
                assert inputs['buttons'] == ['down:1', 'up:1', 'down:2', 'up:2'], inputs
                assert inputs['moves'] >= 1, inputs
                # Ctrl+Shift+Esc must reach labwc's Execute -> a new udeckctl -> D-Bus.
                output.chord((29, 42, 1))
                until(lambda: controller.modal.get('source') == 'console' and shell.isActive())
                assert len(controller.modal['options']) == 5
                output.chord((1,))
                until(lambda target=target: not controller.modal and any(entry['id'] == target and entry['active'] for entry in windows.entries()))
                assert not controller.backend.actions
                # An interrupted gesture must not click in the new foreground window.
                pointer.middleButton.emit(True)
                pointer.reset.emit()
                pointer.middleButton.emit(False)
                pump()
                assert report(process)['buttons'] == inputs['buttons']
                checks.append({'platform': platform, 'clicks': inputs['buttons'], 'globalShortcut': True,
                               'restoredWindow': True, 'recoveryDidNotClick': True})
                windows.request(target, 'close')
                until(lambda process=process: process.poll() is not None)
                assert process.returncode == 0, process.stderr.read()
            print(json.dumps({'passed': True, 'syntheticOwnedCompositor': True, 'checks': checks}, indent=2))
        finally:
            trackball.close()
            panel.close()
            controller.close()
            output.close()
            for process in processes:
                if process.poll() is None:
                    process.terminate()
                    process.wait(timeout=5)
            windows.close()
            bus.unregisterObject(CONTROL_PATH)
            bus.unregisterService(APP_ID)


if __name__ == '__main__':
    main()
