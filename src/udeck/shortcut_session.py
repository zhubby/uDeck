"""Serialize shortcut edits and direction isolation against one labwc instance."""

import hashlib
import os
import signal
import stat
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal

from .i18n import error_text, tr
from .shortcuts import ShortcutStore, atomic_bytes, render_bindings


def configuration_directory(arguments, default):
    directory = os.fspath(default)
    for index, argument in enumerate(arguments):
        if argument in (b'-C', b'--config-dir'):
            directory = os.fsdecode(arguments[index + 1])
        elif argument.startswith(b'--config-dir='):
            directory = os.fsdecode(argument.partition(b'=')[2])
        elif argument.startswith(b'-C') and len(argument) > 2:
            directory = os.fsdecode(argument[2:])
    if not directory:
        raise ValueError(tr('Global shortcuts require the current labwc session'))
    return directory


class ShortcutSession(QObject):
    changed = Signal()
    finished = Signal(object)
    pointerFinished = Signal(bool)

    def __init__(self, store, output, *, config=None, pid=None, parent=None):
        super().__init__(parent)
        self.store, self.output = store, output
        self.pid = 0
        self.config = Path(config) if config else None
        self.available = False
        self.pointer = False
        self.pending = None
        self.queued_pointer = None
        self.token = ''
        self.error = ''
        self.backup = ''
        self.applied = False
        self.started = False
        self.attempts = 0
        self.timer = QTimer(self)
        self.timer.setInterval(400)
        self.timer.timeout.connect(self._probe)
        try:
            self.pid = int(pid if pid is not None else os.environ.get('LABWC_PID', '0'))
            if self.config is None:
                arguments = (Path('/proc') / str(self.pid) / 'cmdline').read_bytes().split(b'\0')
                self.config = self._directory(arguments) / 'rc.xml'
            self.available = self._owns_compositor()
        except (OSError, ValueError, IndexError):
            pass
        if not self.available:
            self.error = tr('Global shortcuts require the current labwc session')

    @property
    def busy(self):
        return self.pending is not None

    def _owns_compositor(self):
        try:
            process = Path('/proc') / str(self.pid)
            arguments = (process / 'cmdline').read_bytes().split(b'\0')
            if (self.pid <= 1 or process.stat().st_uid != os.getuid()
                    or Path(os.fsdecode(arguments[0])).name != 'labwc' or b'--merge-config' in arguments
                    or b'-m' in arguments or self.config is None):
                return False
            directory = self._directory(arguments)
            return (directory.absolute() == self.config.parent.absolute() and not self.config.is_symlink()
                    and self.config.is_file() and self.config.stat().st_uid == os.getuid()
                    and not directory.is_symlink() and directory.stat().st_uid == os.getuid())
        except (OSError, ValueError, IndexError):
            return False

    def _directory(self, arguments):
        process = Path('/proc') / str(self.pid)
        environment = dict(entry.split(b'=', 1) for entry in (process / 'environ').read_bytes().split(b'\0') if b'=' in entry)
        compositor_home = Path(os.fsdecode(environment.get(b'HOME', os.fsencode(Path.home()))))
        config_home = Path(os.fsdecode(environment[b'XDG_CONFIG_HOME'])) if environment.get(b'XDG_CONFIG_HOME') else compositor_home / '.config'
        directory = Path(configuration_directory(arguments, config_home / 'labwc'))
        return directory if directory.is_absolute() else (process / 'cwd').resolve() / directory

    def _backup(self, original):
        if b'udeck-managed-shortcuts' in original:
            return
        directory = Path(os.environ.get('XDG_STATE_HOME', Path.home() / '.local/state')) / 'udeck/shortcuts'
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        if directory.is_symlink() or directory.stat().st_uid != os.getuid():
            raise ValueError(tr('Unsafe shortcut backup directory'))
        path = directory / ('labwc-before-udeck-' + hashlib.sha256(original).hexdigest() + '.xml')
        if path.exists():
            if path.is_symlink() or path.read_bytes() != original:
                raise ValueError(tr('Unsafe shortcut backup file'))
        else:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, 'wb') as stream:
                stream.write(original)
                stream.flush()
                os.fsync(stream.fileno())
        self.backup = str(path)

    def start(self, *, retry=False):
        if not self.busy and (retry or not self.started):
            self.started = True
            self.apply(None, kind='takeover')

    def apply(self, overrides, *, kind='bindings', pointer=None):
        if self.busy:
            raise ValueError(tr('Wait for the current shortcut change'))
        if not self._owns_compositor() or not self.output or not self.output.available:
            self.available = False
            self.error = tr('Global shortcuts require the current labwc session')
            self.finished.emit({'kind': kind, 'success': False, 'error': self.error})
            self.changed.emit()
            return
        self.available = True
        try:
            self.store = ShortcutStore(self.store.path)
            if overrides is not None:
                overrides = self.store.validate(overrides)
            original = self.config.read_bytes()
            self._backup(original)
            self.token = uuid.uuid4().hex
            value = self.pointer if pointer is None else pointer
            generated = render_bindings(original, self.store.bindings(overrides), pointer=value, token=self.token)
            self.pending = {'kind': kind, 'original': original, 'mode': stat.S_IMODE(self.config.stat().st_mode),
                            'overrides': overrides, 'pointer': value, 'generated': generated.encode(),
                            'stored': self.store.path.read_bytes() if self.store.path.exists() else None}
            atomic_bytes(self.config, generated.encode(), self.pending['mode'])
            os.kill(self.pid, signal.SIGHUP)
            self.error = ''
            self.attempts = 0
            self.timer.start()
            self.changed.emit()
        except (OSError, ValueError, ET.ParseError) as error:
            self._finish(False, error_text(error), kind=kind)

    def request_pointer(self, enabled):
        if self.busy:
            self.queued_pointer = enabled
        elif self.pointer == enabled:
            token = self.token
            QTimer.singleShot(0, lambda: self.pointerFinished.emit(True)
                              if not self.busy and self.pointer == enabled and self.token == token else None)
        else:
            self.apply(None, kind='pointer', pointer=enabled)

    def _probe(self):
        self.attempts += 1
        if self.attempts > 7 or not self.output or not self.output.available or not self._owns_compositor():
            self._finish(False, tr('Shortcut configuration confirmation timed out'))
            return
        self.output.chord((194,))

    def acknowledge(self, token):
        if not token or token != self.token or self.error:
            return False
        if not self.busy:
            return self.applied
        try:
            if self.config.read_bytes() != self.pending['generated']:
                raise ValueError(tr('Shortcut settings changed externally; reload and try again'))
            current = self.store.path.read_bytes() if self.store.path.exists() else None
            if current != self.pending['stored']:
                raise ValueError(tr('Shortcut settings changed externally; reload and try again'))
            if self.pending['overrides'] is not None:
                self.store.save(self.pending['overrides'])
        except (OSError, ValueError) as error:
            self._finish(False, error_text(error))
            return False
        self.pointer = self.pending['pointer']
        self.applied = True
        self._finish(True)
        return True

    def _finish(self, success, error='', *, kind=None):
        self.timer.stop()
        operation, self.pending = self.pending, None
        kind = operation['kind'] if operation else kind
        self.error = error
        if not success and operation and self._owns_compositor():
            try:
                if self.config.read_bytes() == operation['generated']:
                    atomic_bytes(self.config, operation['original'], operation['mode'])
                else:
                    self.applied = False
                os.kill(self.pid, signal.SIGHUP)
            except (OSError, ValueError) as rollback:
                self.error = tr('Could not restore shortcut configuration: {error}', error=error_text(rollback))
        self.changed.emit()
        self.finished.emit({'kind': kind, 'success': success, 'error': self.error})
        if kind == 'pointer':
            self.pointerFinished.emit(success)
        queued, self.queued_pointer = self.queued_pointer, None
        if queued is not None:
            self.request_pointer(queued)

    def restore_pointer(self):
        self.queued_pointer = None
        if self.busy:
            self._finish(False, tr('Shortcut change cancelled'))
        if not self._owns_compositor():
            return
        try:
            self.token = uuid.uuid4().hex
            bindings = ShortcutStore(self.store.path).bindings()
            mode = stat.S_IMODE(self.config.stat().st_mode)
            atomic_bytes(self.config, render_bindings(self.config.read_bytes(), bindings, token=self.token).encode(), mode)
            os.kill(self.pid, signal.SIGHUP)
            self.pointer = False
        except (OSError, ValueError, ET.ParseError) as error:
            self.error = error_text(error)

    def close(self):
        self.queued_pointer = None
        if self.busy:
            self._finish(False, tr('Shortcut change cancelled'))
        self.timer.stop()
