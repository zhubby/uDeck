"""
[INPUT]: 依赖私有 labwc、随机会话总线与独立 Qt 客户端。
[OUTPUT]: 验证合帧位移、桌面圆点连续性和 Console 输入。
[POS]: 安装版轨迹球的合成器回归；不代表实体手感验收。
[PROTOCOL]: Update this header on change, then check AGENTS.md

在私有 D-Bus/Wayland 会话中运行，PATH 需包含 udeckctl。
"""

import json
import os
import runpy
import select
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtDBus import QDBusConnection
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine

from udeck.console import ConsolePanel
from udeck.controller import ShellController
from udeck.core import ConfigStore
from udeck.cursor import PointerCursor
from udeck.main import CONTROL_INTERFACE, CONTROL_PATH, Control, IconProvider
from udeck.mock import MockBackend
from udeck.trackball import TrackballInput
from udeck.virtual_input import VirtualInput
from udeck.windows import APP_ID, WindowService


class Pointer(QObject):
    button = Signal(str, bool)
    middleButton = Signal(bool)
    middleButtonTimed = Signal(bool, float)
    reset = Signal()
    motion = Signal(int, int)
    motionFrame = Signal(int, int, float)

    def discard_motion(self):
        pass

    def __init__(self):
        super().__init__()
        self.middleButton.connect(lambda pressed: self.middleButtonTimed.emit(pressed, time.monotonic()))


def main():
    application = QGuiApplication([])
    application.setDesktopFileName(APP_ID)
    application.setOverrideCursor(Qt.CursorShape.BlankCursor)
    windows, output, pointer = WindowService(), VirtualInput(), Pointer()
    windows.start()
    output.start()
    assert windows.available and output.available, output.error
    probe = runpy.run_path(str(Path(__file__).with_name('verify-application-input.py')))['PROBE']
    processes, checks = [], []

    def until(predicate, timeout=8):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            application.processEvents()
            if predicate():
                return
            time.sleep(0.01)
        raise RuntimeError('Trackball/console probe timed out')

    def pump(seconds=0.15):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            application.processEvents()
            time.sleep(0.01)

    def receive(process):
        until(lambda: bool(select.select([process.stdout], [], [], 0)[0]) or process.poll() is not None)
        line = process.stdout.readline()
        assert line, process.stderr.read()
        return json.loads(line)

    def report(process):
        process.stdin.write('report\n')
        process.stdin.flush()
        return receive(process)

    def reset(process):
        process.stdin.write('reset\n')
        process.stdin.flush()
        assert receive(process)['reset']

    def assert_point(actual, expected, label):
        assert all(abs(actual[index] - expected[index]) <= 1 for index in (0, 1)), {
            'check': label, 'actual': actual, 'expected': expected,
        }

    def client_point(position):
        assert position is not None, 'Qt client did not receive pointer motion'
        # Wayland 不提供跨进程的全局原点；全屏窗口使用内容坐标。
        return position['x'], position['y']

    def move_client(process, dx, dy, before, label):
        reset(process)
        pointer.motionFrame.emit(dx, dy, time.monotonic())
        pump()
        result = report(process)
        expected = (before[0] + dx * 4, before[1] + dy * 4)
        actual = client_point(result['lastPosition'])
        assert_point(actual, expected, label)
        moved = [client_point(position) for position in result['motionPositions']
                 if client_point(position) != before]
        assert moved, {'check': label, 'report': result}
        # Qt 可合并重复事件，但不应出现只更新一个轴的中间位置。
        for position in moved:
            assert_point(position, expected, label + ': paired axes')
        return actual, {'check': label, 'rawDelta': [dx, dy], 'expectedDelta': [dx * 4, dy * 4],
                        'actualPosition': list(actual), 'qtMotionPositions': result['motionPositions']}

    with tempfile.TemporaryDirectory(prefix='udeck-console-probe-') as directory:
        controller = ShellController(MockBackend(), windows, ConfigStore(Path(directory) / 'settings.json'), mock=True)
        panel = ConsolePanel(controller, windows)
        trackball = TrackballInput(pointer, controller, windows, output)
        control = Control(controller, windows)
        control.console_panel = panel
        bus = QDBusConnection.sessionBus()
        assert bus.registerService(APP_ID)
        assert bus.registerObject(CONTROL_PATH, CONTROL_INTERFACE, control, QDBusConnection.RegisterOption.ExportAllSlots)
        engine = QQmlApplicationEngine()
        engine.addImageProvider('desktop', IconProvider())
        for name, value in (('controller', controller), ('windowedPreview', False), ('headlessPreview', False)):
            engine.rootContext().setContextProperty(name, value)
        import udeck.main

        engine.load(str(Path(udeck.main.__file__).parent / 'qml/Main.qml'))
        assert engine.rootObjects()
        shell = engine.rootObjects()[0]
        cursor = PointerCursor(shell, pointer=pointer)
        shell.setProperty('pointerCursor', cursor)
        shell.activeChanged.connect(lambda: controller.windowActive(shell.isActive()))
        controller.present.connect(windows.activate_shell)
        try:
            until(shell.isActive)
            for platform in ('wayland', 'xcb'):
                title = 'uDeck trackball check ' + platform
                process = subprocess.Popen([sys.executable, '-c', probe, title, 'io.github.zhubby.uDeck.Reader'],
                                           env={**os.environ, 'QT_QPA_PLATFORM': platform},
                                           stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                processes.append(process)
                assert receive(process)['ready']
                until(lambda title=title: any(entry['name'] == title and entry['active'] for entry in windows.entries()))
                target = next(entry['id'] for entry in windows.entries() if entry['name'] == title)
                assert windows.handles[target]['appId'] == 'io.github.zhubby.uDeck.Reader', windows.entries()
                until(lambda target=target: not trackball.foreground and trackball.target and trackball.target[0] == target)
                # 绝对定位只用于建立初始条件，后续生产位移全部走相对入口。
                # 两轮使用不同起点，避免 Qt 将同坐标的再次进入合并为无位移。
                origin = (640, 360) if platform == 'wayland' else (608, 384)
                output.position, output.extent = origin, (1280, 720)
                output.move(0, 0)
                pump()
                position = client_point(report(process)['lastPosition'])
                # 故意污染旧坐标簿，验证相对移动不依赖旧绝对位置或范围。
                output.position, output.extent = (21, 35), (193, 137)
                movement_checks = []
                for dx, dy, label in ((12, 3, 'positive diagonal'), (-5, -7, 'negative diagonal'),
                                      (5, 0, 'horizontal only'), (0, -4, 'vertical only')):
                    position, check = move_client(process, dx, dy, position, label)
                    movement_checks.append(check)
                pointer.middleButton.emit(True)
                pump(0.05)
                pointer.middleButton.emit(False)
                pointer.middleButton.emit(True)
                pump(2.15)
                pointer.middleButton.emit(False)
                pump()
                inputs = report(process)
                assert inputs['buttons'] == ['down:1', 'up:1', 'down:2', 'up:2'], inputs
                assert inputs['moves'] >= 1, inputs
                # Ctrl+Shift+Esc must reach labwc's Execute -> a new udeckctl -> D-Bus.
                output.chord((29, 42, 1))
                until(lambda: controller.modal.get('source') == 'console' and shell.isActive())
                assert len(controller.modal['options']) == 5
                until(lambda: trackball.foreground)
                pointer.motionFrame.emit(6, -2, time.monotonic())
                try:
                    until(lambda: cursor.visible)
                except RuntimeError as error:
                    raise AssertionError({'platform': platform, 'foreground': trackball.foreground,
                                          'target': trackball._target(), 'outputAvailable': output.available,
                                          'outputError': output.error,
                                          'shell': [shell.isActive(), shell.isVisible(), shell.isExposed(), shell.visibility().value],
                                          'geometry': [shell.x(), shell.y(), shell.width(), shell.height()],
                                          'windows': windows.entries(), 'client': report(process)}) from error
                pump()
                actual_shell = (cursor.position.x(), cursor.position.y())
                assert_point(actual_shell, (position[0] + 24, position[1] - 8),
                             'application to desktop continuity ' + json.dumps({
                                 'platform': platform, 'shellGeometry': [shell.x(), shell.y(), shell.width(), shell.height()],
                                 'visibility': shell.visibility().value, 'lastClient': inputs['lastPosition'],
                                 'shellMouse': [cursor._last_mouse_position.x(), cursor._last_mouse_position.y()],
                             }))
                desktop_check = {'previousApplicationPosition': list(position), 'rawDelta': [6, -2],
                                 'actualDotContentPosition': list(actual_shell)}
                output.chord((1,))
                until(lambda target=target: not controller.modal and any(entry['id'] == target and entry['active'] for entry in windows.entries()))
                until(lambda: not trackball.foreground)
                pump()
                position, return_check = move_client(process, -4, 5, actual_shell,
                                                     'desktop to application continuity')
                movement_checks.append(return_check)
                assert not controller.backend.actions
                # An interrupted gesture must not click in the new foreground window.
                recovery_buttons = report(process)['buttons']
                pointer.middleButton.emit(True)
                pointer.reset.emit()
                pointer.middleButton.emit(False)
                pump()
                assert report(process)['buttons'] == recovery_buttons
                checks.append({'platform': platform, 'clicks': inputs['buttons'], 'globalShortcut': True,
                               'restoredWindow': True, 'recoveryDidNotClick': True,
                               'movement': movement_checks, 'desktopContinuity': desktop_check,
                               'staleAbsoluteBookkeepingIgnored': True})
                windows.request(target, 'close')
                until(lambda process=process: process.poll() is not None)
                assert process.returncode == 0, process.stderr.read()
            print(json.dumps({'passed': True, 'syntheticOwnedCompositor': True, 'checks': checks}, indent=2))
        finally:
            cursor.close()
            trackball.close()
            panel.close()
            controller.close()
            output.close()
            for process in processes:
                if process.poll() is None:
                    process.terminate()
                    process.wait(timeout=5)
            windows.close()
            bus.unregisterObject(CONTROL_PATH)
            bus.unregisterService(APP_ID)
            application.restoreOverrideCursor()


if __name__ == '__main__':
    main()
