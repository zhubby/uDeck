import argparse
import os
import re
import signal
import tempfile
import uuid
import xml.etree.ElementTree as ElementTree
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal

from .i18n import error_text, tr


def render_config(original, pointer, token):
    if not re.fullmatch(r'[a-zA-Z0-9]{1,64}', token):
        raise ValueError('Invalid configuration generation')
    root = ElementTree.fromstring(original)
    keyboard = root.find('keyboard')
    if keyboard is None:
        keyboard = ElementTree.SubElement(root, 'keyboard')
    for binding in list(keyboard):
        if binding.get('key') == 'F24':
            keyboard.remove(binding)
    if pointer:
        for direction in ('Up', 'Down', 'Left', 'Right'):
            binding = ElementTree.SubElement(keyboard, 'keybind', key=direction)
            action = ElementTree.SubElement(binding, 'action', name='If')
            ElementTree.SubElement(action, 'query', identifier='io.github.zhubby.uDeck.NoSuchWindow')
    binding = ElementTree.SubElement(keyboard, 'keybind', key='F24', allowWhenLocked='yes')
    ElementTree.SubElement(binding, 'action', name='Execute', command='udeckctl input-ack ' + token)
    return ElementTree.tostring(root, encoding='unicode')


def atomic_write(path, contents):
    descriptor, temporary = tempfile.mkstemp(prefix='.config-', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'w') as stream:
            stream.write(contents)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def prepare(directory, template):
    directory.mkdir(parents=True, mode=0o700, exist_ok=True)
    if directory.is_symlink() or directory.stat().st_uid != os.getuid():
        raise RuntimeError(tr('不安全的会话配置目录'))
    directory.chmod(0o700)
    original = (template / 'rc.xml').read_text()
    atomic_write(directory / 'base.xml', original)
    atomic_write(directory / 'rc.xml', render_config(original, False, uuid.uuid4().hex))
    for name in ('autostart', 'environment'):
        atomic_write(directory / name, (template / name).read_text())
    return directory


class DirectionIsolation(QObject):
    finished = Signal(bool)

    def __init__(self, output, parent=None):
        super().__init__(parent)
        self.output = output
        self.directory = Path(os.environ.get('UDECK_CONFIG_DIR', '/nonexistent'))
        self.pid = 0
        self.available = False
        self.applied = False
        self.pending = None
        self.token = ''
        self.error = ''
        self.attempts = 0
        self.timer = QTimer(self)
        self.timer.setInterval(400)
        self.timer.timeout.connect(self._probe)
        try:
            self.pid = int(os.environ.get('LABWC_PID', '0'))
            self.available = self._owns_compositor()
        except ValueError:
            pass

    def _owns_compositor(self):
        try:
            process = Path('/proc') / str(self.pid)
            arguments = (process / 'cmdline').read_bytes().split(b'\0')
            return (os.environ.get('UDECK_SESSION') == '1' and self.pid > 1
                    and process.stat().st_uid == os.getuid() and Path(os.fsdecode(arguments[0])).name == 'labwc'
                    and b'-C' in arguments and arguments[arguments.index(b'-C') + 1] == os.fsencode(self.directory)
                    and self.directory.stat().st_uid == os.getuid() and not self.directory.is_symlink()
                    and (self.directory / 'base.xml').is_file())
        except (OSError, ValueError, IndexError):
            return False

    def request(self, enabled):
        if not self.available or not self._owns_compositor():
            self.available = False
            self.error = tr('完整兼容模式需要独立 uDeck 会话')
            QTimer.singleShot(0, lambda: self.finished.emit(False))
            return
        if self.pending is enabled:
            return
        if self.pending is None and self.applied == enabled:
            token = self.token
            QTimer.singleShot(0, lambda: self.finished.emit(True)
                              if self.pending is None and self.applied == enabled and self.token == token else None)
            return
        self.pending = enabled
        self.token = uuid.uuid4().hex
        self.attempts = 0
        try:
            atomic_write(self.directory / 'rc.xml', render_config((self.directory / 'base.xml').read_text(), enabled, self.token))
            os.kill(self.pid, signal.SIGHUP)
            self.timer.start()
        except (OSError, ValueError, ElementTree.ParseError) as error:
            self._fail(error_text(error))

    def _probe(self):
        self.attempts += 1
        if self.attempts > 7 or not self.output.available:
            self._fail(tr('方向键配置确认超时；已请求恢复普通键盘'))
            return
        self.output.chord((194,))

    def acknowledge(self, token):
        if token and token == self.token and self.pending is None and not self.error:
            return True
        if self.pending is None or token != self.token:
            return False
        self.applied = self.pending
        self.pending = None
        self.timer.stop()
        self.error = ''
        self.finished.emit(True)
        return True

    def _fail(self, message):
        self.timer.stop()
        self.pending = None
        self.error = message
        self.restore()
        self.finished.emit(False)

    def restore(self):
        self.timer.stop()
        self.pending = None
        if not self.available or not self._owns_compositor():
            return
        try:
            self.token = uuid.uuid4().hex
            atomic_write(self.directory / 'rc.xml', render_config((self.directory / 'base.xml').read_text(), False, self.token))
            os.kill(self.pid, signal.SIGHUP)
        except (OSError, ValueError, ElementTree.ParseError):
            pass
        self.applied = False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=('prepare', 'restore'))
    options = parser.parse_args()
    directory = Path(os.environ.get('XDG_RUNTIME_DIR', '/run/user/' + str(os.getuid()))) / 'udeck/labwc'
    if options.command == 'prepare':
        print(prepare(directory, Path('/usr/share/udeck/labwc')))
    else:
        DirectionIsolation(None).restore()


if __name__ == '__main__':
    main()
