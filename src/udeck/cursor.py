from PySide6.QtCore import Property, QEvent, QObject, QPointF, Qt, QTimer, Signal
from PySide6.QtGui import QCursor


class PointerCursor(QObject):
    positionChanged = Signal()
    visibleChanged = Signal()

    def __init__(self, window, *, pointer=None, gamepad=None):
        super().__init__(window)
        self.window = window
        self._position = QPointF(window.width() / 2, window.height() / 2)
        self._visible = False
        self._closed = False
        self._last_mouse_position = QPointF(window.mapFromGlobal(QCursor.pos()))
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(3000)
        self.timer.timeout.connect(self.hide)
        window.installEventFilter(self)
        window.activeChanged.connect(self._window_changed)
        window.visibleChanged.connect(self._window_changed)
        window.widthChanged.connect(self._resize)
        window.heightChanged.connect(self._resize)
        if pointer:
            pointer.motion.connect(self.move_relative)
            pointer.button.connect(self.navigation_button)
        if gamepad:
            gamepad.button.connect(self.navigation_button)
            gamepad.direction.connect(self.navigation_button)
            gamepad.auxiliaryButton.connect(self.navigation_button)

    @Property(QPointF, notify=positionChanged)
    def position(self):
        return QPointF(self._position)

    @Property(bool, notify=visibleChanged)
    def visible(self):
        return self._visible

    @Property(int, constant=True)
    def diameter(self):
        return 18

    def _available(self):
        return not self._closed and self.window.isActive() and self.window.isVisible()

    def _clamp(self, position):
        radius = self.diameter / 2
        horizontal = max(radius, self.window.width() - radius)
        vertical = max(radius, self.window.height() - radius)
        return QPointF(max(radius, min(position.x(), horizontal)),
                       max(radius, min(position.y(), vertical)))

    def _resize(self):
        if self._closed:
            return
        position = self._clamp(self._position)
        if position != self._position:
            self._position = position
            self.positionChanged.emit()

    def _show_at(self, position):
        if not self._available():
            return
        position = self._clamp(position)
        if position != self._position:
            self._position = position
            self.positionChanged.emit()
        if not self._visible:
            self._visible = True
            self.visibleChanged.emit()
        self.timer.start()

    def move_relative(self, axis, value):
        if axis not in (0, 1) or not value:
            return
        delta = QPointF(value, 0) if axis == 0 else QPointF(0, value)
        self._show_at(self._position + delta)

    def navigation_button(self, action, pressed):
        if pressed:
            self.hide()

    def _window_changed(self):
        if self._closed:
            return
        self.hide()
        self._last_mouse_position = QPointF(self.window.mapFromGlobal(QCursor.pos()))

    def hide(self):
        self.timer.stop()
        if self._visible:
            self._visible = False
            self.visibleChanged.emit()

    def eventFilter(self, watched, event):
        if event.type() in (QEvent.Type.KeyPress, QEvent.Type.Leave):
            self.hide()
        elif (event.type() == QEvent.Type.MouseMove
              and event.source() == Qt.MouseEventSource.MouseEventNotSynthesized):
            position = event.position()
            if position != self._last_mouse_position:
                self._last_mouse_position = QPointF(position)
                self._show_at(position)
        return False

    def close(self):
        if self._closed:
            return
        self._closed = True
        self.hide()
        self.window.removeEventFilter(self)
