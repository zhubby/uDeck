"""
[INPUT]: 依赖虚拟输入与隔离的 Wayland 请求记录器。
[OUTPUT]: 验证相对协议、事件时间、绝对边界和按键释放。
[POS]: 合成输入传输契约回归，不连接用户图形会话。
[PROTOCOL]: Update this header on change, then check AGENTS.md
"""

import ctypes

from udeck.virtual_input import VirtualInput


def test_chord_releases_modifiers_and_all_keys_even_if_transport_fails():
    output = VirtualInput()
    output.available = True
    events = []
    output._key = lambda code, pressed: events.append((code, pressed))
    output.chord((42, 68))
    assert events == [(42, True), (68, True), (68, False), (42, False)]
    assert not output.keys


def test_drag_release_is_idempotent_and_motion_clamps_to_output():
    output = VirtualInput()
    events = []
    output.available = True
    output.pointer = 20
    output._request = lambda *arguments: events.append(arguments)
    output._flush = lambda: None
    output.button(272, True)
    output.button(272, True)
    output.release_all()
    output.release_all()
    states = [arguments[-1].value for arguments in events if arguments[1] == 2]
    assert states == [1, 0]
    output.move(-10000, 10000)
    assert output.position == (0, 719)


def test_disconnected_virtual_input_does_not_queue_keys_for_next_connection():
    output = VirtualInput()
    output.chord((28,))
    output.button(272, True)
    output.move(10, 10)
    assert not output.keys and not output.buttons


def test_relative_motion_preserves_signed_fractional_values_and_source_time(monkeypatch):
    output = VirtualInput()
    output.available = True
    output.pointer = 20
    events, flushes = [], []
    output._request = lambda *arguments: events.append(arguments)
    output._flush = lambda: flushes.append(True)
    monkeypatch.setattr('udeck.virtual_input.time.monotonic', lambda: 500.5)
    output.move_relative(-2.5, 3.25, occurred=12.345)
    assert len(events) == 2
    pointer, opcode, stamp, horizontal, vertical = events[0]
    assert (pointer, opcode, stamp.value, horizontal.value, vertical.value) == (20, 0, 12345, -640, 832)
    assert isinstance(horizontal, ctypes.c_int32) and isinstance(vertical, ctypes.c_int32)
    assert events[1] == (20, 4)
    assert flushes == [True]
    assert output.position == (640, 360)


def test_relative_motion_ignores_absolute_position_and_extent():
    output = VirtualInput()
    output.available = True
    output.pointer = 20
    output.position = (0, 719)
    output.extent = (3, 5)
    events = []
    output._request = lambda *arguments: events.append(arguments)
    output._flush = lambda: None
    output.move_relative(-10000, 10000, occurred=20)
    assert [event[1] for event in events] == [0, 4]
    assert (events[0][3].value, events[0][4].value) == (-2560000, 2560000)
    assert output.position == (0, 719)
    assert output.extent == (3, 5)


def test_relative_motion_without_source_time_uses_monotonic_clock(monkeypatch):
    output = VirtualInput()
    output.available = True
    output.pointer = 20
    events = []
    output._request = lambda *arguments: events.append(arguments)
    output._flush = lambda: None
    monkeypatch.setattr('udeck.virtual_input.time.monotonic', lambda: 22.25)
    output.move_relative(1, -1)
    assert events[0][2].value == 22250


def test_disconnected_relative_motion_does_not_replay_after_reconnection():
    output = VirtualInput()
    events = []
    output._request = lambda *arguments: events.append(arguments)
    output._flush = lambda: None
    output.move_relative(10, -10, occurred=20)
    assert events == []
    assert output.position == (640, 360)
    output.available = True
    output.pointer = 20
    output.move_relative(-1, 2, occurred=21)
    assert [event[1] for event in events] == [0, 4]
    assert (events[0][2].value, events[0][3].value, events[0][4].value) == (21000, -256, 512)
