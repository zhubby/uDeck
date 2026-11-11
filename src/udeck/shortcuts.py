"""System actions, portable shortcut identities and the owned labwc bindings."""

import json
import os
import re
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .i18n import tr


@dataclass(frozen=True)
class SystemAction:
    id: str
    label: str
    group: str
    defaults: tuple[str, ...]
    command: str = ''
    native: str = ''
    feature: str = ''


ACTIONS = (
    SystemAction('console', tr('Open console'), 'navigation', ('C-S-Escape',), 'udeckctl console'),
    SystemAction('home', tr('Return to home'), 'navigation', ('C-A-Escape',), 'udeckctl home'),
    SystemAction('switcher', tr('Running windows'), 'navigation', ('C-A-Tab',), 'udeckctl switcher'),
    SystemAction('apps', tr('Applications'), 'navigation', ('C-A-a',), 'udeckctl apps'),
    SystemAction('files', tr('Files'), 'navigation', ('C-A-f',), 'udeckctl files'),
    SystemAction('settings', tr('System settings'), 'navigation', ('C-A-comma',), 'udeckctl settings'),
    SystemAction('quick-settings', tr('Quick settings'), 'navigation', ('C-A-s', 'XF86PowerOff'), 'udeckctl quick-settings'),
    SystemAction('terminal', tr('Open terminal'), 'navigation', ('C-A-t',), 'xdg-terminal-exec'),
    SystemAction('next-window', tr('Next window'), 'windows', ('A-Tab',), native='NextWindow'),
    SystemAction('previous-window', tr('Previous window'), 'windows', ('A-S-Tab',), native='PreviousWindow'),
    SystemAction('close-window', tr('Close current window'), 'windows', ('A-F4',), native='Close'),
    SystemAction('pause-game', tr('Pause emulator'), 'windows', ('C-A-m',), 'udeck-app emulator --command pause-game'),
    SystemAction('screenshot', tr('Full screen screenshot'), 'capture', ('C-A-p', 'Print'), 'udeckctl screenshot', feature='screenshot'),
    SystemAction('lock', tr('Lock screen'), 'power', ('C-A-l',), 'udeckctl lock'),
    SystemAction('blank', tr('Turn screen off'), 'power', ('C-A-b',), 'udeckctl blank'),
    SystemAction('logout', tr('Log out'), 'power', (), 'udeckctl logout', feature='logout'),
    SystemAction('reboot', tr('Restart'), 'power', (), 'udeckctl reboot'),
    SystemAction('poweroff', tr('Shut down'), 'power', (), 'udeckctl poweroff'),
    SystemAction('volume-up', tr('Volume up'), 'audio', ('XF86AudioRaiseVolume',), 'udeckctl volume-up', feature='audio'),
    SystemAction('volume-down', tr('Volume down'), 'audio', ('XF86AudioLowerVolume',), 'udeckctl volume-down', feature='audio'),
    SystemAction('mute', tr('Mute sound'), 'audio', ('XF86AudioMute',), 'udeckctl mute', feature='audio'),
    SystemAction('brightness-up', tr('Brightness up'), 'brightness', ('XF86MonBrightnessUp',), 'udeckctl brightness-up', feature='brightness'),
    SystemAction('brightness-down', tr('Brightness down'), 'brightness', ('XF86MonBrightnessDown',), 'udeckctl brightness-down', feature='brightness'),
)
ACTION_BY_ID = {action.id: action for action in ACTIONS}
GROUPS = {'navigation': tr('Desktop navigation'), 'windows': tr('Windows'), 'capture': tr('Screenshots'),
          'power': tr('Power and session'), 'audio': tr('Sound'), 'brightness': tr('Brightness')}
CAPTURE_TITLE = 'uDeck Shortcut Recorder'
MODIFIERS = {'C': 'C', 'Ctrl': 'C', 'Control': 'C', 'A': 'A', 'Alt': 'A', 'Mod1': 'A',
             'S': 'S', 'Shift': 'S', 'W': 'W', 'Super': 'W', 'Meta': 'W', 'Mod4': 'W'}
KEY_ALIASES = {'Esc': 'Escape', 'Enter': 'Return', 'PrintScreen': 'Print', 'PrtSc': 'Print',
               'VolumeUp': 'XF86AudioRaiseVolume', 'VolumeDown': 'XF86AudioLowerVolume',
               'VolumeMute': 'XF86AudioMute', 'MonBrightnessUp': 'XF86MonBrightnessUp',
               'MonBrightnessDown': 'XF86MonBrightnessDown', 'PowerOff': 'XF86PowerOff',
               'Volume Up': 'XF86AudioRaiseVolume', 'Volume Down': 'XF86AudioLowerVolume',
               'Volume Mute': 'XF86AudioMute', 'Monitor Brightness Up': 'XF86MonBrightnessUp',
               'Monitor Brightness Down': 'XF86MonBrightnessDown', 'Power Off': 'XF86PowerOff',
               'Backspace': 'BackSpace',
               'PgUp': 'Prior', 'PageUp': 'Prior', 'PgDown': 'Next', 'PageDown': 'Next',
               'Del': 'Delete', 'Ins': 'Insert', 'Backtab': 'Tab', 'Space': 'space',
               ',': 'comma', '.': 'period', '/': 'slash', '\\': 'backslash',
               ';': 'semicolon', "'": 'apostrophe', '[': 'bracketleft', ']': 'bracketright',
               '-': 'minus', '=': 'equal', '+': 'plus', '`': 'grave', '!': 'exclam',
               '@': 'at', '#': 'numbersign', '$': 'dollar', '%': 'percent', '^': 'asciicircum',
               '&': 'ampersand', '*': 'asterisk', '(': 'parenleft', ')': 'parenright',
               '_': 'underscore', ':': 'colon', '"': 'quotedbl', '<': 'less', '>': 'greater',
               '?': 'question', '{': 'braceleft', '}': 'braceright', '|': 'bar', '~': 'asciitilde'}
SPECIAL_KEYS = {'Escape', 'Return', 'Tab', 'BackSpace', 'Backspace', 'Delete', 'Insert',
                'Home', 'End', 'Prior', 'Next', 'Left', 'Right', 'Up', 'Down', 'Print', 'Pause'}
MEDIA_KEYS = {key for action in ACTIONS for key in action.defaults if key.startswith('XF86')}


def normalize(value):
    if not isinstance(value, str) or not value or len(value) > 100 or ', ' in value:
        raise ValueError(tr('Use one key combination'))
    value = value.strip()
    if '+' in value:
        parts = (value[:-1] + 'plus').split('+') if value.endswith('+') else value.split('+')
    else:
        parts = value.split('-')
    modifiers = set()
    for part in parts[:-1]:
        if part not in MODIFIERS:
            raise ValueError(tr('Unsupported modifier key'))
        modifiers.add(MODIFIERS[part])
    key = KEY_ALIASES.get(parts[-1], parts[-1])
    if len(key) == 1 and key.isascii() and key.isalnum():
        key = key.lower()
    if key in ('F23', 'F24'):
        raise ValueError(tr('This key is reserved by the system'))
    function = bool(re.fullmatch(r'F(?:[1-9]|1[0-9]|2[0-2])', key))
    if not (function or key in MEDIA_KEYS or key in SPECIAL_KEYS or key in KEY_ALIASES.values()
            or (len(key) == 1 and key.isascii() and key.isalnum())):
        raise ValueError(tr('Unsupported key'))
    if not function and key not in MEDIA_KEYS | {'Print', 'Pause'} and not modifiers & {'C', 'A', 'W'}:
        raise ValueError(tr('Use Ctrl, Alt or Super with character and navigation keys'))
    return '-'.join([*(mod for mod in ('C', 'A', 'S', 'W') if mod in modifiers), key])


def label(sequence):
    parts = sequence.split('-')
    names = {'C': 'Ctrl', 'A': 'Alt', 'S': 'Shift', 'W': 'Super', 'Escape': 'Esc',
             'comma': ',', 'Print': 'PrintScreen', 'Return': 'Enter',
             'XF86AudioRaiseVolume': tr('Volume up key'), 'XF86AudioLowerVolume': tr('Volume down key'),
             'XF86AudioMute': tr('Mute key'), 'XF86MonBrightnessUp': tr('Brightness up key'),
             'XF86MonBrightnessDown': tr('Brightness down key'), 'XF86PowerOff': tr('Power key')}
    result = names.get(parts[-1], parts[-1].upper() if len(parts[-1]) == 1 else parts[-1])
    return '+'.join(names.get(part, part) for part in parts[:-1]) + ('+' if len(parts) > 1 else '') + result


def binding_label(sequences):
    result = label(sequences[0]) if sequences else tr('Unbound')
    for sequence in sequences[1:]:
        result = result + ' / ' + label(sequence)
    return result


@lru_cache(maxsize=256)
def _prompt_keys(sequence):
    names = {'C': 'ctrl', 'A': 'alt', 'S': 'shift', 'W': 'command',
             'Escape': 'escape', 'Return': 'enter', 'BackSpace': 'backspace_icon',
             'Print': 'printscreen', 'Prior': 'page_up', 'Next': 'page_down'}
    keys = ['keyboard_' + names.get(part, part.lower()) for part in sequence.split('-')]
    directory = Path(__file__).parent / 'assets/input-prompts'
    if any(not (directory / (key + '.png')).is_file() for key in keys):
        return None
    return tuple(value for index, key in enumerate(keys) for value in (['+', key] if index else [key]))


def key_hint(sequence, title):
    keys = _prompt_keys(sequence)
    return {'keys': list(keys or ()), 'label': title if keys else label(sequence) + ' · ' + title}


def atomic_bytes(path, data, mode=0o600):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.parent.is_symlink() or path.parent.stat().st_uid != os.getuid() or path.is_symlink():
        raise ValueError(tr('Unsafe shortcut configuration path'))
    if path.exists() and (not path.is_file() or path.stat().st_uid != os.getuid()):
        raise ValueError(tr('Unsafe shortcut configuration path'))
    descriptor, temporary = tempfile.mkstemp(prefix='.udeck-shortcuts-', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            os.fchmod(stream.fileno(), mode)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


class ShortcutConflict(ValueError):
    def __init__(self, conflicts):
        self.conflicts = conflicts
        super().__init__(tr('This combination is already assigned'))


class ShortcutStore:
    def __init__(self, path=None):
        self.path = Path(path) if path else Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'udeck/shortcuts.json'
        self.overrides = {}
        if self.path.is_symlink():
            raise ValueError(tr('Unsafe shortcut configuration path'))
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text())
                if data.get('version') != 1 or not isinstance(data.get('bindings'), dict):
                    raise ValueError(tr('Invalid shortcut configuration'))
                self.overrides = self.validate(data['bindings'])
            except (TypeError, AttributeError, json.JSONDecodeError) as error:
                raise ValueError(tr('Invalid shortcut configuration')) from error

    def bindings(self, overrides=None):
        overrides = self.overrides if overrides is None else overrides
        return {action.id: list(overrides.get(action.id, action.defaults)) for action in ACTIONS}

    def validate(self, overrides):
        result = {}
        for identifier, values in overrides.items():
            if identifier not in ACTION_BY_ID or not isinstance(values, list) or len(values) > 8:
                raise ValueError(tr('Invalid shortcut configuration'))
            normalized = list(dict.fromkeys(normalize(value) for value in values))
            result[identifier] = normalized
        occupied = set()
        for sequences in self.bindings(result).values():
            for sequence in sequences:
                if sequence in occupied:
                    raise ValueError(tr('Duplicate shortcut in configuration'))
                occupied.add(sequence)
        return result

    def propose(self, identifier, sequences, *, transfer=False):
        if identifier not in ACTION_BY_ID:
            raise ValueError(tr('Unknown system action'))
        result = {key: list(values) for key, values in self.overrides.items()}
        values = list(ACTION_BY_ID[identifier].defaults) if sequences is None else list(dict.fromkeys(normalize(value) for value in sequences))
        conflicts = [(sequence, key) for key, bindings in self.bindings().items() if key != identifier
                     for sequence in values if sequence in bindings]
        if conflicts and not transfer:
            raise ShortcutConflict(conflicts)
        for sequence, key in conflicts:
            result[key] = [value for value in self.bindings(result)[key] if value != sequence]
        if sequences is None:
            result.pop(identifier, None)
        else:
            result[identifier] = values
        return self.validate(result)

    def save(self, overrides):
        values = self.validate(overrides)
        atomic_bytes(self.path, json.dumps({'version': 1, 'bindings': values}, indent=2).encode())
        self.overrides = values


def render_bindings(original, bindings, *, pointer=False, token='startup'):
    if not re.fullmatch(r'[a-zA-Z0-9]{1,64}', token):
        raise ValueError('Invalid configuration generation')
    root = ET.fromstring(original, parser=ET.XMLParser(target=ET.TreeBuilder(insert_comments=True)))
    namespace, separator, name = root.tag.rpartition('}')
    prefix = namespace + '}' if separator else ''
    if name not in ('labwc_config', 'openbox_config'):
        raise ValueError(tr('Not a labwc configuration'))
    if prefix:
        ET.register_namespace('', namespace.removeprefix('{'))
    keyboard = root.find(prefix + 'keyboard')
    if keyboard is None:
        keyboard = ET.SubElement(root, prefix + 'keyboard')
    for section in root.findall(prefix + 'keyboard'):
        for child in list(section):
            if child.tag in (prefix + 'keybind', prefix + 'default'):
                section.remove(child)
    if not any(child.tag is ET.Comment and child.text == 'udeck-managed-shortcuts' for child in keyboard):
        keyboard.append(ET.Comment('udeck-managed-shortcuts'))
    for action in ACTIONS:
        for sequence in bindings[action.id]:
            binding = ET.SubElement(keyboard, prefix + 'keybind', key=normalize(sequence))
            attributes = {'name': action.native} if action.native else {'name': 'Execute', 'command': action.command}
            ET.SubElement(binding, prefix + 'action', **attributes)
    if pointer:
        for direction in ('Up', 'Down', 'Left', 'Right'):
            binding = ET.SubElement(keyboard, prefix + 'keybind', key=direction)
            action = ET.SubElement(binding, prefix + 'action', name='If')
            ET.SubElement(action, prefix + 'query', identifier='io.github.zhubby.uDeck.NoSuchWindow')
    binding = ET.SubElement(keyboard, prefix + 'keybind', key='F23')
    action = ET.SubElement(binding, prefix + 'action', name='If')
    ET.SubElement(action, prefix + 'query', identifier='io.github.zhubby.uDeck', title=CAPTURE_TITLE)
    branch = ET.SubElement(action, prefix + 'then')
    ET.SubElement(branch, prefix + 'action', name='ToggleKeybinds')
    binding = ET.SubElement(keyboard, prefix + 'keybind', key='F24', allowWhenLocked='yes')
    ET.SubElement(binding, prefix + 'action', name='Execute', command='udeckctl input-ack ' + token)
    return ET.tostring(root, encoding='unicode')
