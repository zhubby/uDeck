"""System actions, portable shortcut identities and the owned labwc bindings."""

import json
import os
import re
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .i18n import Msg, tr


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
    SystemAction('console', tr(Msg.OPEN_CONSOLE), 'navigation', ('C-S-Escape',), 'udeckctl console'),
    SystemAction('home', tr(Msg.RETURN_TO_HOME), 'navigation', ('C-A-Escape',), 'udeckctl home'),
    SystemAction('switcher', tr(Msg.RUNNING_WINDOWS), 'navigation', ('C-A-Tab',), 'udeckctl switcher'),
    SystemAction('apps', tr(Msg.APPLICATIONS), 'navigation', ('C-A-a',), 'udeckctl apps'),
    SystemAction('files', tr(Msg.FILES_APP), 'navigation', ('C-A-f',), 'udeckctl files'),
    SystemAction('settings', tr(Msg.SYSTEM_SETTINGS), 'navigation', ('C-A-comma',), 'udeckctl settings'),
    SystemAction('quick-settings', tr(Msg.QUICK_SETTINGS), 'navigation', ('C-A-s', 'XF86PowerOff'), 'udeckctl quick-settings'),
    SystemAction('terminal', tr(Msg.OPEN_TERMINAL), 'navigation', ('C-A-t',), 'xdg-terminal-exec'),
    SystemAction('next-window', tr(Msg.NEXT_WINDOW), 'windows', ('A-Tab',), native='NextWindow'),
    SystemAction('previous-window', tr(Msg.PREVIOUS_WINDOW), 'windows', ('A-S-Tab',), native='PreviousWindow'),
    SystemAction('close-window', tr(Msg.CLOSE_CURRENT_WINDOW), 'windows', ('A-F4',), native='Close'),
    SystemAction('pause-game', tr(Msg.PAUSE_EMULATOR), 'windows', ('C-A-m',), 'udeck-app emulator --command pause-game'),
    SystemAction('screenshot', tr(Msg.FULL_SCREEN_SCREENSHOT), 'capture', ('C-A-p', 'Print'), 'udeckctl screenshot', feature='screenshot'),
    SystemAction('lock', tr(Msg.LOCK_SCREEN), 'power', ('C-A-l',), 'udeckctl lock'),
    SystemAction('blank', tr(Msg.TURN_SCREEN_OFF), 'power', ('C-A-b',), 'udeckctl blank'),
    SystemAction('logout', tr(Msg.LOG_OUT), 'power', (), 'udeckctl logout', feature='logout'),
    SystemAction('reboot', tr(Msg.RESTART), 'power', (), 'udeckctl reboot'),
    SystemAction('poweroff', tr(Msg.SHUT_DOWN), 'power', (), 'udeckctl poweroff'),
    SystemAction('volume-up', tr(Msg.VOLUME_UP), 'audio', ('XF86AudioRaiseVolume',), 'udeckctl volume-up', feature='audio'),
    SystemAction('volume-down', tr(Msg.VOLUME_DOWN), 'audio', ('XF86AudioLowerVolume',), 'udeckctl volume-down', feature='audio'),
    SystemAction('mute', tr(Msg.MUTE_SOUND), 'audio', ('XF86AudioMute',), 'udeckctl mute', feature='audio'),
    SystemAction('brightness-up', tr(Msg.BRIGHTNESS_UP), 'brightness', ('XF86MonBrightnessUp',), 'udeckctl brightness-up', feature='brightness'),
    SystemAction('brightness-down', tr(Msg.BRIGHTNESS_DOWN), 'brightness', ('XF86MonBrightnessDown',), 'udeckctl brightness-down', feature='brightness'),
)
ACTION_BY_ID = {action.id: action for action in ACTIONS}
GROUPS = {'navigation': tr(Msg.DESKTOP_NAVIGATION), 'windows': tr(Msg.WINDOWS), 'capture': tr(Msg.SCREENSHOTS),
          'power': tr(Msg.POWER_AND_SESSION), 'audio': tr(Msg.SOUND), 'brightness': tr(Msg.BRIGHTNESS)}
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
        raise ValueError(tr(Msg.USE_ONE_KEY_COMBINATION))
    value = value.strip()
    if '+' in value:
        parts = (value[:-1] + 'plus').split('+') if value.endswith('+') else value.split('+')
    else:
        parts = value.split('-')
    modifiers = set()
    for part in parts[:-1]:
        if part not in MODIFIERS:
            raise ValueError(tr(Msg.UNSUPPORTED_MODIFIER_KEY))
        modifiers.add(MODIFIERS[part])
    key = KEY_ALIASES.get(parts[-1], parts[-1])
    if len(key) == 1 and key.isascii() and key.isalnum():
        key = key.lower()
    if key in ('F23', 'F24'):
        raise ValueError(tr(Msg.THIS_KEY_IS_RESERVED_BY_THE_SYSTEM))
    function = bool(re.fullmatch(r'F(?:[1-9]|1[0-9]|2[0-2])', key))
    if not (function or key in MEDIA_KEYS or key in SPECIAL_KEYS or key in KEY_ALIASES.values()
            or (len(key) == 1 and key.isascii() and key.isalnum())):
        raise ValueError(tr(Msg.UNSUPPORTED_KEY))
    if not function and key not in MEDIA_KEYS | {'Print', 'Pause'} and not modifiers & {'C', 'A', 'W'}:
        raise ValueError(tr(Msg.USE_CTRL_ALT_OR_SUPER_WITH_CHARACTER_AND_NAVIGATION_KEYS))
    return '-'.join([*(mod for mod in ('C', 'A', 'S', 'W') if mod in modifiers), key])


def label(sequence):
    parts = sequence.split('-')
    names = {'C': 'Ctrl', 'A': 'Alt', 'S': 'Shift', 'W': 'Super', 'Escape': 'Esc',
             'comma': ',', 'Print': 'PrintScreen', 'Return': 'Enter',
             'XF86AudioRaiseVolume': tr(Msg.VOLUME_UP_KEY), 'XF86AudioLowerVolume': tr(Msg.VOLUME_DOWN_KEY),
             'XF86AudioMute': tr(Msg.MUTE_KEY), 'XF86MonBrightnessUp': tr(Msg.BRIGHTNESS_UP_KEY),
             'XF86MonBrightnessDown': tr(Msg.BRIGHTNESS_DOWN_KEY), 'XF86PowerOff': tr(Msg.POWER_KEY)}
    result = names.get(parts[-1], parts[-1].upper() if len(parts[-1]) == 1 else parts[-1])
    return '+'.join(names.get(part, part) for part in parts[:-1]) + ('+' if len(parts) > 1 else '') + result


def binding_label(sequences):
    result = label(sequences[0]) if sequences else tr(Msg.UNBOUND)
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
        raise ValueError(tr(Msg.UNSAFE_SHORTCUT_CONFIGURATION_PATH))
    if path.exists() and (not path.is_file() or path.stat().st_uid != os.getuid()):
        raise ValueError(tr(Msg.UNSAFE_SHORTCUT_CONFIGURATION_PATH))
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
        super().__init__(tr(Msg.THIS_COMBINATION_IS_ALREADY_ASSIGNED))


class ShortcutStore:
    def __init__(self, path=None):
        self.path = Path(path) if path else Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'udeck/shortcuts.json'
        self.overrides = {}
        if self.path.is_symlink():
            raise ValueError(tr(Msg.UNSAFE_SHORTCUT_CONFIGURATION_PATH))
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text())
                if data.get('version') != 1 or not isinstance(data.get('bindings'), dict):
                    raise ValueError(tr(Msg.INVALID_SHORTCUT_CONFIGURATION))
                self.overrides = self.validate(data['bindings'])
            except (TypeError, AttributeError, json.JSONDecodeError) as error:
                raise ValueError(tr(Msg.INVALID_SHORTCUT_CONFIGURATION)) from error

    def bindings(self, overrides=None):
        overrides = self.overrides if overrides is None else overrides
        return {action.id: list(overrides.get(action.id, action.defaults)) for action in ACTIONS}

    def validate(self, overrides):
        result = {}
        for identifier, values in overrides.items():
            if identifier not in ACTION_BY_ID or not isinstance(values, list) or len(values) > 8:
                raise ValueError(tr(Msg.INVALID_SHORTCUT_CONFIGURATION))
            normalized = list(dict.fromkeys(normalize(value) for value in values))
            result[identifier] = normalized
        occupied = set()
        for sequences in self.bindings(result).values():
            for sequence in sequences:
                if sequence in occupied:
                    raise ValueError(tr(Msg.DUPLICATE_SHORTCUT_IN_CONFIGURATION))
                occupied.add(sequence)
        return result

    def propose(self, identifier, sequences, *, transfer=False):
        if identifier not in ACTION_BY_ID:
            raise ValueError(tr(Msg.UNKNOWN_SYSTEM_ACTION))
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
        raise ValueError(tr(Msg.NOT_A_LABWC_CONFIGURATION))
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
