import json
import os
import select
import subprocess
import sys
import time
import uuid

from PySide6.QtCore import QCoreApplication
from PySide6.QtDBus import QDBusConnection, QDBusInterface

from udeck.virtual_input import VirtualInput
from udeck.windows import APP_ID, WindowService

PROBE = '''
import json
import sys
from PySide6.QtCore import QSocketNotifier
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
application = QGuiApplication([])
application.setDesktopFileName('io.github.zhubby.uDeck.CompatibilityProbe')
engine = QQmlApplicationEngine()
engine.loadData(b'import QtQuick\\nimport QtQuick.Window\\nWindow { id: screen; width:1280; height:720; visible:true; visibility:Window.FullScreen; color:"#24282b"; property var keys:[]; property var buttons:[]; property int moves:0; property int wheels:0; Text { anchors.centerIn:parent; text:"uDeck application input check"; font.pixelSize:36; color:"#edb866" } FocusScope { anchors.fill:parent; focus:true; Keys.onPressed: function(event) { screen.keys = screen.keys.concat([{key:event.key, modifiers:event.modifiers}]); event.accepted=true } } MouseArea { anchors.fill:parent; hoverEnabled:true; acceptedButtons:Qt.LeftButton|Qt.RightButton; onPressed: function(mouse) { screen.buttons=screen.buttons.concat(["down:"+mouse.button]) }; onReleased: function(mouse) { screen.buttons=screen.buttons.concat(["up:"+mouse.button]) }; onPositionChanged: screen.moves++; onWheel: screen.wheels++ } }')
window = engine.rootObjects()[0]
window.setTitle(sys.argv[1])
ready = False
def first_frame():
    global ready
    if not ready:
        ready = True
        print(json.dumps({'ready':True}), flush=True)
window.frameSwapped.connect(first_frame)
def command(*arguments):
    message = sys.stdin.readline().strip()
    if message == 'reset':
        window.setProperty('keys', [])
        window.setProperty('buttons', [])
        window.setProperty('moves', 0)
        window.setProperty('wheels', 0)
        print(json.dumps({'reset':True}), flush=True)
    elif message == 'report':
        print(json.dumps({field: window.property(field).toVariant() if hasattr(window.property(field), 'toVariant') else window.property(field) for field in ('keys','buttons','moves','wheels')}), flush=True)
notifier = QSocketNotifier(sys.stdin.fileno(), QSocketNotifier.Type.Read)
notifier.activated.connect(command)
raise SystemExit(application.exec())
'''


def main():
    application = QCoreApplication([])
    windows = WindowService()
    windows.start()
    output = VirtualInput()
    output.start()
    if not windows.available or not output.available:
        raise RuntimeError(output.error or 'Window protocol unavailable')
    control = QDBusInterface(APP_ID, '/io/github/zhubby/uDeck', APP_ID + '.Control', QDBusConnection.sessionBus())
    checks, processes = [], []

    def until(predicate, timeout=8):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            application.processEvents()
            if predicate():
                return
            time.sleep(0.01)
        raise RuntimeError('Owned window input probe timed out')

    def pump(seconds):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            application.processEvents()
            time.sleep(0.01)

    def receive(process):
        until(lambda: bool(select.select([process.stdout], [], [], 0)[0]) or process.poll() is not None)
        line = process.stdout.readline()
        if not line:
            raise RuntimeError(process.stderr.read())
        return json.loads(line)

    try:
        for platform in ('wayland', 'xcb'):
            title = 'uDeck owned application probe ' + uuid.uuid4().hex
            process = subprocess.Popen([sys.executable, '-c', PROBE, title], env={**os.environ, 'QT_QPA_PLATFORM': platform},
                                       stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            processes.append(process)
            assert receive(process)['ready']
            until(lambda title=title: any(entry['name'] == title for entry in windows.entries()))
            identifier = next(entry['id'] for entry in windows.entries() if entry['name'] == title)
            windows.request(identifier, 'activate')
            until(lambda identifier=identifier: windows.handles.get(identifier, {}).get('active'))
            output.move(0, 0)
            pump(0.2)
            process.stdin.write('reset\n')
            process.stdin.flush()
            assert receive(process)['reset']
            for chord in ((28,), (1,), (42, 68), (42, 15), (15,), (29, 38)):
                output.chord(chord)
                pump(0.06)
            output.button(272, True)
            for _step in range(5):
                output.move(10, 3)
                pump(0.03)
            output.button(272, False)
            output.button(273, True)
            output.button(273, False)
            output.scroll(1)
            pump(0.2)
            process.stdin.write('report\n')
            process.stdin.flush()
            report = receive(process)
            assert any(entry['key'] == 16777220 for entry in report['keys']), report
            assert any(entry['key'] == 16777216 for entry in report['keys']), report
            assert any(entry['key'] == 76 and entry['modifiers'] & 67108864 for entry in report['keys']), report
            assert report['buttons'] == ['down:1', 'up:1', 'down:2', 'up:2'], report
            assert report['moves'] >= 5 and report['wheels'] >= 1, report
            assert not output.keys and not output.buttons
            checks.append({'platform': platform, 'passed': True, **report})
            windows.request(identifier, 'close')
            until(lambda process=process: process.poll() is not None)
            assert process.returncode == 0, process.stderr.read()
        print(json.dumps({'passed': True, 'syntheticOwnedWindows': True, 'checks': checks}, indent=2))
    finally:
        output.close()
        for process in processes:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=5)
        windows.close()
        if control.isValid():
            control.call('Home')


if __name__ == '__main__':
    main()
