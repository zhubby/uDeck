"""
[INPUT]: 依赖方向读取器、临时设备身份与受控按键报告。
[OUTPUT]: 验证连接筛选、启动按住隔离与修饰键释放。
[POS]: 桌面方向输入边界的回归入口。
[PROTOCOL]: Update this header on change, then check AGENTS.md
"""

import os
import sys
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QCoreApplication

from udeck.directions import DirectionReader


@pytest.fixture
def input_device(monkeypatch, tmp_path):
    application = QCoreApplication.instance() or QCoreApplication([])
    descriptor, writer = os.pipe()
    closed, opened = [], []
    device = SimpleNamespace(name='ClockworkPI uConsole Keyboard', uniq='20230713', fd=descriptor,
                             info=SimpleNamespace(vendor=0x1eaf, product=0x0024),
                             active_keys=lambda: [106], close=lambda: closed.append(True))
    monkeypatch.setitem(sys.modules, 'evdev', SimpleNamespace(
        list_devices=lambda: ['/dev/input/event4', '/dev/input/event5'],
        InputDevice=lambda path: opened.append(path) or device))
    reader = DirectionReader()
    reader.sysfs_root = tmp_path
    yield application, reader, opened, closed
    reader.close()
    os.close(descriptor)
    os.close(writer)


def test_connect_never_opens_known_unrelated_interfaces(input_device):
    _, reader, opened, _ = input_device
    for index, name in [(4, 'ClockworkPI uConsole Mouse'), (5, 'ClockworkPI uConsole Keyboard')]:
        folder = reader.sysfs_root / f'event{index}/device'
        (folder / 'id').mkdir(parents=True)
        (folder / 'id/vendor').write_text('1eaf')
        (folder / 'id/product').write_text('0024')
        (folder / 'name').write_text(name)
    reader._connect()
    assert opened == ['/dev/input/event5'] and reader.available


def test_unreadable_identity_uses_evdev_and_inherited_arrow_waits_for_release(input_device):
    _, reader, opened, _ = input_device
    events = []
    reader.direction.connect(lambda *event: events.append(event))
    reader._connect()
    assert opened == ['/dev/input/event4'] and reader.available
    reader.feed(106, 1)
    reader.feed(106, 2)
    assert not events
    reader.feed(106, 0)
    reader.feed(106, 1)
    assert events == [('right', False), ('right', True)]


def test_direction_reader_ignores_modified_arrows_and_waits_for_release():
    application = QCoreApplication.instance() or QCoreApplication([])
    reader = DirectionReader()
    events = []
    reader.direction.connect(lambda action, pressed: events.append((action, pressed)))
    reader.feed(106, 1)
    reader.feed(29, 1)
    reader.feed(106, 2)
    reader.feed(29, 0)
    reader.feed(106, 2)
    reader.feed(106, 0)
    reader.feed(106, 1)
    assert events == [('right', True), ('right', False), ('right', False), ('right', True)]
    reader.close()
    assert application


def test_direction_reader_does_not_treat_letters_as_buttons():
    application = QCoreApplication.instance() or QCoreApplication([])
    reader = DirectionReader()
    events = []
    reader.direction.connect(lambda *arguments: events.append(arguments))
    for code in (30, 36, 37, 23):
        reader.feed(code, 1)
    assert not events
    reader.close()
    assert application
