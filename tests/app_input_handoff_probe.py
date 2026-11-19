"""
[INPUT]: 依赖真实共享 QML、会话注册和受控显示回调。
[OUTPUT]: 验证冷启动交接、当前会话注册和默认可见。
[POS]: 首次窗口显示的独立进程回归；不连接真实设备。
[PROTOCOL]: Update this header on change, then check AGENTS.md
"""

import json
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PySide6.QtCore import QObject, QTimer, QUrl, Signal
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtWidgets import QApplication
from shiboken6 import delete

import udeck
from udeck.apps import runtime
from udeck.apps.common.controller import AppController
from udeck.apps.common.library import Source
from udeck.icons import IconProvider

os.environ.setdefault('QT_QUICK_CONTROLS_STYLE', 'Basic')
mode = sys.argv[1]
with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    controller = None

    def make_controller(*_arguments):
        global controller
        controller = AppController('music', root / 'state', root / 'settings.json')
        content = root / 'empty-library'
        content.mkdir(exist_ok=True)
        controller.library.sources = [Source.create(content)]
        return controller

    if mode == 'registry':
        from PySide6.QtDBus import QDBusConnection

        from udeck.app_routing import APP_IDS, service_name
        from udeck.compatibility import ApplicationRouter
        from udeck.controller import ShellController
        from udeck.core import ConfigStore
        from udeck.mock import MockBackend

        class Windows(QObject):
            changed = Signal(list)
            failed = Signal(str)

            def entries(self):
                return []

        class Isolation(QObject):
            finished = Signal(bool)
            available, applied, pending = True, False, None

        application = QApplication([])
        bus = QDBusConnection.sessionBus()
        assert bus.isConnected()
        windows, isolation = Windows(), Isolation()
        controller = ShellController(MockBackend(), windows, ConfigStore(root / 'settings.json'), mock=True)
        ownership = []
        router = ApplicationRouter(controller, windows, SimpleNamespace(set_foreground=ownership.append),
                                   SimpleNamespace(available=True, release_all=lambda: None), isolation)
        router.window_active(True)
        app_id = APP_IDS['music']
        with patch.dict(os.environ, {'WAYLAND_DISPLAY': 'udeck-other-session-test'}):
            foreign_name = service_name(app_id)
        assert bus.registerService(foreign_name)
        assert not router.prepare_native_activation(app_id), 'Another session released desktop input'
        assert ownership[-1] is True
        current_name = service_name(app_id)
        assert bus.registerService(current_name)
        assert router.prepare_native_activation(app_id)
        assert ownership[-1] is False and router.mode == 'transition'
        router.close()
        controller.close()
        bus.unregisterService(current_name)
        bus.unregisterService(foreign_name)
    elif mode == 'direct':
        application = QApplication([])
        controller = make_controller()
        engine = QQmlApplicationEngine()
        engine.addImageProvider('desktop', IconProvider())
        engine.rootContext().setContextProperty('controller', controller)
        engine.rootContext().setContextProperty('windowed', True)
        engine.load(QUrl.fromLocalFile(str(Path(udeck.__file__).parent / 'apps/common/qml/Main.qml')))
        assert engine.rootObjects()
        window = engine.rootObjects()[0]
        assert window.isVisible(), 'Direct QML probes lost their default visible window'
        controller.close()
        window.setProperty('allowClose', True)
        window.close()
        delete(engine)
    else:
        bus = SimpleNamespace(isConnected=lambda: True, registerService=lambda _service: True,
                              registerObject=lambda *_arguments: True, unregisterObject=lambda _path: None,
                              unregisterService=lambda _service: None, asyncCall=lambda _message: None)
        connection = SimpleNamespace(sessionBus=lambda: bus, RegisterOption=runtime.QDBusConnection.RegisterOption)
        checks = []
        failures = []

        def handoff(_bus, _app_id, window, present, **_arguments):
            def inspect():
                try:
                    assert not window.isVisible(), 'Cold-start window appeared before input handoff'
                    checks.append('hidden-before-handoff')
                    present()
                    assert window.isVisible(), 'Completed input handoff did not present the window'
                    checks.append('visible-after-handoff')
                except AssertionError as error:
                    failures.append(str(error))
                finally:
                    QApplication.instance().quit()
            QTimer.singleShot(40, inspect)

        with patch.object(runtime, 'QDBusConnection', connection), \
                patch.object(runtime, 'QDBusInterface', lambda *_arguments: SimpleNamespace(isValid=lambda: False)), \
                patch.object(runtime, 'make_controller', make_controller), \
                patch.object(runtime, 'present_after_input_handoff', handoff):
            result = runtime.main(['music', '--no-input', '--data-dir', str(root / 'state')])
        assert not failures, failures
        assert result == 0 and checks == ['hidden-before-handoff', 'visible-after-handoff']
print(json.dumps({'mode': mode, 'passed': True}))
