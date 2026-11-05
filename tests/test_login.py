import importlib.util
from pathlib import Path

import pytest

specification = importlib.util.spec_from_file_location("configure_login", Path(__file__).parents[1] / "tools/configure-login.py")
login = importlib.util.module_from_spec(specification)
specification.loader.exec_module(login)


def test_login_settings_replace_existing_values_without_losing_other_configuration():
    original = "# existing settings\n[Seat:*]\ngreeter-session=pi-greeter-labwc\nuser-session=rpd-labwc\nautologin-user=alice\nautologin-session=rpd-labwc\n\n[XDMCPServer]\nenabled=false\n"
    configured = login.render_config(original, "alice")
    assert "# existing settings\n" in configured
    assert "greeter-session=pi-greeter-labwc\n" in configured
    assert "user-session=udeck\n" in configured
    assert "autologin-user=alice\n" in configured
    assert "autologin-session=udeck\n" in configured
    assert "autologin-user-timeout=0\n" in configured
    assert configured.endswith("[XDMCPServer]\nenabled=false\n")
    assert login.render_config(configured, "alice") == configured


def test_login_config_adds_missing_seat_without_concatenating_lines():
    configured = login.render_config("[LightDM]\nlogind-check-graphical=true", "alice")
    assert "logind-check-graphical=true\n[Seat:*]\n" in configured
    assert "autologin-session=udeck\n" in configured


def test_specific_seat_override_is_not_silently_ignored():
    with pytest.raises(ValueError, match="Seat:seat0"):
        login.render_config("[Seat:*]\nuser-session=rpd-labwc\n[Seat:seat0]\nautologin-session=rpd-labwc\n", "alice")


def test_login_configuration_backs_up_original_and_is_idempotent(tmp_path):
    config = tmp_path / "lightdm.conf"
    original = b"# preserve this\n[Seat:*]\nuser-session=rpd-labwc\n"
    config.write_bytes(original)
    config.chmod(0o640)
    backups = tmp_path / "backups"
    result = login.configure_login(config, backups, "alice")
    assert result["changed"] is True
    assert Path(result["backup"]).read_bytes() == original
    assert config.stat().st_mode & 0o777 == 0o640
    assert backups.stat().st_mode & 0o077 == 0
    assert "autologin-session=udeck\n" in config.read_text()
    assert login.configure_login(config, backups, "alice")["changed"] is False
    assert len(list(backups.iterdir())) == 1


def test_login_configuration_does_not_follow_symlinks(tmp_path):
    original = tmp_path / "original.conf"
    original.write_text("[Seat:*]\n")
    config = tmp_path / "lightdm.conf"
    config.symlink_to(original)
    with pytest.raises(ValueError, match="symbolic"):
        login.configure_login(config, tmp_path / "backups", "alice")
    assert original.read_text() == "[Seat:*]\n"
