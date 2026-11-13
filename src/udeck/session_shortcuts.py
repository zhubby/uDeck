"""Legacy offline helper using the shared system action registry.

The CLI uses ShortcutSession instead so it can confirm compositor reloads.
"""

import hashlib
import os
import stat
import xml.etree.ElementTree as ET
from pathlib import Path

from .i18n import Msg, tr
from .shortcuts import ShortcutStore, atomic_bytes, render_bindings


def bind_console(config, backups):
    config, backups = Path(config), Path(backups)
    if config.is_symlink() or not config.is_file() or config.stat().st_uid != os.getuid():
        raise ValueError(tr(Msg.SHORTCUT_USER_CONFIG_REQUIRED))
    original = config.read_bytes()
    try:
        generated = render_bindings(original, ShortcutStore().bindings(), token='compat').encode()
    except ET.ParseError as error:
        raise ValueError(tr(Msg.SHORTCUT_INVALID_XML, error=error)) from error
    if generated == original:
        return {'changed': False, 'config': str(config)}
    result = {'changed': True, 'config': str(config)}
    if b'udeck-managed-shortcuts' not in original:
        backups.mkdir(parents=True, exist_ok=True, mode=0o700)
        if backups.is_symlink() or backups.stat().st_uid != os.getuid():
            raise ValueError(tr(Msg.SHORTCUT_UNSAFE_BACKUP_DIRECTORY))
        backup = backups / ('labwc-before-udeck-' + hashlib.sha256(original).hexdigest() + '.xml')
        if backup.exists():
            if backup.is_symlink() or backup.read_bytes() != original:
                raise ValueError(tr(Msg.SHORTCUT_UNSAFE_BACKUP_FILE))
        else:
            with backup.open('xb') as stream:
                os.fchmod(stream.fileno(), 0o600)
                stream.write(original)
                stream.flush()
                os.fsync(stream.fileno())
        result['backup'] = str(backup)
    atomic_bytes(config, generated, stat.S_IMODE(config.stat().st_mode))
    return result


def install():
    config = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'labwc/rc.xml'
    backups = Path(os.environ.get('XDG_STATE_HOME', Path.home() / '.local/state')) / 'udeck/shortcuts'
    return bind_console(config, backups)
