"""
[INPUT]: 依赖 Fcitx 5 会话 D-Bus 和 Qt 信号。
[OUTPUT]: 提供当前输入法、待切换项与输入法组循环切换。
[POS]: 结合 Fcitx 5 输入上下文和输入法组回读选择。
[PROTOCOL]: Update this header on change, then check AGENTS.md
"""

import asyncio
import sys
from dataclasses import dataclass
from threading import Thread

from PySide6.QtCore import QObject, Signal, Slot

SERVICE = "org.fcitx.Fcitx5"
INTERFACE = "org.fcitx.Fcitx.Controller1"
CURRENT_INTERVAL = 0.4
GROUP_INTERVAL = 3
RETRY_INTERVAL = 2
CALL_TIMEOUT = 1
ACTIVE_ENGINE = 2


@dataclass
class InputMethodGroup:
    name: str
    layout: str
    default_id: str
    members: list[list[str]]
    choices: list[dict[str, str]]


class InputMethodController(QObject):
    stateChanged = Signal()
    selectionFailed = Signal()
    _stateReceived = Signal(object, str, bool, str)

    def __init__(self, parent=None, *, mock=False):
        super().__init__(parent)
        self.available = mock
        self.current_id = ""
        self.current_label = ""
        self.pending_id = ""
        self.choices = []
        self._mock = mock
        self._closed = False
        self._loop = None
        self._thread = None
        self._requested = ""
        self._cycle_steps = 0
        self._reload_group = False
        self._stateReceived.connect(self._publish)
        if mock:
            self._publish(
                [_choice("keyboard-us", "English (US)", enabled=True),
                 _choice("pinyin", "Pinyin", enabled=True)],
                "keyboard-us",
                True,
            )
        elif sys.platform == "linux":
            self._thread = Thread(target=self._run, name="udeck-input-method", daemon=True)
            self._thread.start()

    def refresh(self):
        self._submit(self._schedule_refresh)

    def select_input_method(self, method_id: str) -> bool:
        if self._closed or not self.available or not any(item["id"] == method_id for item in self.choices):
            return False
        if self._mock:
            self._publish(self.choices, method_id, True)
            return True
        return self._submit(self._schedule_refresh, method_id)

    def cycle_input_method(self) -> bool:
        enabled = _enabled_ids(self.choices)
        if self._closed or not self.available or len(enabled) < 2:
            return False
        if self._mock:
            return self.select_input_method(_next_method(enabled, self.current_id, 1))
        return self._submit(self._queue_cycle)

    def close(self):
        if self._closed:
            return
        loop = self._loop
        if loop is not None:
            self._submit(self._task.cancel)
        self._closed = True
        if self._thread is not None:
            self._thread.join(timeout=0.2)

    def _submit(self, callback, *args):
        loop = self._loop
        if loop is None or self._closed:
            return False
        try:
            loop.call_soon_threadsafe(callback, *args)
        except RuntimeError:
            return False
        return True

    @Slot(object, str, bool, str)
    def _publish(self, choices, current_id, available, pending_id=""):
        if self._closed:
            return
        current = next((item for item in choices if item["id"] == current_id), None)
        label = current["label"] if current else current_id
        if (self.choices, self.current_id, self.current_label, self.available, self.pending_id) == (
            choices, current_id, label, available, pending_id
        ):
            return
        self.choices = choices
        self.current_id = current_id
        self.current_label = label
        self.available = available
        self.pending_id = pending_id
        self.stateChanged.emit()

    def _run(self):
        asyncio.run(self._watch())

    def _schedule_refresh(self, method_id=""):
        if method_id:
            self._requested = method_id
            self._cycle_steps = 0
        self._reload_group = True
        self._wake.set()

    def _queue_cycle(self):
        self._cycle_steps += 1
        self._wake.set()

    async def _watch(self):
        from dbus_next.aio import MessageBus
        from dbus_next.errors import AuthError, DBusError, InvalidAddressError

        self._wake = asyncio.Event()
        self._task = asyncio.current_task()
        self._loop = asyncio.get_running_loop()
        try:
            while not self._closed:
                try:
                    bus = MessageBus()
                    try:
                        await asyncio.wait_for(bus.connect(), CALL_TIMEOUT)
                        await self._read_session(bus)
                    finally:
                        bus.disconnect()
                        if bus.unique_name is not None:
                            await bus.wait_for_disconnect()
                except (AuthError, DBusError, InvalidAddressError, OSError, EOFError):
                    pass
                if not self._closed:
                    self._stateReceived.emit([], "", False, "")
                await asyncio.sleep(RETRY_INTERVAL)
        except asyncio.CancelledError:
            pass
        finally:
            self._loop = None

    async def _read_session(self, bus):
        owner = ""
        installed = []
        refresh_at = 0
        pending = ""
        while not self._closed and bus.connected:
            self._wake.clear()
            pending = self._requested or pending
            self._requested = ""
            steps, self._cycle_steps = self._cycle_steps, 0
            failed = False
            try:
                current = await _call(bus, SERVICE, "CurrentInputMethod")
                if not current:
                    raise LookupError
                reload_installed = self._reload_group or current.sender != owner
                if reload_installed or steps or self._loop.time() >= refresh_at:
                    self._reload_group = False
                    owner = current.sender
                    if reload_installed:
                        installed = await _read_installed(bus, owner)
                    group = await _read_group(bus, owner, installed)
                    refresh_at = self._loop.time() + GROUP_INTERVAL
                current_id = await _current_selection(bus, owner, group, current.body[0])
                if steps:
                    enabled = _enabled_ids(group.choices)
                    if len(enabled) > 1:
                        pending = _next_method(enabled, pending or current_id, steps)
                    else:
                        failed = True
                if pending and current_id:
                    if pending != current_id:
                        switched = await _select(bus, owner, group, pending)
                        group = await _read_group(bus, owner, installed)
                        current = await _call(bus, owner, "CurrentInputMethod")
                        if not current:
                            raise LookupError
                        current_id = await _current_selection(bus, owner, group, current.body[0])
                        failed = failed or not switched or current_id != pending
                        refresh_at = self._loop.time() + GROUP_INTERVAL
                    pending = ""
                self._stateReceived.emit(group.choices, current_id, True, pending)
                delay = CURRENT_INTERVAL
            except LookupError:
                failed = bool(pending or steps)
                pending = ""
                owner = ""
                self._stateReceived.emit([], "", False, "")
                delay = RETRY_INTERVAL
            if failed:
                self.selectionFailed.emit()
            try:
                await asyncio.wait_for(self._wake.wait(), delay)
            except TimeoutError:
                pass


async def _call(bus, destination, method, signature="", body=None):
    from dbus_next import Message, MessageFlag, MessageType

    try:
        reply = await asyncio.wait_for(bus.call(Message(
            destination=destination, path="/controller", interface=INTERFACE, member=method,
            signature=signature, body=body or [], flags=MessageFlag.NO_AUTOSTART,
        )), CALL_TIMEOUT)
    except TimeoutError:
        return None
    return reply if reply and reply.message_type == MessageType.METHOD_RETURN else None


def _choice(method_id, name, *, enabled=False):
    return {"id": method_id, "label": name or method_id, "enabled": enabled}


def _enabled_ids(choices):
    return [choice["id"] for choice in choices if choice["enabled"]]


def _next_method(enabled, current_id, steps):
    position = enabled.index(current_id) if current_id in enabled else 0
    return enabled[(position + steps) % len(enabled)]


async def _read_group(bus, owner, installed):
    reply = await _call(bus, owner, "FullInputMethodGroupInfo", "s", [""])
    if not reply or not reply.body[0] or not reply.body[4]:
        raise LookupError
    group, default_id, layout, _, entries = reply.body
    members = [[entry[0], entry[8]] for entry in entries]
    enabled_ids = {member[0] for member in members}
    choices = [_choice(entry[0], entry[1], enabled=True) for entry in entries]
    choices.extend(item for item in installed if item["id"] not in enabled_ids)
    return InputMethodGroup(group, layout, default_id, members, choices)


async def _current_selection(bus, owner, group, method_id):
    if method_id != f"keyboard-{group.layout}" or group.default_id in ("", method_id):
        return method_id
    # Wayland 禁用文本输入时，Fcitx 返回键盘布局，但保留引擎激活位。
    state = await _call(bus, owner, "State")
    if state and state.body[0] == ACTIVE_ENGINE:
        return group.default_id
    return method_id


async def _read_installed(bus, owner):
    available = await _call(bus, owner, "AvailableInputMethods")
    if not available:
        return []
    choices = [_choice(entry[0], entry[1]) for entry in available.body[0]
               if not entry[0].startswith("keyboard-")]
    return sorted(choices, key=lambda item: (item["label"].casefold(), item["id"]))


async def _select(bus, owner, group, method_id):
    if not any(item["id"] == method_id for item in group.choices):
        return False
    if method_id == group.members[0][0]:
        # SetCurrentIM 会将临时回退的键盘布局视为已选项。
        return bool(await _call(bus, owner, "Deactivate"))
    if not any(member[0] == method_id for member in group.members):
        updated = await _call(bus, owner, "SetInputMethodGroupInfo", "ssa(ss)",
                              [group.name, group.layout, [*group.members, [method_id, ""]]])
        if not updated:
            return False
    return bool(await _call(bus, owner, "SetCurrentIM", "s", [method_id]))
