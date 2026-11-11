"""A short-lived window whose labwc keybindings are inhibited while recording."""

import json
from pathlib import Path

from PySide6.QtCore import Property, QEvent, QObject, Qt, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QKeySequence
from PySide6.QtQml import QQmlComponent, QQmlContext

from .i18n import error_text, render, tr
from .shortcuts import ACTION_BY_ID, label, normalize


class ShortcutRecorder(QObject):
    changed = Signal()

    def __init__(self, controller, engine, shell, output=None):
        super().__init__(shell)
        self.controller, self.engine, self.shell, self.output = controller, engine, shell, output
        self.window = None
        self.context = None
        self.component = None
        self.identifier = ''
        self.index = -1
        self.sequence = ''
        self.error = ''
        self.ready = False
        self.pressed = set()
        self.focused_once = False
        self.timeout_timer = QTimer(self)
        self.timeout_timer.setSingleShot(True)
        self.timeout_timer.setInterval(15000)
        self.timeout_timer.timeout.connect(self.timeout)
        self.handshake_timer = QTimer(self)
        self.handshake_timer.setSingleShot(True)
        self.handshake_timer.setInterval(1500)
        self.handshake_timer.timeout.connect(self._isolation_failed)

    @Property(str, notify=changed)
    def snapshotJson(self):
        return json.dumps(render({'label': ACTION_BY_ID[self.identifier].label if self.identifier else '',
                                  'sequence': label(self.sequence) if self.sequence else '',
                                  'error': self.error, 'ready': self.ready,
                                  'canConfirm': bool(self.sequence and not self.pressed)}, self.controller.language))

    def open(self, identifier, index):
        self.close()
        session = self.controller.shortcut_session
        if not self.controller.mock and (not session or not session.applied or session.busy
                                         or not self.output or not self.output.available):
            self.controller.notify(tr('Shortcut recording is unavailable'))
            return
        self.identifier, self.index = identifier, index
        self.sequence, self.error = '', ''
        self.ready = self.controller.mock
        self.focused_once = self.controller.mock
        self.pressed.clear()
        self.context = QQmlContext(self.engine.rootContext(), self)
        self.context.setContextProperty('recorder', self)
        self.component = QQmlComponent(self.engine, QUrl.fromLocalFile(str(Path(__file__).parent / 'qml/ShortcutRecorder.qml')), self)
        window = self.component.create(self.context)
        if window is None:
            self.controller.notify(tr('Shortcut recording is unavailable'))
            return
        self.window = window
        window.setTransientParent(self.shell)
        window.resize(min(700, self.shell.width() - 64), 360)
        window.installEventFilter(self)
        window.show()
        window.requestActivate()
        self.timeout_timer.start()
        self.changed.emit()

    @Slot(bool)
    def activeChanged(self, active):
        if self.window is None:
            return
        if active and not self.focused_once:
            self.focused_once = True
            # F23 is conditional on this window's title and app ID. It cannot
            # disable keybindings on a different window if focus changes.
            self.output.chord((193,))
            QTimer.singleShot(80, self._verify_isolation)
            self.handshake_timer.start()
        elif not active and self.focused_once:
            self.close()

    def _verify_isolation(self):
        if self.window and self.window.isActive() and not self.ready:
            self.output.chord((194,))

    def _isolation_failed(self):
        if self.window and not self.ready:
            self.close(restore=True)
            self.controller.notify(tr('Could not isolate shortcut recording'))

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.ShortcutOverride:
            event.accept()
            return True
        if event.type() not in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
            return False
        event.accept()
        if event.isAutoRepeat():
            return True
        key = event.key()
        if key == Qt.Key.Key_F24 and not self.ready:
            if event.type() == QEvent.Type.KeyPress:
                self.ready = True
                self.handshake_timer.stop()
                self.changed.emit()
            return True
        if not self.ready:
            return True
        if event.type() == QEvent.Type.KeyRelease:
            self.pressed.discard(key)
            self.changed.emit()
            return True
        if not event.modifiers() and key == Qt.Key.Key_Escape:
            self.cancel()
            return True
        if self.sequence and not self.pressed and not event.modifiers() and key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.confirm()
            return True
        self.pressed.add(key)
        if key not in (Qt.Key.Key_Control, Qt.Key.Key_Alt, Qt.Key.Key_Shift, Qt.Key.Key_Meta, Qt.Key.Key_AltGr):
            try:
                self.sequence = normalize(QKeySequence(event.keyCombination()).toString(QKeySequence.SequenceFormat.PortableText))
                self.error = ''
            except ValueError as error:
                self.sequence = ''
                self.error = error_text(error)
        self.changed.emit()
        return True

    @Slot()
    def confirm(self):
        if not self.window or not self.sequence or self.pressed:
            return
        identifier, sequence, index = self.identifier, self.sequence, self.index
        self.close(restore=True)
        self.controller.setShortcut(identifier, sequence, index)

    @Slot()
    def cancel(self):
        self.close(restore=True)

    @Slot()
    def timeout(self):
        if self.window:
            self.close(restore=True)
            self.controller.notify(tr('Shortcut recording timed out'))

    def close(self, *, restore=False):
        self.timeout_timer.stop()
        self.handshake_timer.stop()
        window, self.window = self.window, None
        if window:
            window.removeEventFilter(self)
            window.close()
            window.deleteLater()
            if self.context:
                self.context.deleteLater()
            if self.component:
                self.component.deleteLater()
        self.context = self.component = None
        self.pressed.clear()
        if restore:
            self.controller.present.emit()
