"""
[INPUT]: 依赖隔离的 Fcitx 5 控制器回复与输入法服务。
[OUTPUT]: 验证候选列表、循环切换、延迟应用和服务读回。
[POS]: 输入法后端回归；模拟会话总线，不访问用户配置。
[PROTOCOL]: Update this header on change, then check AGENTS.md
"""

import asyncio
from types import SimpleNamespace

import pytest

from udeck import input_method


def test_fcitx_lists_and_enables_installed_input_methods(monkeypatch):
    calls = []

    async def call(bus, owner, method, signature="", body=None):
        calls.append((owner, method, signature, body))
        if method == "FullInputMethodGroupInfo":
            return SimpleNamespace(body=["Default", "", "us", {}, [
                ["keyboard-us", "English (US)", "", "", "", "en", "keyboard", False, "", {}],
                ["keyboard-fr", "French", "", "", "", "fr", "keyboard", False, "fr", {}],
            ]])
        if method == "AvailableInputMethods":
            return SimpleNamespace(body=[[
                ["keyboard-es", "Spanish", "", "", "", "es", False],
                ["pinyin", "Pinyin", "", "", "拼", "zh_CN", True],
            ]])
        return SimpleNamespace(body=[])

    monkeypatch.setattr(input_method, "_call", call)

    async def verify():
        installed = await input_method._read_installed(None, ":1.4")
        group = await input_method._read_group(None, ":1.4", installed)
        assert group.choices == [
            {"id": "keyboard-us", "label": "English (US)", "enabled": True},
            {"id": "keyboard-fr", "label": "French", "enabled": True},
            {"id": "pinyin", "label": "Pinyin", "enabled": False},
        ]
        assert not await input_method._select(None, ":1.4", group, "keyboard-es")
        assert len(calls) == 2
        assert await input_method._select(None, ":1.4", group, "pinyin")

    asyncio.run(verify())

    assert calls[2:] == [
        (":1.4", "SetInputMethodGroupInfo", "ssa(ss)", [
            "Default", "us", [["keyboard-us", ""], ["keyboard-fr", "fr"], ["pinyin", ""]],
        ]),
        (":1.4", "SetCurrentIM", "s", ["pinyin"]),
    ]


@pytest.mark.parametrize("use_shortcut", [False, True])
def test_selection_waits_for_text_input_and_publishes_readback(monkeypatch, use_shortcut):
    controller = input_method.InputMethodController(mock=True)
    choices = [*controller.choices, input_method._choice("table", "Table"),
               input_method._choice("shuangpin", "Shuangpin", enabled=True)]
    expected = "shuangpin" if use_shortcut else "pinyin"
    states = []
    failures = []
    writes = []
    current = ""

    async def call(bus, owner, method):
        assert method == "CurrentInputMethod"
        return SimpleNamespace(sender=":1.4", body=[current])

    async def read_installed(bus, owner):
        return []

    async def read_group(bus, owner, installed):
        return input_method.InputMethodGroup(
            "Default", "us", "keyboard-us", [[item["id"], ""] for item in choices if item["enabled"]], choices,
        )

    async def select(bus, owner, group, method_id):
        nonlocal current
        assert current == "keyboard-us"
        writes.append(method_id)
        current = method_id
        return True

    def on_state():
        nonlocal current
        states.append((controller.current_id, controller.pending_id))
        if states == [("", "")]:
            if use_shortcut:
                controller._queue_cycle()
                controller._queue_cycle()
            else:
                controller._schedule_refresh("pinyin")
        elif controller.pending_id:
            assert not writes
            current = "keyboard-us"
            controller._schedule_refresh()
        else:
            controller._closed = True
            controller._wake.set()

    monkeypatch.setattr(input_method, "_call", call)
    monkeypatch.setattr(input_method, "_read_installed", read_installed)
    monkeypatch.setattr(input_method, "_read_group", read_group)
    monkeypatch.setattr(input_method, "_select", select)
    controller.stateChanged.connect(on_state)
    controller.selectionFailed.connect(lambda: failures.append(True))

    async def verify():
        controller._loop = asyncio.get_running_loop()
        controller._wake = asyncio.Event()
        await asyncio.wait_for(controller._read_session(SimpleNamespace(connected=True)), 1)

    asyncio.run(verify())
    assert states == [("", ""), ("", expected), (expected, "")]
    assert writes == [expected]
    assert not failures


def test_wayland_keyboard_fallback_preserves_selection_and_can_deactivate(monkeypatch):
    choices = [{"id": "keyboard-us", "label": "English"}, {"id": "pinyin", "label": "Pinyin"}]
    group = input_method.InputMethodGroup(
        "Default", "us", "pinyin", [["keyboard-us", ""], ["pinyin", ""]], choices,
    )
    calls = []
    active = True

    async def call(bus, owner, method):
        nonlocal active
        calls.append(method)
        if method == "Deactivate":
            active = False
            return SimpleNamespace(body=[])
        assert method == "State"
        return SimpleNamespace(body=[2 if active else 1])

    monkeypatch.setattr(input_method, "_call", call)

    async def verify():
        assert await input_method._current_selection(None, ":1.4", group, "keyboard-us") == "pinyin"
        assert await input_method._select(None, ":1.4", group, "keyboard-us")
        assert await input_method._current_selection(None, ":1.4", group, "keyboard-us") == "keyboard-us"
        assert await input_method._current_selection(None, ":1.4", group, "") == ""

    asyncio.run(verify())
    assert calls == ["State", "Deactivate", "State"]
