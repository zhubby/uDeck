import os
import sys
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QCoreApplication

from udeck.pointer import PointerGuard


@pytest.fixture
def pointer_device(monkeypatch):
    application = QCoreApplication.instance() or QCoreApplication([])
    reader, writer = os.pipe()
    events = []
    ownership = []
    device = SimpleNamespace(
        path="/dev/input/event8", name="ClockworkPI uConsole Mouse", fd=reader,
        info=SimpleNamespace(vendor=0x1EAF, product=0x0024), uniq="20230713",
        capabilities=lambda: {1: [272, 273, 274], 2: [0, 1, 8]},
        active_keys=lambda: [], grab=lambda: ownership.append("grab"),
        ungrab=lambda: ownership.append("ungrab"), close=lambda: None,
        read=lambda: list(events),
    )
    monkeypatch.setitem(sys.modules, "evdev", SimpleNamespace(
        InputDevice=lambda path: device, list_devices=lambda: [device.path],
    ))
    guard = PointerGuard()
    guard._test_application = application
    yield guard, device, events, ownership
    guard.close()
    os.close(reader)
    os.close(writer)


def test_lr_are_shoulder_edges_and_pointer_motion_is_discarded(pointer_device):
    guard, device, events, ownership = pointer_device
    actions = []
    guard.action.connect(actions.append)
    guard.set_foreground(True)
    guard.start()
    events[:] = [SimpleNamespace(type=2, code=0, value=200),
                 SimpleNamespace(type=2, code=8, value=1),
                 SimpleNamespace(type=1, code=272, value=1),
                 SimpleNamespace(type=1, code=272, value=2),
                 SimpleNamespace(type=1, code=272, value=1),
                 SimpleNamespace(type=1, code=272, value=0),
                 SimpleNamespace(type=1, code=273, value=1)]
    guard._read(device.path)
    assert actions == ["previous-page", "next-page"]
    assert ownership == ["grab"]


def test_mouse_remains_blocked_when_third_party_app_has_focus(pointer_device):
    guard, device, events, ownership = pointer_device
    actions = []
    guard.action.connect(actions.append)
    guard.set_foreground(True)
    guard.start()
    guard.set_foreground(False)
    events[:] = [SimpleNamespace(type=1, code=272, value=1)]
    guard._read(device.path)
    assert actions == []
    assert ownership == ["grab"]
    guard.close()
    assert ownership == ["grab", "ungrab"]


def test_keyboard_and_gamepad_are_not_blocked(pointer_device):
    guard, device, events, ownership = pointer_device
    for capabilities in ({1: [28, 36, 37, 103], 2: []}, {1: [288, 289], 3: [0, 1]},
                         {1: [28, 272], 2: [0, 1]}):
        device.capabilities = lambda capabilities=capabilities: capabilities
        guard.start()
    assert ownership == []


def test_touchpad_absolute_capabilities_are_blocked_too(pointer_device):
    guard, device, events, ownership = pointer_device
    device.name = "External Touchpad"
    device.capabilities = lambda: {1: [272, 325, 330],
                                   3: [(0, SimpleNamespace(min=0, max=4096)),
                                       (1, SimpleNamespace(min=0, max=4096))]}
    guard.start()
    assert ownership == ["grab"]


def test_external_mouse_is_blocked_without_becoming_uconsole_shoulders(pointer_device):
    guard, device, events, ownership = pointer_device
    device.info.vendor = 0x1234
    device.name = "External Mouse"
    actions = []
    guard.action.connect(actions.append)
    guard.set_foreground(True)
    guard.start()
    events[:] = [SimpleNamespace(type=1, code=272, value=1)]
    guard._read(device.path)
    assert ownership == ["grab"]
    assert actions == []


def test_dropped_event_stream_does_not_create_phantom_shoulder_press(pointer_device):
    guard, device, events, ownership = pointer_device
    actions = []
    guard.action.connect(actions.append)
    guard.set_foreground(True)
    guard.start()
    device.active_keys = lambda: [272]
    events[:] = [SimpleNamespace(type=0, code=3, value=0),
                 SimpleNamespace(type=1, code=272, value=1),
                 SimpleNamespace(type=0, code=0, value=0),
                 SimpleNamespace(type=1, code=272, value=1)]
    guard._read(device.path)
    assert actions == []
    events[:] = [SimpleNamespace(type=1, code=272, value=0),
                 SimpleNamespace(type=1, code=272, value=1)]
    guard._read(device.path)
    assert actions == ["previous-page"]


def test_permission_failure_is_reported_and_scan_can_retry(pointer_device):
    guard, device, events, ownership = pointer_device
    status = {}
    guard.status.connect(status.update)
    grab = device.grab

    def denied():
        raise PermissionError("permission denied")

    device.grab = denied
    guard.start()
    assert status["pointer"]["errors"]
    assert status["pointer"]["blockedDevices"] == 0
    device.grab = grab
    guard._scan()
    assert status["pointer"]["errors"] == []
    assert status["pointer"]["blockedDevices"] == 1


def test_hotplug_releases_removed_pointer_and_grabs_it_again(pointer_device, monkeypatch):
    guard, device, events, ownership = pointer_device
    guard.start()
    monkeypatch.setattr(sys.modules["evdev"], "list_devices", lambda: [])
    guard._scan()
    assert ownership == ["grab", "ungrab"]
    monkeypatch.setattr(sys.modules["evdev"], "list_devices", lambda: [device.path])
    guard._scan()
    assert ownership == ["grab", "ungrab", "grab"]


def test_unchanged_pointer_scan_does_not_republish_the_ui_every_second(pointer_device):
    guard, device, events, ownership = pointer_device
    updates = []
    guard.status.connect(updates.append)
    guard.start()
    guard._scan()
    guard._scan()
    assert len(updates) == 1
