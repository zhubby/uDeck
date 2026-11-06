import json
from pathlib import Path

import pytest

from udeck.terminal.defaults import DefaultManager, validate_acceptance


class Alternatives:
    def __init__(self):
        self.state = {"status": "auto", "value": "/usr/bin/old-terminal", "registered": False}

    def query(self):
        return dict(self.state)

    def install(self):
        self.state["registered"] = True

    def select(self):
        self.state.update(status="manual", value="/usr/bin/udeck-terminal")

    def restore(self, state):
        self.state = dict(state)


@pytest.fixture
def defaults(tmp_path):
    manager = DefaultManager(tmp_path, Path("/home/test"), Alternatives())
    config = tmp_path / "home/test/.config"
    config.mkdir(parents=True)
    return manager, config


def test_default_transaction_preserves_preferences_and_restores_auto_mode(defaults):
    manager, config = defaults
    path = config / "labwc-xdg-terminals.list"
    path.write_text("old.desktop\n# keep this\n")
    backup = manager.apply()
    assert path.read_text().startswith("io.github.zhubby.uDeck.Terminal.desktop\nold.desktop")
    assert manager.alternatives.query()["value"] == "/usr/bin/udeck-terminal"
    manager.restore(backup)
    assert path.read_text() == "old.desktop\n# keep this\n"
    assert manager.alternatives.query() == {"status": "auto", "value": "/usr/bin/old-terminal", "registered": False}
    assert not (config / "xdg-terminals.list").exists()


def test_restore_does_not_overwrite_subsequent_user_changes(defaults):
    manager, config = defaults
    backup = manager.apply()
    (config / "xdg-terminals.list").write_text("my-new-preference.desktop\n")
    with pytest.raises(ValueError, match="已被修改"):
        manager.restore(backup)
    assert manager.alternatives.query()["value"] == "/usr/bin/udeck-terminal"


def test_failed_default_change_rolls_back_files_and_alternative(defaults):
    manager, config = defaults
    original = manager.alternatives.query()
    def fail():
        raise RuntimeError("simulated alternative failure")
    manager.alternatives.select = fail
    with pytest.raises(RuntimeError):
        manager.apply()
    assert manager.alternatives.query() == original
    assert not (config / "xdg-terminals.list").exists()


def test_explicit_old_terminal_bindings_are_migrated_without_shell_interpolation(defaults):
    manager, config = defaults
    (config / "labwc").mkdir()
    path = config / "labwc/rc.xml"
    original = '<labwc_config><keyboard><keybind key="C-A-t"><action name="Execute"><command>lxterminal</command></action></keybind></keyboard></labwc_config>'
    path.write_text(original)
    backup = manager.apply()
    assert "<command>x-terminal-emulator</command>" in path.read_text()
    manager.restore(backup)
    assert path.read_text() == original


def test_unsafe_or_unknown_flags_block_before_any_default_is_changed(defaults):
    manager, config = defaults
    (config / "labwc").mkdir()
    (config / "labwc/rc.xml").write_text('<command>foot --server</command>')
    with pytest.raises(ValueError, match="手动迁移"):
        manager.apply()
    assert manager.alternatives.query()["status"] == "auto"
    assert not (config / "xdg-terminals.list").exists()


def test_symbolic_link_configuration_is_not_followed(defaults):
    manager, config = defaults
    (config / "xdg-terminals.list").symlink_to(config / "other")
    with pytest.raises(ValueError, match="符号链接"):
        manager.apply()


def test_labwc_command_attribute_is_migrated_and_restored(defaults):
    manager, config = defaults
    (config / "labwc").mkdir()
    path = config / "labwc/rc.xml"
    original = '<action name="Execute" command="lxterminal"/>'
    path.write_text(original)
    backup = manager.apply()
    assert path.read_text() == '<action name="Execute" command="x-terminal-emulator"/>'
    manager.restore(backup)
    assert path.read_text() == original


def test_acceptance_requires_all_physical_and_performance_evidence(tmp_path):
    report = tmp_path / "acceptance.json"
    report.write_text(json.dumps({"buildId": "abc", "checks": {}}))
    with pytest.raises(ValueError, match="验收"):
        validate_acceptance(report, "abc")
