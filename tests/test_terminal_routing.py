from types import SimpleNamespace

from PySide6.QtCore import QCoreApplication, QObject, Signal

from udeck.terminal.input import TerminalInput
from udeck.terminal_routing import APP_ID, TerminalInputBroker, service_name


class Windows(QObject):
    changed = Signal(list)
    failed = Signal(str)


class Pointer(QObject):
    shoulder = Signal(str)


def test_wayland_service_identity_does_not_depend_on_optional_xwayland_display(monkeypatch):
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
    monkeypatch.setenv("DISPLAY", ":0")
    expected = service_name()
    monkeypatch.delenv("DISPLAY")
    assert service_name() == expected
    monkeypatch.setenv("DISPLAY", ":1")
    assert service_name() == expected
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-1")
    assert service_name() != expected


def test_broker_uses_compositor_focus_and_invalidates_queued_generations():
    application = QCoreApplication.instance() or QCoreApplication([])
    windows, pointer = Windows(), Pointer()
    messages = []
    broker = TerminalInputBroker(windows, pointer, lambda *args: messages.append(args))
    pointer.shoulder.emit("next-page")
    assert not messages
    windows.changed.emit([{"id": "10", "appId": APP_ID, "active": False}])
    assert not messages
    windows.changed.emit([{"id": "10", "appId": APP_ID, "active": True}])
    assert messages[-1] == ("Route", [1, True])
    pointer.shoulder.emit("next-page")
    assert messages[-1] == ("Shoulder", [1, "next-tab"])
    windows.changed.emit([{"id": "11", "appId": "other.app", "active": True}])
    assert messages[-1] == ("Route", [2, False])
    count = len(messages)
    pointer.shoulder.emit("previous-page")
    assert len(messages) == count
    assert application
    assert not broker.enabled


def test_terminal_rejects_stale_events_and_rechecks_actual_qt_focus():
    application = QCoreApplication.instance() or QCoreApplication([])
    actions = []
    active = True
    entry = {"window": SimpleNamespace(isActive=lambda: active),
             "controller": SimpleNamespace(dispatch=actions.append)}
    coordinator = QObject()
    coordinator.windows = [entry]
    inputs = TerminalInput(coordinator, {})
    inputs.foreground = True
    inputs.route(7, True)
    inputs.shoulder(6, "next-tab")
    assert not actions
    inputs.shoulder(7, "next-tab")
    assert actions == ["next-tab"]
    active = False
    inputs.shoulder(7, "next-tab")
    assert len(actions) == 1
    inputs.route(8, False)
    inputs.route(7, True)
    assert not inputs.routed
    inputs.close()
    assert application
