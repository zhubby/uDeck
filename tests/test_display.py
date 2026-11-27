"""
[INPUT]: 依赖模拟的 Wayland 输出、复制进程与桌面设置。
[OUTPUT]: 验证外屏布局、热插拔及保存偏好。
[POS]: 显示设置与合成器边界的回归入口。
[PROTOCOL]: Update this header on change, then check AGENTS.md
"""

import asyncio
import json
from copy import deepcopy

import pytest

from udeck.controller import ShellController
from udeck.core import ConfigStore
from udeck.display import DisplayLayout
from udeck.mock import MockBackend


def output(name, width, height, *, transform='normal', scale=1):
    return {'name': name, 'enabled': True, 'position': {'x': 0, 'y': 0},
            'modes': [{'width': width, 'height': height, 'current': True}],
            'transform': transform, 'scale': scale}


class MirrorProcess:
    returncode = None

    def terminate(self):
        self.returncode = 0

    async def wait(self):
        return self.returncode


class Compositor:
    def __init__(self):
        self.internal = output('DSI-1', 720, 1280, transform='270')
        self.external = output('HDMI-A-1', 1920, 1080)
        self.outputs = [self.internal, self.external]
        self.mirrors = []
        self.fail_mirror = False

    async def command(self, *args, timeout):
        if args == ('wlr-randr', '--json'):
            return json.dumps(self.outputs)
        assert args[0] == 'wlr-randr' and args[1:3] == ('--output', 'HDMI-A-1')
        assert self.external in self.outputs
        if not self.external['enabled']:
            assert '--on' in args and '--preferred' not in args
        x, y = map(int, args[args.index('--pos') + 1].split(','))
        self.external.update(enabled=True, position={'x': x, 'y': y})

    async def mirror(self, *args, **kwargs):
        assert args == ('wl-mirror', '--fullscreen', '--fullscreen-output', 'HDMI-A-1', '--scaling', 'fit', 'DSI-1')
        process = MirrorProcess()
        self.mirrors.append(process)
        if self.fail_mirror:
            process.returncode = 1
        return process


def test_display_default_switch_and_hotplug():
    async def exercise():
        compositor = Compositor()
        compositor.external['enabled'] = False
        original = deepcopy(compositor.internal)
        layout = DisplayLayout(compositor.command, start_process=compositor.mirror)
        assert (await layout.refresh())['activeMode'] == 'mirror'
        assert (await layout.refresh())['activeMode'] == 'mirror'
        assert len(compositor.mirrors) == 1
        assert (await layout.select('extend'))['activeMode'] == 'extend'
        assert compositor.external['position'] == {'x': 1280, 'y': 0}
        assert compositor.mirrors[0].returncode == 0
        compositor.outputs.pop()
        assert (await layout.refresh())['outputs'] == []
        assert (await layout.select('mirror'))['mode'] == 'mirror'
        compositor.outputs.append(compositor.external)
        assert (await layout.refresh())['activeMode'] == 'mirror'
        assert compositor.internal == original
        await layout.close()
        assert compositor.mirrors[-1].returncode == 0

    asyncio.run(exercise())


def test_mirror_failure_keeps_extend_and_allows_retry():
    async def exercise():
        compositor = Compositor()
        compositor.fail_mirror = True
        layout = DisplayLayout(compositor.command, start_process=compositor.mirror)
        state = await layout.refresh()
        assert state['activeMode'] == 'extend' and state['error']
        assert compositor.external['position'] == {'x': 1280, 'y': 0}
        await layout.refresh()
        assert len(compositor.mirrors) == 1
        compositor.fail_mirror = False
        assert (await layout.select('mirror'))['activeMode'] == 'mirror'
        await layout.select('extend')
        compositor.fail_mirror = True
        with pytest.raises(RuntimeError):
            await layout.select('mirror')
        assert (await layout.refresh())['mode'] == 'extend'
        await layout.close()

    asyncio.run(exercise())


def test_save_failure_restores_previous_layout():
    def fail_to_save(mode):
        raise OSError('disk full')

    async def exercise():
        compositor = Compositor()
        layout = DisplayLayout(compositor.command, start_process=compositor.mirror)
        await layout.refresh()
        try:
            with pytest.raises(OSError, match='disk full'):
                await layout.select('extend', fail_to_save)
            assert (await layout.refresh())['activeMode'] == 'mirror'
        finally:
            await layout.close()

    asyncio.run(exercise())


def test_display_setting_persists_with_no_monitor(tmp_path):
    config = ConfigStore(tmp_path / 'settings.json')
    assert config.data['preferences']['displayMode'] == 'mirror'
    backend = MockBackend()
    backend.state['display']['outputs'] = []
    controller = ShellController(backend, config=config, mock=True)
    try:
        controller.setPage('settings')
        controller.select(next(index for index, row in enumerate(controller._items()) if row['id'] == 'display'))
        controller.dispatch('accept')
        assert controller.modal['options'][0]['current']
        controller.dispatch('down')
        controller.dispatch('accept')
        assert controller.modal['options'][1]['current']
        assert ConfigStore(config.path).data['preferences']['displayMode'] == 'extend'
    finally:
        controller.close()
