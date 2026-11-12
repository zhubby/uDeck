"""Exercise installed system services and real files in a native Wayland session.

Run as the desktop user with a private session bus and a fresh output directory:
    dbus-run-session -- python3 tests/system_device_probe.py /tmp/udeck-system-probe

The caller must supply the desktop's Wayland environment. Config, cache, data,
and trash are isolated below the output directory. System state is read only;
power confirmations and volume previews are cancelled. Only test files change.
"""
import hashlib
import json
import os
import sys
import time
from pathlib import Path

from PySide6.QtCore import QEvent, QEventLoop, Qt, QTimer, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine, QQmlEngine, QQmlExpression
from PySide6.QtTest import QTest

import udeck
from udeck.backend import SystemBackend
from udeck.controller import ShellController
from udeck.core import ConfigStore
from udeck.icons import IconProvider
from udeck.windows import APP_ID, WindowService


def tick(milliseconds=25):
    loop = QEventLoop()
    QTimer.singleShot(milliseconds, loop.quit)
    loop.exec()


def run(root):
    root.mkdir(parents=True, exist_ok=True)
    for key, name in [("XDG_CONFIG_HOME", "config"), ("XDG_DATA_HOME", "data"),
                      ("XDG_CACHE_HOME", "cache"), ("XDG_STATE_HOME", "state")]:
        os.environ[key] = str(root / "isolated" / name)
    os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")
    app = QGuiApplication([])
    app.setApplicationName(APP_ID)
    app.setDesktopFileName(APP_ID)
    assert app.platformName() == 'wayland'
    errors, backend_errors, checks = [], [], []
    backend, windows = SystemBackend(), WindowService()
    backend.failed.connect(lambda error: backend_errors.append(str(error)))
    controller = ShellController(backend, windows, ConfigStore(root / 'settings.json'))
    engine = QQmlApplicationEngine()
    engine.addImageProvider('desktop', IconProvider())
    engine.warnings.connect(lambda values: errors.extend(item.toString() for item in values))
    for key, value in [('controller', controller), ('windowedPreview', True), ('headlessPreview', True)]:
        engine.rootContext().setContextProperty(key, value)
    # Set the viewport before the visible QML window is mapped. A full-output
    # initial size can make the compositor maximize the surface and ignore resize.
    engine.setInitialProperties({'width': 960, 'height': 600})
    engine.load(QUrl.fromLocalFile(str(Path(udeck.__file__).parent / 'qml/Main.qml')))
    assert engine.rootObjects(), errors
    window = engine.rootObjects()[0]
    window.show()

    def wait(predicate, message, timeout=25):
        deadline = time.monotonic() + timeout
        while not predicate() and time.monotonic() < deadline:
            tick()
        assert predicate(), {'message': message, 'state': controller.snapshotJson, 'errors': errors, 'backend': backend_errors}

    def capture(name):
        tick(180)
        assert window.grabWindow().save(str(root / (name + '.png')))

    def dismiss():
        while controller.modal:
            QTest.keyClick(window, Qt.Key_Escape)
            tick(50)

    def browse(path):
        dismiss()
        controller._browse(path)
        wait(lambda: not controller.busy and controller.data['directory'] == str(path), 'browse ' + str(path))
        tick(80)

    def select(name):
        wait(lambda: any(item['name'] == name for item in controller.data['files']), 'find ' + name)
        controller.select(next(i for i, item in enumerate(controller.data['files']) if item['name'] == name))

    def finish_job():
        wait(lambda: not controller._file_active(), 'file task complete')
        assert controller.file_task['state'] == 'completed', controller.file_task
        dismiss()
        wait(lambda: not controller.busy, 'post-task browse')

    report = {'platform': app.platformName(), 'mock': False, 'checks': checks}
    try:
        assert QTest.qWaitForWindowExposed(window, 5000), 'Wayland window exposure'
        window.requestActivate()
        wait(window.isActive, 'Wayland window activation')
        window.setWidth(960)
        window.setHeight(600)
        tick(100)
        viewport = window.grabWindow().size().toTuple()
        assert viewport == (960, 600), viewport
        report['viewport'] = viewport
        windows.start()
        backend.start()
        wait(lambda: all(controller.data[part].get('available') for part in ['wifi', 'bluetooth', 'audio', 'brightness', 'battery', 'timezone']), 'real system services and hardware')
        wait(lambda: bool(controller.data['windows']), 'foreign toplevel window list')
        assert windows.available
        report['systemState'] = {
            'wifiAdapterCount': len(controller.data['wifi']['devices']),
            'bluetoothAvailable': controller.data['bluetooth']['available'],
            'audioOutputCount': len(controller.data['audio']['outputs']),
            'audioInputCount': len(controller.data['audio']['inputs']),
            'brightnessAvailable': controller.data['brightness']['available'],
            'battery': controller.data['battery'],
            'timezone': controller.data['timezone']['current'],
            'windowCount': len(controller.data['windows']),
        }
        checks.append('real-wifi-bluetooth-pipewire-backlight-timezone-battery-and-wayland-state')
        assert controller.applications
        controller.setPage('apps')
        controller.dispatch('search')
        controller.editText('uDeck')
        controller.dispatch('accept')
        assert controller._items()
        assert all('udeck' in (str(item['name']) + str(item.get('subtitle', ''))).casefold() for item in controller._items())
        capture('apps-search')
        checks.append('real-desktop-catalog-and-search')
        controller.setPage('windows')
        native_windows = [(i, row) for i, row in enumerate(controller._items())
                          if row['appId'].startswith(APP_ID + '.')]
        assert native_windows
        for index, row in native_windows:
            controller.select(index)
            tick(80)
            # Inspect delegates in QML; do not take Python ownership of their
            # temporary QQuickItem wrappers while ListView may recycle them.
            expression = QQmlExpression(QQmlEngine.contextForObject(window), window, '''
                JSON.stringify((function() {
                    for (const child of itemList.currentItem.children)
                        if (child.objectName === 'systemSettingIcon')
                            return {iconName: child.iconName, nativeKind: child.nativeKind}
                    return null
                })())
            ''')
            value, _ = expression.evaluate()
            assert not expression.hasError(), expression.error().toString()
            icon = json.loads(value)
            assert icon and icon['iconName'] == row['icon'], (row, icon)
            assert icon['nativeKind'] == row['appId'].split('.')[-1].lower(), (row, icon)
        report['runningNativeIcons'] = [row['appId'] for _, row in native_windows]
        controller.select(0)
        capture('running')
        checks.append('real-running-window-titles-and-icons')
        controller.setPage('settings')
        capture('system-settings')
        for identifier in ['wifi', 'hotspot', 'bluetooth', 'output', 'microphone', 'volume', 'brightness', 'battery', 'timezone', 'language', 'theme', 'sharing']:
            index = next(i for i, row in enumerate(controller._items()) if row['id'] == identifier)
            controller.select(index)
            QTest.keyClick(window, Qt.Key_Return)
            wait(lambda: bool(controller.modal), 'settings ' + identifier)
            capture('system-' + identifier)
            dismiss()
            assert controller.navigation.index == index, identifier
        checks.append('real-settings-open-cancel-focus-preserved-12-sections')
        for identifier in ['logout', 'reboot', 'poweroff']:
            controller.activateSetting(identifier)
            assert controller.modal['kind'] == 'confirm'
            dismiss()
        checks.append('session-power-confirmations-cancelled')
        before = dict(controller.data['audio'])
        controller.activateSetting('volume-level')
        assert controller.modal['kind'] == 'slider'
        QTest.keyClick(window, Qt.Key_Right)
        dismiss()
        assert controller.data['audio'] == before
        checks.append('volume-preview-cancel-keeps-real-output-unchanged')
        for language, theme in [('en', 'dark'), ('zh_CN', 'classic')]:
            controller.setLanguage(language)
            controller.setTheme(theme)
            capture('system-' + language + '-' + theme)
        checks.append('isolated-language-theme-round-trip')

        content = root / 'files'
        content.mkdir()
        destination = content / 'destination'
        destination.mkdir()
        original = content / '中文 ; literal %U.txt'
        payload = ('中文 original bytes\n' * 1024).encode()
        original.write_bytes(payload)
        (content / '.hidden.txt').write_text('hidden')
        (content / 'track2.txt').write_text('2')
        (content / 'track10.txt').write_text('10')
        controller.setPage('files')
        wait(lambda: not controller.busy, 'enter files')
        browse(content)
        assert '.hidden.txt' not in [item['name'] for item in controller.data['files']]
        controller._execute_option({'action': 'hidden'})
        wait(lambda: any(item['name'] == '.hidden.txt' for item in controller.data['files']), 'show hidden')
        controller._execute_option({'action': 'hidden'})
        wait(lambda: not controller.busy, 'hide hidden')
        select(original.name)
        controller.fileAction('rename', '')
        controller.editText('已改名.txt')
        QTest.keyClick(window, Qt.Key_Return)
        renamed = content / '已改名.txt'
        wait(lambda: not controller.busy and renamed.exists(), 'rename')
        assert controller._file_current()['path'] == str(renamed)
        controller.fileAction('copy', '')
        browse(destination)
        controller.fileAction('paste', '')
        finish_job()
        assert (destination / renamed.name).read_bytes() == payload
        controller.fileAction('paste', '')
        assert controller.modal['kind'] == 'menu'
        controller.chooseModal(next(i for i, item in enumerate(controller.modal['options']) if item.get('command') == 'paste-keep'))
        finish_job()
        assert (destination / '已改名 (2).txt').read_bytes() == payload
        capture('files-copied')
        checks.append('real-unicode-rename-focus-copy-conflict-keep-both-byte-check')
        browse(content)
        select(renamed.name)
        controller.fileAction('cut', '')
        browse(destination)
        controller.fileAction('paste-keep', '')
        finish_job()
        assert not renamed.exists() and controller.clipboard is None
        moved = destination / '已改名 (3).txt'
        assert moved.read_bytes() == payload
        checks.append('real-cut-paste-clears-clipboard-and-keeps-existing-files')
        browse(destination)
        select(moved.name)
        controller.fileAction('preview', '')
        wait(lambda: controller.modal.get('previewType') == 'text', 'real text preview')
        capture('files-preview')
        dismiss()
        controller.fileAction('trash', '')
        assert controller.modal['kind'] == 'confirm'
        controller.chooseModal(1)
        finish_job()
        assert not moved.exists()
        browse('trash:///')
        select(moved.name)
        controller.fileAction('restore', '')
        controller.chooseModal(1)
        finish_job()
        assert moved.read_bytes() == payload
        checks.append('real-gio-trash-list-and-restore-original-bytes')
        browse(destination)
        (destination / 'external.txt').write_text('external')
        wait(lambda: any(item['name'] == 'external.txt' for item in controller.data['files']), 'watch external create')
        (destination / 'external.txt').unlink()
        wait(lambda: not any(item['name'] == 'external.txt' for item in controller.data['files']), 'watch external remove')
        capture('files-final')
        checks.append('real-filesystem-watcher-create-and-remove')
        controller._file_start_job('copy', [str(moved)], str(root / 'missing-destination'))
        wait(lambda: not controller._file_active(), 'failure report')
        assert controller.file_task['state'] == 'failed'
        assert moved.read_bytes() == payload
        dismiss()
        wait(lambda: not controller.busy, 'recovery browse')
        recovered = root / 'recovered'
        recovered.mkdir()
        controller._file_start_job('copy', [str(moved)], str(recovered))
        finish_job()
        assert (recovered / moved.name).read_bytes() == payload
        checks.append('file-job-failure-preserves-source-and-next-job-recovers')
        report.update(passed=True, qmlErrors=errors, backendErrors=backend_errors,
                      payloadSha256=hashlib.sha256(payload).hexdigest(), catalogCount=len(controller.applications))
        assert not errors and not backend_errors, report
    except Exception as error:
        report.update(passed=False, error=repr(error), qmlErrors=errors, backendErrors=backend_errors)
        capture('failure')
        raise
    finally:
        (root / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
        window.close()
        engine.deleteLater()
        app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        controller.close()
        backend.close()
        windows.close()
    print(json.dumps(report, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    run(Path(sys.argv[1]))
