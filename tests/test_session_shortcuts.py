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


@pytest.mark.parametrize('root_name,namespace', [
    ('openbox_config', 'http://openbox.org/3.4/rc'),
    ('labwc_config', 'http://openbox.org/3.4/rc'),
    ('openbox_config', ''),
])
def test_stock_openbox_configuration_keeps_namespace_and_existing_controls(tmp_path, root_name, namespace):
    config = tmp_path / 'rc.xml'
    declaration = f' xmlns="{namespace}"' if namespace else ''
    original = f'''<?xml version="1.0"?>
<{root_name}{declaration}><!-- stock desktop --><keyboard>
  <keybind key="XF86MonBrightnessUp"><action name="Execute" command="rpi-backlight up"/></keybind>
  <keybind key="C-S-Escape"><action name="Execute" command="taskmanager"/></keybind>
</keyboard><theme><name>PiXtrix</name></theme></{root_name}>'''.encode()
    config.write_bytes(original)
    result = bind_console(config, tmp_path / 'backups')
    assert result['changed']
    assert (tmp_path / 'backups').joinpath(result['backup']).read_bytes() == original
    root = ET.fromstring(config.read_bytes())
    prefix = '{' + namespace + '}' if namespace else ''
    assert root.tag == prefix + root_name
    assert root.find(f'{prefix}theme/{prefix}name').text == 'PiXtrix'
    keyboards = root.findall(prefix + 'keyboard')
    assert len(keyboards) == 1
    bindings = keyboards[0].findall(prefix + 'keybind')
    assert len(bindings) == 2
    assert bindings[0].find(prefix + 'action').get('command') == 'rpi-backlight up'
    assert bindings[1].get('key') == 'C-S-Escape'
    assert bindings[1].find(prefix + 'action').get('command') == 'udeckctl console'
    assert b'<!-- stock desktop -->' in config.read_bytes()
    assert not bind_console(config, tmp_path / 'backups')['changed']
    assert len(list((tmp_path / 'backups').iterdir())) == 1
