import json
import xml.etree.ElementTree as ET

import pytest

from udeck import shortcuts


@pytest.mark.parametrize(('value', 'expected'), [
    ('Alt+Ctrl+P', 'C-A-p'), ('S-C-Escape', 'C-S-Escape'),
    ('Ctrl+Alt+,', 'C-A-comma'), ('PrintScreen', 'Print'),
    ('VolumeUp', 'XF86AudioRaiseVolume'), ('Alt+Shift+Tab', 'A-S-Tab'),
    ('Volume Up', 'XF86AudioRaiseVolume'), ('Volume Down', 'XF86AudioLowerVolume'),
    ('Volume Mute', 'XF86AudioMute'), ('Monitor Brightness Up', 'XF86MonBrightnessUp'),
    ('Monitor Brightness Down', 'XF86MonBrightnessDown'), ('Power Off', 'XF86PowerOff'),
    ('Ctrl+Backspace', 'C-BackSpace'),
])
def test_equivalent_combinations_have_one_identity(value, expected):
    assert shortcuts.normalize(value) == expected


@pytest.mark.parametrize('value', ['A', 'Shift+A', 'Ctrl', 'F23', 'Ctrl+F24', 'Escape',
                                  'Ctrl+K, Ctrl+C', 'Ctrl+Alt+bad;command'])
def test_typing_navigation_and_internal_keys_cannot_become_global_bindings(value):
    with pytest.raises(ValueError):
        shortcuts.normalize(value)


def test_clear_is_persistent_and_missing_override_uses_default(tmp_path):
    store = shortcuts.ShortcutStore(tmp_path / 'shortcuts.json')
    store.save(store.propose('console', []))
    loaded = shortcuts.ShortcutStore(store.path)
    assert loaded.bindings()['console'] == []
    assert loaded.bindings()['screenshot'] == ['C-A-p', 'Print']
    assert loaded.bindings()['poweroff'] == []
    loaded.save(loaded.propose('console', None))
    assert shortcuts.ShortcutStore(store.path).bindings()['console'] == ['C-S-Escape']


def test_transfer_removes_only_the_occupied_alias_and_needs_confirmation(tmp_path):
    store = shortcuts.ShortcutStore(tmp_path / 'shortcuts.json')
    with pytest.raises(shortcuts.ShortcutConflict) as conflict:
        store.propose('terminal', ['Ctrl+Alt+P'])
    assert conflict.value.conflicts == [('C-A-p', 'screenshot')]
    assert not store.path.exists()
    store.save(store.propose('terminal', ['Ctrl+Alt+P'], transfer=True))
    loaded = shortcuts.ShortcutStore(store.path)
    assert loaded.bindings()['terminal'] == ['C-A-p']
    assert loaded.bindings()['screenshot'] == ['Print']
    assert loaded.bindings()['console'] == ['C-S-Escape']


def test_bad_store_never_silently_resets_user_bindings(tmp_path):
    path = tmp_path / 'shortcuts.json'
    path.write_text(json.dumps({'version': 1, 'bindings': {'console': ['F24']}}))
    with pytest.raises(ValueError):
        shortcuts.ShortcutStore(path)
    assert 'F24' in path.read_text()


def test_takeover_replaces_old_and_inherited_bindings_preserving_other_settings(tmp_path):
    original = '''<openbox_config xmlns="http://openbox.org/3.4/rc"><!-- keep -->
      <theme><name>PiXtrix</name></theme><keyboard><default/><repeatRate>30</repeatRate>
      <keybind key="C-A-p"><action name="Execute" command="old-capture"/></keybind>
      <keybind key="W-r"><action name="Execute" command="old-runner"/></keybind></keyboard>
      <mouse><default/></mouse></openbox_config>'''
    store = shortcuts.ShortcutStore(tmp_path / 'shortcuts.json')
    store.save(store.propose('console', ['Ctrl+Alt+Q']))
    result = shortcuts.render_bindings(original, store.bindings(), pointer=True, token='abc123')
    root = ET.fromstring(result)
    ns = '{http://openbox.org/3.4/rc}'
    keyboard = root.find(ns + 'keyboard')
    assert keyboard.find(ns + 'default') is None
    assert keyboard.find(ns + 'repeatRate').text == '30'
    assert root.find(ns + 'theme/' + ns + 'name').text == 'PiXtrix'
    assert root.find(ns + 'mouse/' + ns + 'default') is not None
    assert '<!-- keep -->' in result and 'old-runner' not in result and 'old-capture' not in result
    bindings = {node.get('key'): node for node in keyboard.findall(ns + 'keybind')}
    assert 'C-A-q' in bindings and 'C-S-Escape' not in bindings
    assert bindings['Up'].find(ns + 'action').get('name') == 'If'
    assert bindings['F24'].find(ns + 'action').get('command') == 'udeckctl input-ack abc123'
    assert bindings['F23'].find(ns + 'action').get('name') == 'If'
    assert bindings['C-A-p'].find(ns + 'action').get('command') == 'udeckctl screenshot'
    assert len(bindings) == len(keyboard.findall(ns + 'keybind'))


def test_takeover_removes_bindings_from_repeated_keyboard_sections(tmp_path):
    original = '<labwc_config><keyboard><repeatRate>30</repeatRate></keyboard><keyboard><default/>' \
               '<keybind key="W-r"><action name="Execute" command="old-runner"/></keybind></keyboard></labwc_config>'
    result = shortcuts.render_bindings(original, shortcuts.ShortcutStore(tmp_path / 'keys.json').bindings())
    root = ET.fromstring(result)
    assert not any(node.find('default') is not None for node in root.findall('keyboard'))
    assert 'old-runner' not in result
    assert root.find('keyboard/repeatRate').text == '30'
