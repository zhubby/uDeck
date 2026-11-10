import json
import subprocess
import sys
from pathlib import Path
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


def test_bind_console_reports_backup_even_when_reload_fails(tmp_path, monkeypatch, capsys):
    directory = tmp_path / 'labwc'
    directory.mkdir()
    config = directory / 'rc.xml'
    config.write_text('<labwc_config/>')
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path))
    monkeypatch.setenv('XDG_STATE_HOME', str(tmp_path / 'state'))

    def fail(*args, **kwargs):
        raise subprocess.CalledProcessError(1, ['labwc', '--reconfigure'])

    monkeypatch.setattr(cli.subprocess, 'run', fail)
    assert cli.main(['bind-console']) == 1
    captured = capsys.readouterr()
    result = json.loads(captured.out)
    assert result['changed'] and Path(result['backup']).read_text() == '<labwc_config/>'
    assert captured.err
