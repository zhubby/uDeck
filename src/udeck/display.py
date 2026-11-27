"""
[INPUT]: 依赖独立 labwc 会话、wlr-randr 输出状态与 wl-mirror 进程。
[OUTPUT]: 应用并读回 Micro-HDMI 布局，报告已选模式、活动模式与连接状态。
[POS]: 显示布局服务；仅配置 HDMI，内屏始终是复制源。
[PROTOCOL]: Update this header on change, then check AGENTS.md
"""

import asyncio
import json
from contextlib import suppress

from .i18n import Msg, tr

DISPLAY_MODES = ('mirror', 'extend')
INTERNAL_OUTPUT = 'DSI-1'
EXTERNAL_OUTPUT_PREFIX = 'HDMI-A-'
# 复制屏与内屏隔开，避免相对鼠标移动进入复制窗口。
MIRROR_GAP = 4096
ROTATED = {'90', '270', 'flipped-90', 'flipped-270'}


def _external_position(internal, mode):
    current = next((entry for entry in internal['modes'] if entry.get('current')), None)
    if current is None:
        raise RuntimeError(tr(Msg.DISPLAY_LAYOUT_UNAVAILABLE))
    width = current['height'] if internal['transform'] in ROTATED else current['width']
    position = internal['position']
    gap = MIRROR_GAP if mode == 'mirror' else 0
    return {'x': position['x'] + int(width / internal['scale']) + gap, 'y': position['y']}


class DisplayLayout:
    def __init__(self, command, mode='mirror', *, start_process=asyncio.create_subprocess_exec):
        self.command = command
        self.mode = mode
        self.start_process = start_process
        self.lock = asyncio.Lock()
        self.mirror = None
        self.target = None
        self.failed_target = None

    async def _outputs(self):
        return json.loads(await self.command('wlr-randr', '--json', timeout=4))

    async def _configure(self, external, position):
        if external['enabled'] and external.get('position') == position:
            return
        name = external['name']
        arguments = () if external['enabled'] else ('--on',)
        coordinates = f"{position['x']},{position['y']}"
        await self.command('wlr-randr', '--output', name, *arguments, '--pos', coordinates, timeout=4)
        observed = next((output for output in await self._outputs() if output['name'] == name), {})
        if not observed.get('enabled') or observed.get('position') != position:
            raise RuntimeError(tr(Msg.DISPLAY_LAYOUT_UNAVAILABLE))

    async def _stop_mirror(self):
        process, self.mirror = self.mirror, None
        self.target = None
        if process is None or process.returncode is not None:
            return
        with suppress(ProcessLookupError):
            process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=1)
        except TimeoutError:
            with suppress(ProcessLookupError):
                process.kill()
            await process.wait()

    async def _start_mirror(self, name):
        self.mirror = await self.start_process(
            'wl-mirror', '--fullscreen', '--fullscreen-output', name,
            '--scaling', 'fit', INTERNAL_OUTPUT,
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
        )
        self.target = name
        await asyncio.sleep(0.4)
        if self.mirror.returncode is not None:
            raise RuntimeError(tr(Msg.DISPLAY_MIRROR_FAILED))

    async def _apply(self, mode, *, retry=False):
        outputs = await self._outputs()
        internal = next((output for output in outputs if output['name'] == INTERNAL_OUTPUT and output['enabled']), None)
        external = next((output for output in outputs if output['name'].startswith(EXTERNAL_OUTPUT_PREFIX)), None)
        state = {'available': internal is not None, 'mode': mode, 'activeMode': '', 'outputs': []}
        if external is None or internal is None:
            await self._stop_mirror()
            self.failed_target = None
            return state

        name = external['name']
        state['outputs'] = [external.get('model') or name]
        position = _external_position(internal, mode)
        if mode == 'extend':
            await self._configure(external, position)
            await self._stop_mirror()
            self.failed_target = None
            return {**state, 'activeMode': 'extend'}

        try:
            if retry or self.failed_target != name:
                await self._configure(external, position)
                if self.target != name:
                    await self._stop_mirror()
                    await self._start_mirror(name)
                if self.mirror.returncode is None:
                    self.failed_target = None
                    return {**state, 'activeMode': 'mirror'}
        except (OSError, RuntimeError):
            pass
        self.failed_target = name
        await self._stop_mirror()
        # 重新读取位置，避免使用启动复制前的快照跳过回退。
        observed = next((output for output in await self._outputs() if output['name'] == name), None)
        if observed is None:
            self.failed_target = None
            return {**state, 'outputs': []}
        await self._configure(observed, _external_position(internal, 'extend'))
        return {**state, 'activeMode': 'extend', 'error': tr(Msg.DISPLAY_MIRROR_FAILED)}

    async def refresh(self):
        async with self.lock:
            return await self._apply(self.mode)

    async def select(self, mode, save=None):
        if mode not in DISPLAY_MODES:
            raise ValueError(tr(Msg.DISPLAY_LAYOUT_UNAVAILABLE))
        async with self.lock:
            try:
                state = await self._apply(mode, retry=True)
                if not state['available']:
                    raise RuntimeError(tr(Msg.DISPLAY_LAYOUT_UNAVAILABLE))
                if state.get('error'):
                    raise RuntimeError(state['error'])
                if save is not None:
                    save(mode)
            except (OSError, RuntimeError, ValueError):
                with suppress(OSError, RuntimeError, ValueError):
                    await self._apply(self.mode)
                raise
            self.mode = mode
            return state

    async def close(self):
        async with self.lock:
            await self._stop_mirror()
