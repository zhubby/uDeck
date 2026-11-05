import sys
from types import SimpleNamespace

from udeck import cli


def test_doctor_closes_evdev_handles_without_context_manager(tmp_path, monkeypatch):
    closed = []
    device = SimpleNamespace(
        info=SimpleNamespace(vendor=0x1EAF, product=0x0024),
        name="uConsole Gamepad",
        close=lambda: closed.append(True),
    )
    monkeypatch.setitem(sys.modules, "evdev", SimpleNamespace(
        InputDevice=lambda path: device, list_devices=lambda: ["/dev/input/test"],
    ))
    monkeypatch.setattr(cli.importlib.util, "find_spec", lambda name: object() if name == "evdev" else None)
    monkeypatch.setattr(cli.sys, "platform", "linux")
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    report = cli.doctor()
    assert report["inputDevices"][0]["name"] == "uConsole Gamepad"
    assert closed == [True]
