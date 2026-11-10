import xml.etree.ElementTree as ET

import pytest

from udeck.session_shortcuts import bind_console


def test_console_binding_preserves_existing_desktop_and_is_idempotent(tmp_path):
    config = tmp_path / 'rc.xml'
    original = b'''<labwc_config><!-- user theme --><theme><name>PiXtrix</name></theme><keyboard>
      <keybind key="A-Tab"><action name="NextWindow"/></keybind>
      <keybind key="S-C-Escape"><action name="Execute" command="taskmanager"/></keybind>
    </keyboard><libinput><device category="touch"><naturalScroll>yes</naturalScroll></device></libinput></labwc_config>'''
    config.write_bytes(original)
    config.chmod(0o640)
    result = bind_console(config, tmp_path / 'backups')
    assert result['changed']
    assert (tmp_path / 'backups').joinpath(result['backup']).read_bytes() == original
    root = ET.fromstring(config.read_bytes())
    assert root.find('theme/name').text == 'PiXtrix'
    assert root.find('libinput/device/naturalScroll').text == 'yes'
    assert root.find('keyboard/keybind[@key="A-Tab"]/action').get('name') == 'NextWindow'
    assert root.find('keyboard/keybind[@key="C-S-Escape"]/action').get('command') == 'udeckctl console'
    assert b'<!-- user theme -->' in config.read_bytes()
    assert config.stat().st_mode & 0o777 == 0o640
    updated = config.read_bytes()
    assert not bind_console(config, tmp_path / 'backups')['changed']
    assert config.read_bytes() == updated
    assert len(list((tmp_path / 'backups').iterdir())) == 1


def test_malformed_or_symbolic_config_is_not_changed(tmp_path):
    config = tmp_path / 'rc.xml'
    config.write_text('<invalid')
    with pytest.raises(ValueError):
        bind_console(config, tmp_path / 'backups')
    assert config.read_text() == '<invalid'
    link = tmp_path / 'link.xml'
    link.symlink_to(config)
    with pytest.raises(ValueError):
        bind_console(link, tmp_path / 'backups')
    assert not (tmp_path / 'backups').exists()
