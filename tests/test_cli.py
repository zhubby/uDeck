import json
import sys
from types import SimpleNamespace

import pytest

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


def test_bind_console_requires_live_shell_and_leaves_offline_config_untouched(tmp_path, monkeypatch, capsys):
    from PySide6 import QtDBus

    directory = tmp_path / 'labwc'
    directory.mkdir()
    config = directory / 'rc.xml'
    config.write_text('<labwc_config/>')
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path))
    monkeypatch.setenv('XDG_STATE_HOME', str(tmp_path / 'state'))

    monkeypatch.setattr(QtDBus, 'QDBusInterface', lambda *args: SimpleNamespace(isValid=lambda: False))
    assert cli.main(['bind-console']) == 1
    captured = capsys.readouterr()
    assert not captured.out and captured.err
    assert config.read_text() == '<labwc_config/>'
    assert not (tmp_path / 'state').exists()


@pytest.mark.parametrize(('state', 'code'), [
    ({'available': True, 'pending': False, 'applied': False, 'error': 'timeout'}, 1),
    ({'available': True, 'pending': True, 'applied': False, 'error': ''}, 0),
    ({'available': True, 'pending': False, 'applied': True, 'error': ''}, 0),
])
def test_bind_console_reports_live_reload_result(monkeypatch, capsys, state, code):
    from PySide6 import QtDBus

    calls = []

    def call(name):
        calls.append(name)
        return SimpleNamespace(type=lambda: QtDBus.QDBusMessage.MessageType.ReplyMessage,
                               arguments=lambda: [json.dumps(state)])

    monkeypatch.setattr(QtDBus, 'QDBusInterface', lambda *args: SimpleNamespace(isValid=lambda: True, call=call))
    assert cli.main(['bind-console']) == code
    assert calls == ['ReloadShortcuts']
    assert json.loads(capsys.readouterr().out) == state
