import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QCoreApplication, QObject, Signal


class Windows(QObject):
    changed = Signal(object)

    def __init__(self, entries):
        super().__init__()
        self.items = entries
        self.requests = []

    def entries(self):
        return self.items

    def request(self, identifier, operation):
        self.requests.append((identifier, operation))


@pytest.fixture
def bridge():
    application = QCoreApplication.instance() or QCoreApplication([])
    spec = importlib.util.spec_from_file_location('performance_wayland_bridge',
        Path(__file__).resolve().parents[1] / 'tools/performance-wayland-bridge.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    token = 'udeck-perf-0123456789abcdef'
    app_id = 'io.github.zhubby.uDeck.Reader'
    existing = {'id': '1', 'appId': app_id, 'name': f'existing {token}'}
    windows = Windows([existing])
    control = module.ActivationBridge(windows, token)
    yield SimpleNamespace(control=control, windows=windows, token=token, app_id=app_id)
    control.timer.stop()
    assert application


def test_bridge_only_activates_unique_new_tagged_window(bridge):
    bridge.windows.items += [
        {'id': '2', 'appId': bridge.app_id, 'name': 'user window'},
        {'id': '3', 'appId': bridge.app_id, 'name': f'test {bridge.token}'},
        {'id': '4', 'appId': 'another.app', 'name': bridge.token},
    ]
    bridge.control.ActivateNativeApp(bridge.app_id)
    assert bridge.windows.requests == [('3', 'activate')]


def test_bridge_rejects_ambiguous_or_unmarked_windows(bridge):
    bridge.windows.items += [
        {'id': str(index), 'appId': bridge.app_id, 'name': bridge.token}
        for index in (2, 3)
    ]
    bridge.control.ActivateNativeApp(bridge.app_id)
    assert bridge.windows.requests == []
    assert bridge.control.pending == {}
    bridge.windows.items = bridge.windows.items[:1]
    bridge.control.ActivateNativeApp(bridge.app_id)
    assert bridge.windows.requests == []


def test_bridge_handles_window_arriving_after_activation_request(bridge):
    bridge.control.ActivateNativeApp(bridge.app_id)
    assert bridge.windows.requests == []
    bridge.windows.items.append({'id': '2', 'appId': bridge.app_id, 'name': bridge.token})
    bridge.windows.changed.emit(bridge.windows.items)
    assert bridge.windows.requests == [('2', 'activate')]
