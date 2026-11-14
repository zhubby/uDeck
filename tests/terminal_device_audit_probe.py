"""Exercise native terminal menus and multiple windows in a real Qt session."""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path
from types import SimpleNamespace

from PySide6.QtCore import Q_ARG, Q_RETURN_ARG, QEvent, QEventLoop, QMetaObject, Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from udeck.core import ConfigStore
from udeck.terminal.core import LaunchRequest, TerminalPreferences
from udeck.terminal.main import Coordinator
from udeck.windows import WindowService

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--evdev-keyboard', action='store_true')
options = parser.parse_args()
options.output.mkdir(parents=True, exist_ok=True)
application = QApplication([])
application.setQuitOnLastWindowClosed(False)
application.setDesktopFileName('io.github.zhubby.uDeck.Terminal.Audit')
report = {'platform': application.platformName(), 'humanPhysicalInput': False, 'checks': {}}
windows = WindowService() if application.platformName() == 'wayland' else None
if windows:
    windows.start()
    assert windows.available


def pump(milliseconds=30):
    loop = QEventLoop()
    QTimer.singleShot(milliseconds, loop.quit)
    loop.exec()


def wait(predicate, timeout=8):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        pump()
    assert predicate(), 'Terminal condition timed out'


def items(window, name):
    pending, found = [window.contentItem()], []
    while pending:
        item = pending.pop()
        if item.objectName() == name:
            found.append(item)
        pending.extend(item.childItems())
    return found


def invoke(obj, name, *arguments, result=None):
    values = [Q_ARG(type(value), value) for value in arguments]
    if result:
        return QMetaObject.invokeMethod(obj, name, Q_RETURN_ARG(result), *values)
    return QMetaObject.invokeMethod(obj, name, *values)


def state(window):
    return window.property('state').toVariant()


with tempfile.TemporaryDirectory(prefix='udeck-terminal-audit-') as temporary:
    directory = Path(temporary)
    settings = ConfigStore(directory / 'settings.json')
    settings.data['preferences'].update(language='en', theme='classic')
    settings.save()
    preferences = TerminalPreferences(directory / 'terminal.json')
    coordinator = Coordinator(application, SimpleNamespace(mock=False, no_input=True, windowed=True),
                              preferences, time.monotonic())
    clipboard = application.clipboard().text()
    receiver = directory / 'receiver.py'
    receiver.write_text(
        "import os,sys,tty\nfrom pathlib import Path\n"
        "path=Path(sys.argv[1]);path.write_bytes(b'');tty.setraw(0)\n"
        "os.write(1,f'\\x1b]0;{path.stem}\\x07\\x1b[2J\\x1b[Halpha [literal.*] 中文e\\u0301\\r\\nBETA marker\\r\\n\\x1b[?2004h'.encode())\n"
        "while True:\n data=os.read(0,4096)\n with path.open('ab') as stream:stream.write(data)\n"
    )

    def launch(name):
        received = directory / (name + '.bin')
        coordinator.open(LaunchRequest(temporary, [sys.executable, str(receiver), str(received)],
                                       '', dict(os.environ), True))
        entry = coordinator.recent
        wait(lambda: received.exists() and bool(items(entry['window'], 'nativeTerminal'))
             and bool(entry['controller'].native_sessions))
        terminal = items(entry['window'], 'nativeTerminal')[0]
        wait(lambda: invoke(terminal, 'searchText', 'BETA marker', True, result=bool))
        invoke(terminal, 'leaveHistory')
        wait(lambda: entry['window'].title() == name)
        return entry, received

    def check(name, callback):
        try:
            callback()
            report['checks'][name] = {'passed': True}
        except Exception as error:
            report['checks'][name] = {'passed': False, 'error': str(error), 'traceback': traceback.format_exc()}
            if coordinator.recent:
                active = first['controller']
                focus = first['window'].activeFocusItem()
                report['checks'][name]['focusVisible'] = focus.isVisible() if focus else None
                report['checks'][name]['focusClass'] = focus.metaObject().className() if focus else None
                first['window'].grabWindow().save(str(options.output / (name + '-failure.png')))
                if active.mode != 'input':
                    active.dispatch('back')
                pump()
        (options.output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
        print(json.dumps({name: report['checks'][name]}, ensure_ascii=False), flush=True)

    def key(window, code, modifiers=Qt.KeyboardModifier.NoModifier):
        QTest.keyClick(window, code, modifiers)
        pump()

    try:
        first, received = launch('uTerminal audit A')
        second, _ = launch('uTerminal audit B')
        window, controller = first['window'], first['controller']
        terminal = items(window, 'nativeTerminal')[0]
        coordinator.activate(window)
        if windows:
            def activate():
                matching = [entry for entry in windows.handles.values() if entry['name'] == window.title()]
                if not matching:
                    return False
                windows.request(matching[-1]['id'], 'activate')
                pump(100)
                return window.isActive()
            wait(activate)
        else:
            wait(window.isActive)
        wait(lambda: window.activeFocusItem() is terminal)
        modifiers = Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier
        process_ids = [invoke(next(iter(entry['controller'].native_sessions.values())), 'getShellPID', result=int)
                       for entry in (first, second)]

        if windows:
            targets = {entry['window']: next(row['id'] for row in windows.handles.values()
                       if row['name'] == entry['window'].title()) for entry in (first, second)}

            def recent_window_activation():
                # Duplicate, changing titles must not select the first window.
                try:
                    for entry in (first, second):
                        entry['controller'].updateTitle(entry['controller'].current, 'same terminal title')
                    wait(lambda: all(current['window'].title() == 'same terminal title' for current in (first, second)))
                    for entry in (second, first, second):
                        target = entry['window']
                        windows.request(targets[target], 'activate')
                        wait(lambda target=target, entry=entry: target.isActive() and coordinator.recent is entry)
                        subprocess.run(['/usr/bin/udeckctl', 'home'], check=True, timeout=10,
                                       capture_output=True)
                        wait(lambda: not any(current['window'].isActive() for current in (first, second)))
                        coordinator.open(LaunchRequest(temporary, [], '', dict(os.environ), False))
                        wait(target.isActive, timeout=3)
                        assert len(coordinator.windows) == 2
                finally:
                    for entry, name in ((first, 'uTerminal audit A'), (second, 'uTerminal audit B')):
                        entry['controller'].updateTitle(entry['controller'].current, name)
                    # Also recover the fixture after a failed activation check.
                    windows.request(targets[window], 'activate')
                    wait(window.isActive)

            check('reopen-restores-recent-window-with-duplicate-titles', recent_window_activation)

        def font_sync():
            controller.command('settings')
            wait(lambda: window.activeFocusItem() is not terminal and controller.mode == 'settings')
            key(window, Qt.Key.Key_Down)
            key(window, Qt.Key.Key_Return)
            expected = preferences.font_size
            assert expected == 22
            pump(100)
            actual = [items(entry['window'], 'nativeTerminal')[0].property('font').pixelSize()
                      for entry in (first, second)]
            report['fontSizesAfterChange'] = actual
            for entry in (first, second):
                assert entry['window'].grabWindow().save(str(options.output / (entry['controller'].tabs.items[0]['title'][-1] + '-font.png')))
            assert actual == [expected, expected], f'Font size after one window changes it: {actual}, expected {[expected, expected]}'
            assert [state(entry['window'])['fontSize'] for entry in (first, second)] == [expected, expected]

        check('font-size-shared-between-windows', font_sync)
        # Restore only temporary fixture settings, including after a failed check.
        if controller.mode != 'input':
            controller.dispatch('back')
        preferences.font_size = 20
        for entry in (first, second):
            entry['controller'].changed.emit()
        pump()

        def menu_isolation():
            before = received.read_bytes()
            key(window, Qt.Key.Key_M, modifiers)
            wait(lambda: controller.mode == 'menu')
            count = len(controller.requests)
            key(window, Qt.Key.Key_T, modifiers)
            assert len(controller.requests) == count
            for _ in range(4):
                key(window, Qt.Key.Key_Down)
            key(window, Qt.Key.Key_Return)
            assert controller.mode == 'settings'
            key(window, Qt.Key.Key_Escape)
            wait(lambda: window.activeFocusItem() is terminal)
            assert received.read_bytes() == before

        check('menu-settings-isolation-and-focus', menu_isolation)

        def search_copy():
            before = received.read_bytes()
            key(window, Qt.Key.Key_F, modifiers)
            wait(lambda: controller.mode == 'search')
            for character in '[literal.*]':
                QTest.keyClick(window, character)
            key(window, Qt.Key.Key_Return)
            assert invoke(terminal, 'selectedHistoryText', result=str) == '[literal.*]'
            key(window, Qt.Key.Key_C, modifiers)
            wait(lambda: controller.mode == 'input')
            assert application.clipboard().text() == '[literal.*]'
            assert received.read_bytes() == before

        check('literal-search-and-copy-shortcut', search_copy)
        if controller.mode != 'input':
            controller.dispatch('back')

        def paste():
            before = received.read_bytes()
            original = 'alpha\nbeta'
            application.clipboard().setText(original)
            key(window, Qt.Key.Key_V, modifiers)
            wait(lambda: controller.mode == 'paste')
            assert controller.index == 0
            key(window, Qt.Key.Key_Escape)
            assert received.read_bytes() == before
            key(window, Qt.Key.Key_V, modifiers)
            wait(lambda: controller.mode == 'paste')
            application.clipboard().setText('must-not-replace-frozen-text')
            key(window, Qt.Key.Key_Down)
            key(window, Qt.Key.Key_Return)
            expected = before + b'\x1b[200~alpha\rbeta\x1b[201~'
            report['pasteResult'] = {'expected': expected.hex(), 'received': received.read_bytes().hex(),
                                     'mode': controller.mode, 'index': controller.index}
            wait(lambda: len(received.read_bytes()) >= len(expected))
            assert received.read_bytes() == expected, received.read_bytes().hex()
            wait(lambda: window.activeFocusItem() is terminal)

        check('dangerous-paste-cancel-freeze-and-brackets', paste)

        if options.evdev_keyboard:
            def kernel_keyboard():
                from evdev import UInput, ecodes

                assert windows and window.isActive(), 'Kernel input requires a focused Wayland fixture'
                codes = list(range(ecodes.KEY_ESC, ecodes.KEY_MICMUTE + 1))
                with UInput({ecodes.EV_KEY: codes}, name='uDeck terminal audit keyboard') as keyboard:
                    pump(700)
                    properties = subprocess.check_output(['udevadm', 'info', '--query=property',
                                                           '--name', keyboard.device.path], text=True)
                    report['kernelKeyboard'] = {'device': keyboard.device.path,
                        'udev': [line for line in properties.splitlines() if line.startswith(('ID_INPUT', 'ID_SEAT', 'LIBINPUT_IGNORE'))]}
                    if shutil.which('fcitx5-remote'):
                        method = subprocess.run(['fcitx5-remote'], capture_output=True, text=True, check=False)
                        report['kernelKeyboard']['inputMethodState'] = method.stdout.strip()

                    def received_is(expected):
                        actual = received.read_bytes()
                        report['kernelKeyboard'].update(expected=expected.hex(), received=actual.hex())
                        return actual == expected

                    def press(code, shortcut=False):
                        assert window.isActive(), 'Abort input if the fixture loses focus'
                        modifiers = [ecodes.KEY_LEFTCTRL, ecodes.KEY_LEFTSHIFT] if shortcut else []
                        try:
                            for modifier in modifiers:
                                keyboard.write(ecodes.EV_KEY, modifier, 1)
                            keyboard.write(ecodes.EV_KEY, code, 1)
                            keyboard.syn()
                            pump(35)
                        finally:
                            keyboard.write(ecodes.EV_KEY, code, 0)
                            for modifier in reversed(modifiers):
                                keyboard.write(ecodes.EV_KEY, modifier, 0)
                            keyboard.syn()
                        pump(50)

                    # Device creation precedes compositor hotplug. Verify the
                    # actual input path before checking characters/shortcuts.
                    initial = received.read_bytes()

                    def keyboard_ready():
                        press(ecodes.KEY_SPACE)
                        return len(received.read_bytes()) > len(initial)

                    wait(keyboard_ready)
                    pump(200)
                    report['kernelKeyboard']['readinessBytes'] = received.read_bytes()[len(initial):].hex()
                    before = received.read_bytes()
                    for code in (ecodes.KEY_A, ecodes.KEY_B, ecodes.KEY_X, ecodes.KEY_Y):
                        press(code)
                    expected = before + b'abxy'
                    wait(lambda: received_is(expected))
                    press(ecodes.KEY_M, shortcut=True)
                    wait(lambda: controller.mode == 'menu')
                    press(ecodes.KEY_DOWN)
                    press(ecodes.KEY_ESC)
                    wait(lambda: controller.mode == 'input')
                    press(ecodes.KEY_F, shortcut=True)
                    wait(lambda: controller.mode == 'search')
                    press(ecodes.KEY_A)
                    press(ecodes.KEY_ESC)
                    wait(lambda: controller.mode == 'input')
                    application.clipboard().setText('kernel\nkeyboard')
                    press(ecodes.KEY_V, shortcut=True)
                    wait(lambda: controller.mode == 'paste')
                    press(ecodes.KEY_DOWN)
                    press(ecodes.KEY_ENTER)
                    expected += b'\x1b[200~kernel\rkeyboard\x1b[201~'
                    wait(lambda: received_is(expected))
                    assert controller.mode == 'input'

            check('kernel-keyboard-compositor-menu-search-and-paste', kernel_keyboard)

        def settings_limits_and_persistence():
            controller.command('settings')
            wait(lambda: window.activeFocusItem() is not terminal and controller.mode == 'settings')
            for _ in range(10):
                key(window, Qt.Key.Key_Return)
            assert preferences.font_size == 14
            key(window, Qt.Key.Key_Down)
            for _ in range(10):
                key(window, Qt.Key.Key_Return)
            assert preferences.font_size == 28
            assert TerminalPreferences(preferences.path).font_size == 28
            key(window, Qt.Key.Key_Escape)
            assert terminal.property('font').pixelSize() == 28

        check('font-size-limits-and-reload', settings_limits_and_persistence)

        def close_cancel():
            key(window, Qt.Key.Key_W, modifiers)
            wait(lambda: controller.mode == 'close')
            key(window, Qt.Key.Key_Return)
            assert len(controller.requests) == 1
            assert invoke(next(iter(controller.native_sessions.values())), 'getShellPID', result=int) == process_ids[0]
            key(window, Qt.Key.Key_W, modifiers)
            key(window, Qt.Key.Key_Escape)
            assert controller.mode == 'input' and window.isVisible()

        check('close-default-cancel-preserves-process', close_cancel)
        assert not coordinator.errors, coordinator.errors
        report['qmlErrors'] = coordinator.errors
        report['allPassed'] = all(check['passed'] for check in report['checks'].values())
        (options.output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    finally:
        application.clipboard().setText(clipboard)
        coordinator.close()
        application.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        if windows:
            windows.close()

raise SystemExit(0 if report['allPassed'] else 1)
