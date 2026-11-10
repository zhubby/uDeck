from types import SimpleNamespace

import pytest
from PySide6.QtCore import QCoreApplication, QObject, Signal

from udeck.controller import ShellController
from udeck.core import ConfigStore
from udeck.mock import MockBackend
from udeck.trackball import TrackballInput
from udeck.virtual_input import VirtualInput


class Pointer(QObject):
    middleButton = Signal(bool)
    middleButtonTimed = Signal(bool, float)
    motion = Signal(int, int)
    reset = Signal()


class Windows(QObject):
    changed = Signal(object)
    failed = Signal(object)

    def __init__(self):
        super().__init__()
        self.available = True
        self.rows = [{'id': '10', 'appId': 'firefox', 'active': True}]

    def entries(self):
        return self.rows


@pytest.fixture
def trackball(tmp_path):
    application = QCoreApplication.instance() or QCoreApplication([])
    pointer, windows = Pointer(), Windows()
    controller = ShellController(MockBackend(), config=ConfigStore(tmp_path / 'settings.json'), mock=True)
    output = VirtualInput()
    output.available = True
    output.pointer = 20
    events = []
    output._request = lambda *args: events.append(args)
    output._flush = lambda: None
    now = [10.0]
    pointer.middleButton.connect(lambda pressed: pointer.middleButtonTimed.emit(pressed, now[0]))
    trackball = TrackballInput(pointer, controller, windows, output, clock=lambda: now[0])
    yield SimpleNamespace(input=trackball, pointer=pointer, windows=windows, controller=controller,
                          output=output, events=events, now=now, application=application)
    trackball.close()
    output.close()
    controller.close()


def clicks(trackball):
    return [(event[-2].value, event[-1].value) for event in trackball.events if event[1] == 2]


@pytest.mark.parametrize('duration,code', [(0.05, 272), (1.999, 272), (2.0, 272), (2.001, 273), (5.0, 273)])
def test_release_classifies_click_even_when_event_loop_delays_timer(trackball, duration, code):
    trackball.pointer.middleButton.emit(True)
    assert not clicks(trackball)
    trackball.now[0] += duration
    trackball.pointer.middleButton.emit(False)
    assert clicks(trackball) == [(code, 1), (code, 0)]
    assert not trackball.output.buttons and not trackball.input.timer.isActive()


def test_long_hold_fires_once_without_left_click_or_release_click(trackball):
    trackball.pointer.middleButton.emit(True)
    trackball.now[0] += 2
    trackball.input._timeout()
    assert not clicks(trackball)  # Strictly longer than two seconds.
    trackball.now[0] += 0.001
    trackball.input._timeout()
    trackball.pointer.middleButton.emit(True)
    trackball.now[0] += 10
    trackball.input._timeout()
    trackball.pointer.middleButton.emit(False)
    trackball.pointer.middleButton.emit(False)
    assert clicks(trackball) == [(273, 1), (273, 0)]


def test_queued_device_timestamps_preserve_physical_hold_duration(trackball):
    trackball.pointer.middleButtonTimed.emit(True, trackball.now[0] - 4)
    trackball.pointer.middleButtonTimed.emit(False, trackball.now[0] - 0.1)
    assert clicks(trackball) == [(273, 1), (273, 0)]


@pytest.mark.parametrize('loss', ['reset', 'focus', 'window', 'diagnostic', 'session', 'suspend', 'protocol'])
def test_cancelled_hold_never_becomes_a_click(trackball, loss):
    trackball.pointer.middleButton.emit(True)
    if loss == 'reset':
        trackball.pointer.reset.emit()
    elif loss == 'focus':
        trackball.controller.foregroundChanged.emit(True)
    elif loss == 'window':
        trackball.windows.rows = [{'id': '11', 'appId': 'mousepad', 'active': True}]
        trackball.windows.changed.emit(trackball.windows.rows)
    elif loss == 'diagnostic':
        trackball.controller.activateSetting('key-test')
        trackball.controller.dispatch('back')
    elif loss == 'session':
        trackball.controller.backend.updated.emit({'sessionInput': {'available': True, 'active': True, 'locked': True}})
    elif loss == 'suspend':
        trackball.controller.inputSuspended.emit(True)
    else:
        trackball.output.failed.emit('disconnected')
    trackball.now[0] += 3
    trackball.input._timeout()
    trackball.pointer.middleButton.emit(False)
    assert not clicks(trackball)
    assert not trackball.input.timer.isActive()


def test_shell_uses_confirm_and_context_without_changing_page_or_injecting(trackball):
    trackball.controller.foregroundChanged.emit(True)
    trackball.controller.setPage('home')
    trackball.controller.select(0)
    trackball.pointer.middleButton.emit(True)
    trackball.pointer.middleButton.emit(False)
    assert trackball.controller.config.data['recent']
    assert trackball.controller.navigation.page == 'home'
    trackball.controller.dispatch('home')  # Finish any launch wait before the separate context gesture.
    trackball.pointer.middleButton.emit(True)
    trackball.now[0] += 2.1
    trackball.input._timeout()
    trackball.pointer.middleButton.emit(False)
    assert trackball.controller.modal['kind'] == 'menu'
    assert not clicks(trackball)


def test_diagnostic_observes_raw_edges_without_semantic_actions(trackball):
    trackball.controller.foregroundChanged.emit(True)
    trackball.pointer.middleButton.connect(lambda pressed: trackball.controller.testButton('pointer-click', pressed, 'pointer'))
    trackball.controller.activateSetting('key-test')
    trackball.pointer.middleButton.emit(True)
    assert trackball.controller.modal['pressed'] == ['pointer-click']
    trackball.now[0] += 3
    trackball.input._timeout()
    trackball.pointer.middleButton.emit(False)
    assert trackball.controller.modal['pressed'] == []
    assert trackball.controller.modal['pressCount'] == 1
    assert not clicks(trackball)


def test_trackball_motion_reaches_focused_app_and_does_not_release_gamepad_drag(trackball):
    trackball.pointer.motion.emit(0, 7)
    trackball.pointer.motion.emit(1, -3)
    trackball.pointer.motion.emit(8, 1)
    assert trackball.output.position == (647, 357)
    assert any(event[1] == 7 and event[-1].value == -1 for event in trackball.events)
    trackball.output.button(272, True)
    trackball.events.clear()
    trackball.pointer.middleButton.emit(True)
    trackball.pointer.middleButton.emit(False)
    assert not clicks(trackball)
    assert trackball.output.buttons == {272}


def test_locked_session_and_unavailable_output_do_not_queue_clicks(trackball):
    trackball.output.available = False
    trackball.pointer.middleButton.emit(True)
    trackball.output.available = True
    trackball.pointer.middleButton.emit(False)
    assert not clicks(trackball)
    trackball.controller.backend.updated.emit({'sessionInput': {'available': True, 'active': False, 'locked': False}})
    trackball.pointer.middleButton.emit(True)
    trackball.pointer.middleButton.emit(False)
    assert not clicks(trackball)
