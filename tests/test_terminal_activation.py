from PySide6.QtCore import QObject, Signal

from udeck.terminal.activation import RecentWindowActivation

APP_ID = "io.github.zhubby.uDeck.Terminal"


class Windows(QObject):
    changed = Signal(object)
    failed = Signal(object)

    def __init__(self):
        super().__init__()
        self.available = True
        self.requests = []

    def entries(self):
        return []

    def request(self, identifier, operation):
        self.requests.append((identifier, operation))


def terminal(identifier, active=False, **fields):
    return {"id": identifier, "appId": APP_ID, "active": active, "name": "same title", **fields}


def test_plain_launch_restores_recent_window_after_home_despite_duplicate_titles():
    windows = Windows()
    activation = RecentWindowActivation(windows, APP_ID)
    windows.changed.emit([terminal("A", True), terminal("B")])
    windows.changed.emit([terminal("A"), terminal("B", True)])
    windows.changed.emit([terminal("A"), terminal("B"), terminal("shell", True, appId="desktop")])
    activation.activate()
    assert windows.requests == [("B", "activate")]
    windows.changed.emit([terminal("A", True, name="new title"), terminal("B")])
    windows.changed.emit([terminal("A"), terminal("B")])
    activation.activate()
    assert windows.requests[-1] == ("A", "activate")


def test_closed_recent_window_falls_back_to_previously_focused_survivor():
    windows = Windows()
    activation = RecentWindowActivation(windows, APP_ID)
    windows.changed.emit([terminal("A", True), terminal("B"), terminal("C")])
    windows.changed.emit([terminal("A"), terminal("B", True), terminal("C")])
    windows.changed.emit([terminal("A"), terminal("C")])
    activation.activate()
    assert windows.requests == [("A", "activate")]
    windows.changed.emit([])
    activation.activate()
    assert windows.requests == [("A", "activate")]


def test_unobserved_windows_do_not_guess_and_single_window_can_be_restored():
    windows = Windows()
    activation = RecentWindowActivation(windows, APP_ID)
    windows.changed.emit([terminal("A"), terminal("B"), terminal("dialog", True, parent=True)])
    activation.activate()
    assert not windows.requests
    windows.changed.emit([terminal("B")])
    activation.activate()
    assert windows.requests == [("B", "activate")]


def test_protocol_loss_clears_focus_history_and_unavailable_backend_is_not_used():
    windows = Windows()
    activation = RecentWindowActivation(windows, APP_ID)
    windows.changed.emit([terminal("A", True)])
    windows.available = False
    activation.activate()
    assert not windows.requests
    windows.failed.emit("Disconnected")
    windows.available = True
    activation.activate()
    assert not windows.requests
