"""Add the requested global shortcut to an existing desktop's labwc config."""

import os
import stat
import tempfile
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path


def bind_console(config, backups):
    if config.is_symlink() or not config.is_file() or config.stat().st_uid != os.getuid():
        raise ValueError('An existing, user-owned regular labwc rc.xml is required')
    original = config.read_bytes()
    try:
        root = ET.fromstring(original, parser=ET.XMLParser(target=ET.TreeBuilder(insert_comments=True)))
    except ET.ParseError as error:
        raise ValueError('Invalid labwc XML: ' + str(error)) from error
    if root.tag != 'labwc_config':
        raise ValueError('Not a labwc configuration')
    keyboard = root.find('keyboard')
    if keyboard is None:
        keyboard = ET.SubElement(root, 'keyboard')
    matches = [node for node in keyboard.findall('keybind') if set(node.get('key', '').split('-')) == {'C', 'S', 'Escape'}]
    if (len(matches) == 1 and len(matches[0]) == 1 and matches[0][0].get('name') == 'Execute'
            and matches[0][0].get('command') == 'udeckctl console'):
        return {'changed': False, 'config': str(config)}
    for node in matches:
        keyboard.remove(node)
    binding = ET.SubElement(keyboard, 'keybind', key='C-S-Escape')
    ET.SubElement(binding, 'action', name='Execute', command='udeckctl console')
    backups.mkdir(parents=True, exist_ok=True, mode=0o700)
    if backups.is_symlink() or backups.stat().st_uid != os.getuid():
        raise ValueError('Unsafe shortcut backup directory')
    backup = backups / ('labwc-before-console-' + uuid.uuid4().hex + '.xml')
    with backup.open('xb') as stream:
        os.fchmod(stream.fileno(), 0o600)
        stream.write(original)
    descriptor, temporary = tempfile.mkstemp(prefix='.udeck-shortcut-', dir=config.parent)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            os.fchmod(stream.fileno(), stat.S_IMODE(config.stat().st_mode))
            stream.write(ET.tostring(root, encoding='utf-8', xml_declaration=True))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, config)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return {'changed': True, 'config': str(config), 'backup': str(backup)}


def install():
    config = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'labwc/rc.xml'
    backups = Path(os.environ.get('XDG_STATE_HOME', Path.home() / '.local/state')) / 'udeck/shortcuts'
    return bind_console(config, backups)
