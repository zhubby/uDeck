import os
import sys
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QObject, Qt
from PySide6.QtGui import QKeyEvent

from udeck import key_test_device
from udeck.controller import ShellController
from udeck.core import ConfigStore
from udeck.key_test import KeyTestFilter
from udeck.key_test_device import KeyTestReader
from udeck.mock import MockBackend


@pytest.fixture
def keyboard(monkeypatch):
    application = QCoreApplication.instance() or QCoreApplication([])
    descriptor, writer = os.pipe()
    events, closed = [], []
    device = SimpleNamespace(
        path="/dev/input/event4", name="ClockworkPI uConsole Keyboard", fd=descriptor,
        info=SimpleNamespace(vendor=0x1eaf, product=0x0024),
        capabilities=lambda: {1: [1, 29, 36, 88, 97, 115, 224]},
        read=lambda: list(events), close=lambda: closed.append(True),
    )
    paths = [device.path]
    monkeypatch.setitem(sys.modules, "evdev", SimpleNamespace(
        InputDevice=lambda path: device, list_devices=lambda: list(paths)))
    monkeypatch.setattr(key_test_device, "sys", SimpleNamespace(platform="linux"))
    reader = KeyTestReader()
    reader._test_application = application
    yield application, reader, device, events, paths, closed
    reader.close()
    reader.deleteLater()
    application.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    os.close(descriptor)
    os.close(writer)


def test_native_reader_is_scoped_to_diagnostic_and_never_grabs_devices(keyboard):
    _, reader, device, events, _, closed = keyboard
    edges = []
    reader.key.connect(lambda key, pressed, source: edges.append((key, pressed, source)))
    assert not reader.devices
    reader.set_enabled(True)
    # The fake device deliberately has no grab() or ungrab() methods.
    events[:] = [SimpleNamespace(type=1, code=code, value=value)
                 for code in (29, 97, 115, 224, 88) for value in (1, 2, 1, 0)]
    reader._read(device.path)
    assert [key for key, pressed, _ in edges if pressed] == ["ctrl-left", "ctrl-right", "volume-up", "brightness-down", "f12"]
    assert len(edges) == 10
    reader.set_enabled(False)
    assert closed and not reader.devices and not reader.timer.isActive()
    reader._read(device.path)
    assert len(edges) == 10
    reader.set_enabled(True)
    assert device.path in reader.devices and reader.enabled and reader.timer.isActive()


def test_sync_loss_and_hot_unplug_release_held_states(keyboard):
    _, reader, device, events, paths, _ = keyboard
    resets, edges = [], []
    reader.reset.connect(resets.append)
    reader.key.connect(lambda key, pressed, source: edges.append((key, pressed)))
    reader.set_enabled(True)
    events[:] = [SimpleNamespace(type=1, code=29, value=1), SimpleNamespace(type=0, code=3, value=0),
                 SimpleNamespace(type=1, code=97, value=1), SimpleNamespace(type=0, code=0, value=0)]
    reader._read(device.path)
    assert resets == [device.path] and edges == [("ctrl-left", True)]
    paths.clear()
    reader._scan()
    assert resets == [device.path, device.path] and not reader.devices


def test_closing_reader_cannot_reopen_devices_through_a_reset_notification(keyboard):
    _, reader, _, _, _, _ = keyboard
    reader.set_enabled(True)
    reader.reset.connect(lambda source: reader.set_enabled(True))
    reader.close()
    assert not reader.devices and not reader.enabled and not reader.timer.isActive()


@pytest.mark.parametrize("name,vendor", [("Unrelated keyboard", 0x1234), ("ClockworkPI uConsole Mouse", 0x1eaf),
                                         ("ClockworkPI uConsole", 0x1eaf)])
def test_reader_does_not_open_other_keyboards_or_existing_input_owners(keyboard, name, vendor):
    _, reader, device, _, _, closed = keyboard
    device.name, device.info.vendor = name, vendor
    reader.set_enabled(True)
    assert not reader.devices and closed


@pytest.mark.parametrize("qt_first", [True, False])
def test_native_coverage_deduplicates_complete_batches_and_unplug_restores_qt(keyboard, tmp_path, qt_first):
    application, reader, device, events, paths, _ = keyboard
    controller = ShellController(MockBackend(), config=ConfigStore(tmp_path / "settings.json"), mock=True)
    window = QObject()
    event_filter = KeyTestFilter(controller, window)
    reader.key.connect(controller.testHardwareKey)
    reader.reset.connect(controller.resetHardwareKeys)
    reader.status.connect(controller.input_status)
    controller.activateSetting("key-test")
    try:
        reader.set_enabled(True)
        events[:] = [SimpleNamespace(type=1, code=36, value=value) for value in (1, 0)]

        def qt_tap():
            for kind in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
                application.sendEvent(window, QKeyEvent(kind, Qt.Key_J, Qt.NoModifier))

        if qt_first:
            qt_tap()
        reader._read(device.path)
        if not qt_first:
            qt_tap()
        assert controller.modal["pressCount"] == 1 and not controller.modal["pressed"]
        paths.clear()
        reader._scan()
        qt_tap()
        assert controller.modal["pressCount"] == 2 and not controller.modal["pressed"]
    finally:
        reader.close()
        reader.key.disconnect(controller.testHardwareKey)
        reader.reset.disconnect(controller.resetHardwareKeys)
        reader.status.disconnect(controller.input_status)
        window.removeEventFilter(event_filter)
        controller.close()
        window.deleteLater()
        controller.deleteLater()
        application.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def test_unreadable_capabilities_leave_qt_fallback_enabled(keyboard):
    _, reader, device, _, _, closed = keyboard
    status, warnings = {}, []
    reader.status.connect(status.update)
    reader.warning.connect(warnings.append)

    def denied():
        raise PermissionError("permission denied")

    device.capabilities = denied
    reader.set_enabled(True)
    assert status == {"keyTestNativeKeys": []}
    assert not reader.devices and closed and warnings[-1]
