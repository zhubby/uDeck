import xml.etree.ElementTree as ElementTree
from pathlib import Path
from types import SimpleNamespace

from PySide6.QtCore import QCoreApplication

from udeck.session_config import DirectionIsolation, render_config


def test_global_console_binding_survives_direction_mode_and_restore():
    original = Path('packaging/labwc/rc.xml').read_text()
    for pointer in (False, True):
        root = ElementTree.fromstring(render_config(original, pointer, 'abc123'))
        bindings = root.findall('keyboard/keybind')
        console = [entry for entry in bindings if entry.get('key') == 'C-S-Escape']
        assert len(console) == 1
        assert console[0].get('allowWhenLocked') != 'yes'
        assert console[0].find('action').get('command') == 'udeckctl console'
        assert 'udeck-app games' not in ElementTree.tostring(root, encoding='unicode')


def test_pointer_config_consumes_only_unmodified_directions_and_acknowledges_generation():
    original = '<labwc_config><keyboard><keybind key="C-A-Escape"><action name="Execute" command="udeckctl home"/></keybind></keyboard><theme><name>PiXtrix</name></theme></labwc_config>'
    config = ElementTree.fromstring(render_config(original, True, 'abc123'))
    bindings = {entry.get('key'): entry for entry in config.findall('keyboard/keybind')}
    assert set(bindings) == {'C-A-Escape', 'Up', 'Down', 'Left', 'Right', 'F24'}
    assert all(bindings[key].find('action').get('name') == 'If' for key in ('Up', 'Down', 'Left', 'Right'))
    assert bindings['F24'].find('action').get('command') == 'udeckctl input-ack abc123'
    assert config.find('theme/name').text == 'PiXtrix'
    restored = ElementTree.fromstring(render_config(original, False, 'def456'))
    assert not any(entry.get('key') == 'Up' for entry in restored.findall('keyboard/keybind'))


def test_ack_token_cannot_inject_extra_command_arguments():
    import pytest
    with pytest.raises(ValueError):
        render_config('<labwc_config/>', True, 'invalid;command')


def test_invalid_compositor_pid_never_reloads_another_session(monkeypatch):
    application = QCoreApplication.instance() or QCoreApplication([])
    monkeypatch.setenv('UDECK_SESSION', '1')
    monkeypatch.setenv('LABWC_PID', 'not-a-pid')
    isolation = DirectionIsolation(SimpleNamespace(available=True))
    assert not isolation.available
    assert isolation.acknowledge('stale') is False
    assert application


def test_config_timeout_restores_base_and_rejects_late_ack(tmp_path, monkeypatch):
    application = QCoreApplication.instance() or QCoreApplication([])
    directory = tmp_path / 'labwc'
    directory.mkdir()
    (directory / 'base.xml').write_text('<labwc_config/>')
    monkeypatch.setenv('LABWC_PID', '0')
    isolation = DirectionIsolation(SimpleNamespace(available=True, chord=lambda keys: None))
    isolation.directory = directory
    isolation.pid = 123456
    isolation.available = True
    monkeypatch.setattr(isolation, '_owns_compositor', lambda: True)
    signals = []
    monkeypatch.setattr('udeck.session_config.os.kill', lambda *arguments: signals.append(arguments))
    results = []
    isolation.finished.connect(results.append)
    isolation.request(True)
    token = isolation.token
    for _attempt in range(8):
        isolation._probe()
    assert results == [False]
    assert not isolation.applied and isolation.pending is None
    assert not isolation.timer.isActive()
    assert isolation.acknowledge(token) is False
    assert 'key="Up"' not in (directory / 'rc.xml').read_text()
    assert len(signals) == 2
    assert application


def test_reused_or_foreign_pid_does_not_receive_reload_signal(tmp_path, monkeypatch):
    application = QCoreApplication.instance() or QCoreApplication([])
    isolation = DirectionIsolation(SimpleNamespace(available=True))
    isolation.available = True
    monkeypatch.setattr(isolation, '_owns_compositor', lambda: False)
    signals = []
    monkeypatch.setattr('udeck.session_config.os.kill', lambda *arguments: signals.append(arguments))
    isolation.restore()
    isolation.request(True)
    assert not signals and not isolation.available
    application.processEvents()


def test_old_noop_completion_cannot_acknowledge_new_pointer_request(tmp_path, monkeypatch):
    application = QCoreApplication.instance() or QCoreApplication([])
    (tmp_path / 'base.xml').write_text('<labwc_config/>')
    isolation = DirectionIsolation(SimpleNamespace(available=True))
    isolation.available = True
    isolation.directory = tmp_path
    monkeypatch.setattr(isolation, '_owns_compositor', lambda: True)
    monkeypatch.setattr('udeck.session_config.os.kill', lambda *arguments: None)
    results = []
    isolation.finished.connect(results.append)
    isolation.request(False)
    isolation.request(True)
    application.processEvents()
    assert not results
    assert isolation.pending is True and not isolation.applied
    token = isolation.token
    assert isolation.acknowledge(token) is True
    assert isolation.acknowledge(token) is True
    assert results == [True]
    isolation.restore()
    assert isolation.acknowledge(token) is False
