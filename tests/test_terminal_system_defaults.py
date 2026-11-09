from pathlib import Path

import pytest

from udeck.terminal.defaults import DESKTOP_ID, SystemDefaults


class Alternatives:
    def __init__(self):
        self.state = {"status": "manual", "value": "/usr/bin/original-terminal", "registered": False}

    def query(self):
        return dict(self.state)

    def install(self):
        self.state["registered"] = True

    def select(self):
        self.state.update(status="manual", value="/usr/bin/udeck-terminal")

    def restore(self, state, *, strict=True):
        self.state = dict(state)

    def remove(self):
        self.state["registered"] = False


@pytest.fixture
def system(tmp_path):
    original = tmp_path / "usr/bin/original-terminal"
    original.parent.mkdir(parents=True)
    original.write_text("original terminal")
    return SystemDefaults(tmp_path, Alternatives())


def test_package_defaults_apply_without_acceptance_and_restore_after_reconfiguration(system):
    directory = system.root / "etc/xdg"
    directory.mkdir(parents=True)
    config = directory / "other-desktop-xdg-terminals.list"
    config.write_text("# preserve\noriginal.desktop\n")
    original = system.alternatives.query()
    system.apply()
    system.apply()
    assert system.alternatives.query()["value"] == "/usr/bin/udeck-terminal"
    assert config.read_text() == DESKTOP_ID + "\n# preserve\noriginal.desktop\n"
    system.restore()
    system.restore()
    assert system.alternatives.query() == original
    assert config.read_text() == "# preserve\noriginal.desktop\n"
    assert not (directory / "xdg-terminals.list").exists()
    assert not (system.root / "home").exists()


def test_uninstall_keeps_subsequent_administrator_preferences(system):
    system.apply()
    config = system.root / "etc/xdg/xdg-terminals.list"
    config.write_text("my-new.desktop\n" + DESKTOP_ID + "\n")
    system.alternatives.state["value"] = "/usr/bin/my-new-terminal"
    system.restore()
    assert config.read_text() == "my-new.desktop\n"
    assert system.alternatives.query()["value"] == "/usr/bin/my-new-terminal"
    assert not system.alternatives.query()["registered"]


def test_reconfiguration_preserves_administrator_file_edits_on_removal(system):
    system.apply()
    config = system.root / "etc/xdg/xdg-terminals.list"
    config.write_text("my-new.desktop\n" + DESKTOP_ID + "\n")
    system.apply()
    system.restore()
    assert config.read_text() == "my-new.desktop\n"


def test_package_default_failure_rolls_back_and_does_not_leave_recovery_state(system):
    original = system.alternatives.query()
    def fail():
        raise RuntimeError("selection failed")
    system.alternatives.select = fail
    with pytest.raises(RuntimeError, match="selection failed"):
        system.apply()
    assert system.alternatives.query() == original
    assert not system.state.exists()
    assert not (system.root / "etc/xdg/xdg-terminals.list").exists()


def test_system_symlinks_are_rejected_before_mutating_any_defaults(system):
    directory = system.root / "etc/xdg"
    directory.mkdir(parents=True)
    (directory / "xdg-terminals.list").symlink_to(Path("elsewhere"))
    with pytest.raises(ValueError, match="符号链接"):
        system.apply()
    assert not system.state.exists()
    assert not system.alternatives.query()["registered"]
