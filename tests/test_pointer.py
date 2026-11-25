"""
[INPUT]: 依赖指针服务、隔离 evdev 和 sysfs 能力位图。
[OUTPUT]: 验证输入归属、报告合帧、事件时间与热插拔筛选。
[POS]: 原始诊断与成对位移的边界回归，隔离输入丢帧。
[PROTOCOL]: Update this header on change, then check AGENTS.md
"""

import os
import sys
import time
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QCoreApplication

from udeck.pointer import PointerGuard


@pytest.fixture
def pointer_device(monkeypatch, tmp_path):
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
    guard.sysfs_root = tmp_path / 'input'
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


def test_shoulder_test_edges_release_on_keyup_sync_loss_and_unplug(pointer_device):
    guard, device, events, _ = pointer_device
    edges = []
    guard.button.connect(lambda action, pressed: edges.append((action, pressed)))
    guard.start()
    events[:] = [SimpleNamespace(type=1, code=272, value=value) for value in (1, 2, 1, 0)]
    guard._read(device.path)
    assert edges == [("previous-page", True), ("previous-page", False)]
    events[:] = [SimpleNamespace(type=1, code=273, value=1), SimpleNamespace(type=0, code=3, value=0)]
    guard._read(device.path)
    assert edges[-2:] == [("next-page", True), ("next-page", False)]
    events[:] = [SimpleNamespace(type=0, code=0, value=0), SimpleNamespace(type=1, code=272, value=1)]
    guard._read(device.path)
    guard._remove(device.path)
    assert edges[-2:] == [("previous-page", True), ("previous-page", False)]


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


def test_trackball_click_motion_and_scroll_are_diagnostic_only(pointer_device):
    guard, device, events, _ = pointer_device
    edges, motion, actions = [], [], []
    guard.middleButton.connect(edges.append)
    guard.motion.connect(lambda axis, value: motion.append((axis, value)))
    guard.action.connect(actions.append)
    guard.set_foreground(True)
    guard.start()
    events[:] = [SimpleNamespace(type=2, code=axis, value=value) for axis, value in ((0, 3), (1, -2), (8, 1))]
    events.extend(SimpleNamespace(type=1, code=274, value=value) for value in (1, 2, 1, 0))
    guard._read(device.path)
    assert motion == [(0, 3), (1, -2), (8, 1)] and edges == [True, False]
    assert not actions
    events[:] = [SimpleNamespace(type=1, code=274, value=1)]
    guard._read(device.path)
    guard._remove(device.path)
    assert edges[-2:] == [True, False]


def input_event(kind, code, value=0, *, stamp=12.5):
    return SimpleNamespace(type=kind, code=code, value=value, timestamp=lambda: stamp)


def test_motion_frames_pair_axes_and_keep_kernel_report_times(pointer_device, monkeypatch):
    monkeypatch.setattr('udeck.pointer.fcntl.ioctl', lambda *arguments: 0)
    guard, device, events, _ = pointer_device
    frames, raw = [], []
    guard.motionFrame.connect(lambda x, y, stamp: frames.append((x, y, stamp)))
    guard.motion.connect(lambda axis, value: raw.append((axis, value)))
    guard.start()
    events[:] = [input_event(2, 0, 3), input_event(2, 1, -2), input_event(2, 0, 4),
                 input_event(2, 8, 1), input_event(0, 0, stamp=12.125),
                 input_event(2, 0, -1), input_event(0, 0, stamp=12.25)]
    guard._read(device.path)
    assert frames == [(7, -2, 12.125), (-1, 0, 12.25)]
    assert raw == [(0, 3), (1, -2), (0, 4), (8, 1), (0, -1)]


def test_partial_motion_frame_waits_for_report_across_device_reads(pointer_device, monkeypatch):
    monkeypatch.setattr('udeck.pointer.fcntl.ioctl', lambda *arguments: 0)
    guard, device, events, _ = pointer_device
    frames = []
    guard.motionFrame.connect(lambda x, y, stamp: frames.append((x, y, stamp)))
    guard.start()
    events[:] = [input_event(2, 0, 5)]
    guard._read(device.path)
    assert frames == []
    events[:] = [input_event(2, 1, -1), input_event(0, 0, stamp=19.75)]
    guard._read(device.path)
    assert frames == [(5, -1, 19.75)]


def test_motion_frame_precedes_button_release_in_the_same_report(pointer_device, monkeypatch):
    monkeypatch.setattr('udeck.pointer.fcntl.ioctl', lambda *arguments: 0)
    guard, device, events, _ = pointer_device
    delivered = []
    guard.motionFrame.connect(lambda x, y, stamp: delivered.append(('motion', x, y, stamp)))
    guard.middleButton.connect(lambda pressed: delivered.append(('button', pressed)))
    guard.middleButtonTimed.connect(lambda pressed, stamp: delivered.append(('timed', pressed, stamp)))
    guard.start()
    events[:] = [input_event(1, 274, 1, stamp=12)]
    guard._read(device.path)
    delivered.clear()
    events[:] = [input_event(2, 0, 5), input_event(2, 1, -2),
                 input_event(1, 274, 0, stamp=12.125), input_event(0, 0, stamp=12.25)]
    guard._read(device.path)
    assert delivered == [('motion', 5, -2, 12.125), ('button', False), ('timed', False, 12.125)]


def test_dropped_report_discards_partial_and_recovery_motion(pointer_device, monkeypatch):
    monkeypatch.setattr('udeck.pointer.fcntl.ioctl', lambda *arguments: 0)
    guard, device, events, _ = pointer_device
    frames = []
    guard.motionFrame.connect(lambda x, y, stamp: frames.append((x, y, stamp)))
    guard.start()
    events[:] = [input_event(2, 0, 8), input_event(0, 3), input_event(2, 1, 999),
                 input_event(0, 0, stamp=20), input_event(2, 0, 2), input_event(2, 1, 3),
                 input_event(0, 0, stamp=20.25)]
    guard._read(device.path)
    assert frames == [(2, 3, 20.25)]


def test_unplug_discards_partial_motion_before_reusing_device_path(pointer_device, monkeypatch):
    monkeypatch.setattr('udeck.pointer.fcntl.ioctl', lambda *arguments: 0)
    guard, device, events, _ = pointer_device
    frames = []
    guard.motionFrame.connect(lambda x, y, stamp: frames.append((x, y, stamp)))
    guard.start()
    events[:] = [input_event(2, 0, 9)]
    guard._read(device.path)
    guard._remove(device.path)
    guard._scan()
    events[:] = [input_event(2, 1, 2), input_event(0, 0, stamp=21.5)]
    guard._read(device.path)
    assert frames == [(0, 2, 21.5)]


def test_motion_frame_falls_back_to_monotonic_read_time(pointer_device, monkeypatch):
    def unsupported_clock(*arguments):
        raise OSError('unsupported clock')

    monkeypatch.setattr('udeck.pointer.fcntl.ioctl', unsupported_clock)
    monkeypatch.setattr('udeck.pointer.time.monotonic', lambda: 22.25)
    guard, device, events, _ = pointer_device
    frames = []
    guard.motionFrame.connect(lambda x, y, stamp: frames.append((x, y, stamp)))
    guard.start()
    events[:] = [input_event(2, 0, 1), input_event(0, 0, stamp=999)]
    guard._read(device.path)
    assert frames == [(1, 0, 22.25)]


@pytest.mark.parametrize('gate', ['locked', 'suspended', 'diagnostic'])
def test_unsafe_partial_motion_is_not_replayed_after_recovery(pointer_device, tmp_path, gate):
    from udeck.controller import ShellController
    from udeck.core import ConfigStore
    from udeck.mock import MockBackend
    from udeck.trackball import TrackballInput
    from udeck.virtual_input import VirtualInput

    guard, device, events, _ = pointer_device
    controller = ShellController(MockBackend(), config=ConfigStore(tmp_path / 'config.json'), mock=True)
    output = VirtualInput()
    output.available = True
    output.pointer = 20
    requests = []
    output._request = lambda *arguments: requests.append(arguments)
    output._flush = lambda: None
    trackball = TrackballInput(guard, controller, output=output)
    controller.foregroundChanged.emit(True)
    guard.start()
    try:
        if gate == 'locked':
            controller.backend.updated.emit({'sessionInput': {'available': True, 'active': True, 'locked': True}})
        elif gate == 'suspended':
            controller.inputSuspended.emit(True)
        else:
            controller.activateSetting('key-test')
        events[:] = [input_event(2, 0, 9)]
        guard._read(device.path)
        if gate == 'locked':
            controller.backend.updated.emit({'sessionInput': {'available': True, 'active': True, 'locked': False}})
        elif gate == 'suspended':
            controller.inputSuspended.emit(False)
        else:
            controller.dispatch('back')
        events[:] = [input_event(0, 0)]
        guard._read(device.path)
        assert requests == []
        events[:] = [input_event(2, 0, 2), input_event(2, 1, -1), input_event(0, 0)]
        guard._read(device.path)
        assert [request[1] for request in requests] == [0, 4]
        assert (requests[0][3].value, requests[0][4].value) == (2048, -1024)
    finally:
        trackball.close()
        output.close()
        controller.close()


def test_wheel_and_external_pointer_do_not_create_trackball_frames(pointer_device):
    guard, device, events, _ = pointer_device
    frames = []
    guard.motionFrame.connect(lambda x, y, stamp: frames.append((x, y, stamp)))
    guard.start()
    events[:] = [input_event(2, 8, 1), input_event(0, 0)]
    guard._read(device.path)
    assert frames == []
    guard._remove(device.path)
    device.info.vendor = 0x1234
    device.name = 'External Mouse'
    guard._scan()
    events[:] = [input_event(2, 0, 3), input_event(2, 1, -2), input_event(0, 0)]
    guard._read(device.path)
    assert frames == []


def test_trackball_recovery_cancels_gesture_before_releasing_diagnostic_edge(pointer_device):
    guard, device, events, _ = pointer_device
    edges = []
    guard.middleButton.connect(lambda pressed: edges.append(('button', pressed)))
    guard.reset.connect(lambda: edges.append(('reset',)))
    guard.start()
    events[:] = [SimpleNamespace(type=1, code=274, value=1), SimpleNamespace(type=0, code=3, value=0)]
    guard._read(device.path)
    assert edges == [('button', True), ('reset',), ('button', False)]
    events[:] = [SimpleNamespace(type=0, code=0, value=0), SimpleNamespace(type=1, code=274, value=1)]
    guard._read(device.path)
    guard._remove(device.path)
    assert edges[-3:] == [('button', True), ('reset',), ('button', False)]


def test_native_trackball_recovery_does_not_confirm_selected_shell_app(pointer_device, tmp_path):
    from udeck.controller import ShellController
    from udeck.core import ConfigStore
    from udeck.mock import MockBackend
    from udeck.trackball import TrackballInput

    guard, device, events, _ = pointer_device
    controller = ShellController(MockBackend(), config=ConfigStore(tmp_path / 'config.json'), mock=True)
    trackball = TrackballInput(guard, controller)
    controller.foregroundChanged.emit(True)
    guard.start()
    try:
        events[:] = [SimpleNamespace(type=1, code=274, value=1), SimpleNamespace(type=0, code=3, value=0)]
        guard._read(device.path)
        assert not controller.config.data['recent']
        events[:] = [SimpleNamespace(type=0, code=0, value=0)]
        events.extend(SimpleNamespace(type=1, code=274, value=value) for value in (1, 2, 1, 0))
        guard._read(device.path)
        assert len(controller.config.data['recent']) == 1
    finally:
        trackball.close()
        controller.close()


def test_kernel_monotonic_event_times_survive_batched_reads(pointer_device, tmp_path, monkeypatch):
    from udeck.controller import ShellController
    from udeck.core import ConfigStore
    from udeck.mock import MockBackend
    from udeck.trackball import TrackballInput

    monkeypatch.setattr('udeck.pointer.fcntl.ioctl', lambda *args: 0)
    guard, device, events, _ = pointer_device
    controller = ShellController(MockBackend(), config=ConfigStore(tmp_path / 'config.json'), mock=True)
    trackball = TrackballInput(guard, controller)
    controller.foregroundChanged.emit(True)
    guard.start()
    try:
        now = time.monotonic()
        events[:] = [SimpleNamespace(type=1, code=274, value=pressed, timestamp=lambda stamp=stamp: stamp)
                     for pressed, stamp in ((1, now - 4), (0, now - 0.1))]
        guard._read(device.path)
        assert controller.modal['kind'] == 'menu'
        assert not controller.config.data['recent']
    finally:
        trackball.close()
        controller.close()


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


def sysfs_capabilities(guard, path, capabilities):
    from pathlib import Path

    folder = guard.sysfs_root / Path(path).name / 'device/capabilities'
    folder.mkdir(parents=True, exist_ok=True)
    for name in ('key', 'rel', 'abs'):
        value = sum(1 << code for code in capabilities.get(name, ()))
        words = []
        while value:
            words.insert(0, format(value & ((1 << 64) - 1), 'x'))
            value >>= 64
        (folder / name).write_text(' '.join(words or ['0']) + '\n')


def test_polling_does_not_open_or_close_non_pointer_interfaces(pointer_device, monkeypatch):
    guard, device, _, _ = pointer_device
    sysfs_capabilities(guard, device.path, {'key': [28, 103, 288], 'abs': [0, 1]})
    opened = []
    monkeypatch.setattr(sys.modules['evdev'], 'InputDevice', lambda path: opened.append(path) or device)
    guard.start()
    guard._scan()
    guard._scan()
    assert opened == []


@pytest.mark.parametrize('axes', ['rel', 'abs'])
def test_sysfs_pointer_candidates_still_use_evdev_ownership_checks(pointer_device, axes):
    guard, device, _, ownership = pointer_device
    sysfs_capabilities(guard, device.path, {'key': [272, 273, 274], axes: [0, 1]})
    guard.start()
    assert ownership == ['grab']


def test_hotplug_rechecks_capabilities_at_a_reused_event_path(pointer_device, monkeypatch):
    guard, device, _, ownership = pointer_device
    sysfs_capabilities(guard, device.path, {'key': [28, 103]})
    guard.start()
    assert ownership == []
    monkeypatch.setattr(sys.modules['evdev'], 'list_devices', lambda: [])
    guard._scan()
    monkeypatch.setattr(sys.modules['evdev'], 'list_devices', lambda: [device.path])
    sysfs_capabilities(guard, device.path, {'key': [272], 'rel': [0, 1]})
    guard._scan()
    assert ownership == ['grab']


def test_unreadable_sysfs_keeps_evdev_fallback(pointer_device):
    guard, device, _, ownership = pointer_device
    sysfs_capabilities(guard, device.path, {'key': [272], 'rel': [0, 1]})
    (guard.sysfs_root / 'event8/device/capabilities/key').write_text('invalid')
    guard.start()
    assert ownership == ['grab']
