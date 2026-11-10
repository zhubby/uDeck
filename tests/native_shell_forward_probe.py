import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

from PySide6.QtCore import QCoreApplication, QTimer

from udeck.app_routing import APP_IDS
from udeck.controller import ShellController
from udeck.core import ConfigStore
from udeck.mock import MockBackend
from udeck.terminal import APP_ID as TERMINAL_ID

app = QCoreApplication([])
with tempfile.TemporaryDirectory() as directory:
    shell = ShellController(MockBackend(), config=ConfigStore(Path(directory) / 'settings.json'), mock=True)
    shell.mock = False
    shell.window_service = SimpleNamespace(available=True)
    identifier = APP_IDS.get(sys.argv[1], TERMINAL_ID) + '.desktop'
    mode = sys.argv[2] if len(sys.argv) > 2 else 'success'
    spawned = []

    def spawn(*_args):
        assert mode == 'missing', 'The shell spawned a second process for an owned application'
        spawned.append(True)

    shell.catalog.launch = spawn
    completed = []
    shell.launchFinished.connect(lambda result: (completed.append(result), app.quit()))
    QTimer.singleShot(0, lambda: shell._launch({'id': identifier, 'name': sys.argv[1], 'icon': 'book'}))
    QTimer.singleShot(4000, app.quit)
    app.exec()
    try:
        assert completed, 'Asynchronous forwarding never completed'
        if mode == 'refused':
            assert 'request refused' in str(completed[-1][2]), completed
            assert identifier not in shell.config.data['recent']
        else:
            assert completed[-1][2] is None, completed
            assert identifier in shell.config.data['recent']
        assert bool(spawned) == (mode == 'missing')
    finally:
        shell.close()
print(json.dumps({'shellDirectForwarding': 'passed'}))
