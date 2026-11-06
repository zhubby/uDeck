import json
import os
import runpy
import select
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

from PySide6.QtCore import QObject, Slot
from PySide6.QtDBus import QDBusConnection
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine

from udeck.compatibility import ApplicationRouter
from udeck.controller import ShellController
from udeck.core import ConfigStore
from udeck.mock import MockBackend
from udeck.session_config import DirectionIsolation
from udeck.virtual_input import VirtualInput
from udeck.windows import APP_ID, WindowService


def main():
    application = QGuiApplication([])
    application.setDesktopFileName(APP_ID)
    engine = QQmlApplicationEngine()
    engine.loadData(b'import QtQuick\nimport QtQuick.Window\nWindow { id: screen; visible:true; width:1280; height:720; visibility:Window.FullScreen; property int arrows:0; property int modified:0; property int letters:0; FocusScope { focus:true; anchors.fill:parent; Keys.onPressed: function(event) { if ([Qt.Key_Up,Qt.Key_Down,Qt.Key_Left,Qt.Key_Right].indexOf(event.key)>=0) { if(event.modifiers) screen.modified++; else screen.arrows++ } else if(event.key===Qt.Key_J) screen.letters++; event.accepted=true } } }')
    window = engine.rootObjects()[0]
    output = VirtualInput()
    output.start()
    isolation = DirectionIsolation(output)

    class Control(QObject):
        @Slot(str, result=bool)
        def InputConfigApplied(self, token):
            return isolation.acknowledge(token)

    control = Control()
    bus = QDBusConnection.sessionBus()
    assert bus.registerService(APP_ID)
    assert bus.registerObject('/io/github/zhubby/uDeck', APP_ID + '.Control', control, QDBusConnection.RegisterOption.ExportAllSlots)
    assert isolation.available and output.available
    results = []
    isolation.finished.connect(results.append)

    def until(predicate, timeout=8):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            application.processEvents()
            if predicate():
                return
            time.sleep(0.01)
        raise RuntimeError('Isolation test timed out: ' + isolation.error)

    def pump(seconds=0.25):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            application.processEvents()
            time.sleep(0.01)

    try:
        until(window.isActive)
        isolation.request(True)
        until(lambda: bool(results))
        assert results[-1] and isolation.applied, isolation.error
        assert isolation.acknowledge('stale') is False
        for code in (103, 108, 105, 106):
            output.chord((code,))
        output.chord((29, 106))
        output.chord((36,))
        pump()
        blocked = {name: window.property(name) for name in ('arrows', 'modified', 'letters')}
        assert blocked == {'arrows': 0, 'modified': 1, 'letters': 1}, blocked
        results.clear()
        isolation.request(False)
        until(lambda: bool(results))
        assert results[-1] and not isolation.applied
        for code in (103, 108, 105, 106):
            output.chord((code,))
        pump()
        assert window.property('arrows') == 4
        routes = verify_routes(application, window, output, isolation, until, pump)
        print(json.dumps({'passed': True, 'syntheticOwnedCompositor': True, 'blocked': blocked,
                          'restoredArrows': window.property('arrows'), 'staleGenerationRejected': True,
                          'applicationRoutes': routes}, indent=2), flush=True)
    finally:
        isolation.restore()
        output.close()
        bus.unregisterObject('/io/github/zhubby/uDeck')
        bus.unregisterService(APP_ID)
        window.close()


def verify_routes(application, shell, output, isolation, until, pump):
    probe = runpy.run_path(str(Path(__file__).with_name('verify-application-input.py')))['PROBE']
    windows = WindowService()
    windows.start()
    ownership, results, processes = [], [], []
    with tempfile.TemporaryDirectory(prefix='udeck-routing-') as directory:
        controller = ShellController(MockBackend(), windows, ConfigStore(Path(directory) / 'settings.json'), mock=True)
        router = ApplicationRouter(controller, windows, SimpleNamespace(set_foreground=ownership.append), output, isolation)
        router.direction_status({'available': True})
        router.window_active(shell.isActive())
        shell.activeChanged.connect(lambda: router.window_active(shell.isActive()))
        controller.present.connect(windows.activate_shell)

        def receive(process):
            until(lambda: bool(select.select([process.stdout], [], [], 0)[0]) or process.poll() is not None)
            line = process.stdout.readline()
            assert line, process.stderr.read()
            return json.loads(line)

        def report(process):
            process.stdin.write('report\n')
            process.stdin.flush()
            return receive(process)

        def button(action):
            router.button(action, True)
            router.button(action, False)
            pump(0.08)

        try:
            for platform in ('wayland', 'xcb'):
                controller.config.data['applicationInput'].clear()
                title = 'uDeck routed ' + platform
                process = subprocess.Popen([sys.executable, '-c', probe, title], env={**os.environ, 'QT_QPA_PLATFORM': platform},
                                           stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                processes.append(process)
                assert receive(process)['ready']
                until(lambda title=title: router.mode == 'keyboard' and router.target and router.target['name'] == title)
                identifier = router.target['id']
                button('accept')
                button('back')
                button('context')
                router.shoulder('previous-page')
                router.shoulder('next-page')
                pump()
                keyboard = report(process)
                assert any(entry['key'] == 16777220 for entry in keyboard['keys']), keyboard
                assert any(entry['key'] == 16777216 for entry in keyboard['keys']), keyboard
                assert any(entry['key'] == 16777273 for entry in keyboard['keys']), keyboard
                button('quick-settings')
                until(lambda: shell.isActive() and router.mode == 'desktop')
                assert controller.modal['source'] == 'application' and controller.modal['index'] == 0
                router.action('down')
                pump()
                assert report(process)['keys'] == keyboard['keys']
                assert router.set_mode('pointer')
                until(lambda identifier=identifier: router.mode == 'pointer' and router.target and router.target['id'] == identifier)
                output.move(0, 0)
                pump()
                router.button('accept', True)
                router.direction('right', True)
                output.chord((106,))
                pump(0.2)
                router.direction('right', False)
                router.button('accept', False)
                button('context')
                router.shoulder('next-page')
                pump()
                pointer = report(process)
                assert pointer['keys'] == keyboard['keys'], pointer
                assert pointer['buttons'] == ['down:1', 'up:1', 'down:2', 'up:2'], pointer
                assert pointer['moves'] > 0 and pointer['wheels'] > 0, pointer
                assert not output.buttons and not output.keys and not router.motion.isActive()
                button('quick-settings')
                until(lambda: shell.isActive() and router.mode == 'desktop')
                assert router.set_mode('native')
                until(lambda: router.mode == 'native')
                assert ownership[-1] is False and not isolation.applied
                windows.request(identifier, 'close')
                until(lambda process=process: process.poll() is not None)
                assert process.returncode == 0, process.stderr.read()
                results.append({'platform': platform, 'keyboard': True, 'menuIsolated': True,
                                'pointerAndDrag': True, 'arrowsConsumed': True, 'nativeReleased': True})
        finally:
            router.close()
            controller.close()
            for process in processes:
                if process.poll() is None:
                    process.terminate()
                    process.wait(timeout=5)
            windows.close()
    return results


if __name__ == '__main__':
    main()
