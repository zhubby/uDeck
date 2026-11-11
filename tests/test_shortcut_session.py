from types import SimpleNamespace

import pytest
from PySide6.QtCore import QCoreApplication

from udeck.shortcut_session import ShortcutSession
from udeck.shortcuts import ShortcutStore


@pytest.mark.parametrize('arguments', [
    [b'labwc', b'-C', b'/desktop'], [b'labwc', b'--config-dir', b'/desktop'],
    [b'labwc', b'--config-dir=/desktop'], [b'labwc', b'-C/desktop'],
])
def test_target_directory_uses_actual_compositor_options(arguments):
    from udeck.shortcut_session import configuration_directory
    assert configuration_directory(arguments, '/fallback') == '/desktop'


def session(tmp_path, monkeypatch):
    application = QCoreApplication.instance() or QCoreApplication([])
    config = tmp_path / 'rc.xml'
    config.write_text('<labwc_config><!-- original --><theme><name>PiXtrix</name></theme>'
                      '<keyboard><default/><keybind key="W-r"><action name="Execute" command="old-runner"/>'
                      '</keybind></keyboard></labwc_config>')
    config.chmod(0o640)
    monkeypatch.setenv('XDG_STATE_HOME', str(tmp_path / 'state'))
    store = ShortcutStore(tmp_path / 'shortcuts.json')
    output = SimpleNamespace(available=True, chord=lambda keys: None)
    manager = ShortcutSession(store, output, config=config, pid=12345)
    monkeypatch.setattr(manager, '_owns_compositor', lambda: True)
    manager.available = True
    monkeypatch.setattr('udeck.shortcut_session.os.kill', lambda *args: None)
    return application, manager, config


def test_takeover_backs_up_original_once_and_commits_only_after_ack(tmp_path, monkeypatch):
    app, manager, config = session(tmp_path, monkeypatch)
    original = config.read_bytes()
    manager.start()
    assert manager.busy
    assert 'old-runner' not in config.read_text()
    backups = list((tmp_path / 'state/udeck/shortcuts').glob('*.xml'))
    assert len(backups) == 1 and backups[0].read_bytes() == original
    assert backups[0].stat().st_mode & 0o777 == 0o600
    assert config.stat().st_mode & 0o777 == 0o640
    assert not manager.acknowledge('stale') and manager.busy
    assert manager.acknowledge(manager.token) and not manager.busy
    proposal = manager.store.propose('console', ['Ctrl+Alt+Q'])
    manager.apply(proposal)
    assert not manager.store.path.exists()
    assert manager.acknowledge(manager.token)
    assert ShortcutStore(manager.store.path).bindings()['console'] == ['C-A-q']
    assert len(list(backups[0].parent.glob('*.xml'))) == 1
    manager.close()
    assert app


def test_timeout_restores_exact_xml_and_persisted_bindings(tmp_path, monkeypatch):
    app, manager, config = session(tmp_path, monkeypatch)
    manager.start()
    manager.acknowledge(manager.token)
    manager.store.save(manager.store.propose('console', []))
    original, stored = config.read_bytes(), manager.store.path.read_bytes()
    results = []
    manager.finished.connect(results.append)
    manager.apply(manager.store.propose('console', ['Ctrl+Alt+Q']))
    token = manager.token
    for _ in range(8):
        manager._probe()
    assert not manager.busy and not results[-1]['success']
    assert config.read_bytes() == original and manager.store.path.read_bytes() == stored
    assert not manager.acknowledge(token)
    manager.close()
    assert app


def test_pointer_change_queues_behind_edit_and_keeps_custom_bindings(tmp_path, monkeypatch):
    app, manager, config = session(tmp_path, monkeypatch)
    manager.start()
    manager.acknowledge(manager.token)
    manager.apply(manager.store.propose('console', ['Ctrl+Alt+Q']))
    edit_token = manager.token
    manager.request_pointer(True)
    assert manager.token == edit_token
    manager.acknowledge(edit_token)
    assert manager.busy and manager.token != edit_token
    assert 'key="Up"' in config.read_text() and 'key="C-A-q"' in config.read_text()
    manager.acknowledge(manager.token)
    assert manager.pointer
    manager.restore_pointer()
    assert 'key="Up"' not in config.read_text() and 'key="C-A-q"' in config.read_text()
    manager.close()
    assert app


def test_foreign_compositor_never_receives_a_reload_or_config_write(tmp_path, monkeypatch):
    app, manager, config = session(tmp_path, monkeypatch)
    monkeypatch.setattr(manager, '_owns_compositor', lambda: False)
    original = config.read_bytes()
    manager.start()
    assert config.read_bytes() == original and not manager.available and not manager.busy
    assert not (tmp_path / 'state').exists()
    manager.close()
    assert app


def test_external_xml_edit_is_not_confirmed_or_overwritten_by_rollback(tmp_path, monkeypatch):
    app, manager, config = session(tmp_path, monkeypatch)
    manager.start()
    manager.acknowledge(manager.token)
    manager.apply(manager.store.propose('console', ['Ctrl+Alt+Q']))
    changed = config.read_text().replace('PiXtrix', 'ExternalTheme')
    config.write_text(changed)
    assert not manager.acknowledge(manager.token)
    assert config.read_text() == changed
    assert not manager.store.path.exists()
    assert not manager.busy and manager.error
    manager.close()
    assert app


def test_failed_startup_does_not_retry_on_every_session_update(tmp_path, monkeypatch):
    app, manager, config = session(tmp_path, monkeypatch)
    original = config.read_bytes()
    manager.start()
    for _ in range(8):
        manager._probe()
    manager.start()
    assert not manager.busy and config.read_bytes() == original
    manager.start(retry=True)
    assert manager.busy
    manager.close()
    assert app


def test_reload_signal_failure_rolls_back_without_persisting(tmp_path, monkeypatch):
    app, manager, config = session(tmp_path, monkeypatch)
    original = config.read_bytes()

    def fail(*args):
        raise ProcessLookupError('compositor went away')

    monkeypatch.setattr('udeck.shortcut_session.os.kill', fail)
    manager.apply(manager.store.propose('console', []))
    assert config.read_bytes() == original and not manager.store.path.exists()
    assert not manager.busy and manager.error
    manager.close()
    assert app


def test_json_save_failure_rolls_back_compositor_xml(tmp_path, monkeypatch):
    app, manager, config = session(tmp_path, monkeypatch)
    original = config.read_bytes()
    manager.apply(manager.store.propose('console', []))

    def fail(*args):
        raise OSError('storage full')

    monkeypatch.setattr(manager.store, 'save', fail)
    assert not manager.acknowledge(manager.token)
    assert config.read_bytes() == original and not manager.store.path.exists()
    assert not manager.busy and manager.error
    manager.close()
    assert app
