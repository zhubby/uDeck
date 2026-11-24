"""
[INPUT]: 依赖 Reader 和 Terminal 的真实入口及 Qt 鼠标事件。
[OUTPUT]: 验证内置窗口的圆点、点击动画和原输入策略。
[POS]: 原生指针的独立入口探针；终端使用隔离 Mock 会话。
[PROTOCOL]: Update this header on change, then check AGENTS.md
"""

import json
import os
import sys
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QEvent, QEventLoop, QObject, QPointF, Qt, QTimer
from PySide6.QtGui import QGuiApplication, QMouseEvent


def pause(milliseconds):
    loop = QEventLoop()
    QTimer.singleShot(milliseconds, loop.quit)
    loop.exec()


class Delivery(QObject):
    def __init__(self, window):
        super().__init__(window)
        self.events = []
        window.installEventFilter(self)

    def eventFilter(self, watched, event):
        if event.type() in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease):
            self.events.append(event.type())
        return False


def inspect_windows(windows, kind, output):
    application = QGuiApplication.instance()
    override = application.overrideCursor()
    assert override is not None and override.shape() == Qt.CursorShape.BlankCursor
    reduced = os.environ.get("UDECK_REDUCED_MOTION") == "1"
    cursors = []
    for index, window in enumerate(windows):
        window.requestActivate()
        pause(100)
        assert window.isActive()
        cursor = window.property("pointerCursor")
        assert cursor is not None
        cursors.append(cursor)
        layer = window.findChild(QObject, "pointerLayer")
        orb = window.findChild(QObject, "pointerOrb")
        pulse = window.findChild(QObject, "pointerClickPulse")
        animation = window.findChild(QObject, "pointerPulseAnimation")
        assert layer is not None and not layer.property("enabled")
        assert orb is not None and orb.property("width") <= 10
        assert bool(layer.property("reducedMotion")) == reduced
        delivery = Delivery(window)
        point = QPointF(420, 260)

        def mouse(event_type, button, buttons, point=point, window=window):
            event = QMouseEvent(event_type, point, point, button, buttons, Qt.KeyboardModifier.NoModifier)
            application.sendEvent(window, event)

        mouse(QEvent.Type.MouseMove, Qt.MouseButton.NoButton, Qt.MouseButton.NoButton)
        pause(180)
        assert cursor.visible and cursor.position == point
        assert orb.property("x") + orb.property("width") / 2 == point.x()
        assert orb.property("y") + orb.property("height") / 2 == point.y()
        assert window.grabWindow().save(str(output / f"{kind}-{index}-dot.png"))
        mouse(QEvent.Type.MouseButtonPress, Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton)
        assert cursor.pressed and not cursor.timer.isActive()
        pause(100)
        assert orb.property("scale") < 1
        mouse(QEvent.Type.MouseButtonRelease, Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton)
        assert not cursor.pressed
        pause(30)
        assert bool(pulse.property("opacity") > 0) != reduced
        assert window.grabWindow().save(str(output / f"{kind}-{index}-click.png"))
        assert len(delivery.events) == (0 if kind == "terminal" else 2)
        pause(280)
        assert not animation.property("running") and pulse.property("opacity") == 0
    if len(windows) == 2:
        assert not cursors[0].visible
    cursors[-1].close()
    assert not cursors[-1].visible and not cursors[-1].pressed and not cursors[-1].timer.isActive()
    return {"passed": True, "inputPolicyPreserved": True, "focusReset": True, "windows": len(windows)}


def run(kind, output):
    output.mkdir(parents=True, exist_ok=True)
    outcome = []

    def verify(windows):
        try:
            outcome.append(inspect_windows(windows, kind, output))
        except Exception as error:
            import traceback
            outcome.append({"passed": False, "error": str(error), "traceback": traceback.format_exc()})
        finally:
            QGuiApplication.instance().quit()

    if kind == "reader":
        from udeck.apps import runtime
        factory = runtime.make_controller

        def make_controller(*args):
            controller = factory(*args)

            def ready():
                if controller.reader_ready:
                    verify([controller.window])
                else:
                    QTimer.singleShot(50, ready)

            QTimer.singleShot(250, ready)
            return controller

        runtime.make_controller = make_controller
        document = output / "original.txt"
        document.write_text("圆点指针测试。Pointer animation keeps the click position exact.\n" * 20)
        result = runtime.main(["reader", str(document), "--isolated", "--no-input", "--quit-after", "20"])
    else:
        from udeck.terminal import runtime
        open_window = runtime.Coordinator.open

        def open_windows(coordinator, request):
            open_window(coordinator, request)
            open_window(coordinator, replace(request, new_window=True))
            QTimer.singleShot(250, lambda: verify([entry["window"] for entry in coordinator.windows]))

        runtime.Coordinator.open = open_windows
        result = runtime.main(["--mock", "--no-input", "--quit-after", "20"])
    assert outcome and outcome[0]["passed"], outcome
    assert result == 0, result
    (output / "report.json").write_text(json.dumps(outcome[0], indent=2) + "\n")
    print(json.dumps(outcome[0]), flush=True)


if __name__ == "__main__":
    run(sys.argv[1], Path(sys.argv[2]))
