#!/usr/bin/env python3
"""
[INPUT]: 依赖指定源码、MockBackend、Qt 按键事件和只读电源查询。
[OUTPUT]: 输出电源预检、连续时间线、补位轨迹和资源门槛。
[POS]: 私有总线与临时配置中的全屏探针，不连接机身输入。
[PROTOCOL]: Update this header on change, then check AGENTS.md
"""

import argparse
import faulthandler
import hashlib
import json
import math
import os
import platform
import shutil
import signal
import statistics
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path


class PresentationRecorder:
    def __init__(self):
        self.staged = None
        self.synchronized = None
        self.frames = []

    def stage(self, sample):
        self.staged = sample

    def synchronize(self):
        self.synchronized = self.staged

    def swap(self, timestamp):
        if self.synchronized is not None:
            self.frames.append({'at': timestamp, **self.synchronized})


def summarize_ms(values):
    ordered = sorted(values)
    if not ordered:
        return {'count': 0, 'medianMs': None, 'p95Ms': None, 'p99Ms': None, 'maxMs': None}
    return {'count': len(ordered), 'medianMs': statistics.median(ordered),
            'p95Ms': ordered[math.ceil(len(ordered) * .95) - 1],
            'p99Ms': ordered[math.ceil(len(ordered) * .99) - 1], 'maxMs': ordered[-1]}


def analyze_timeline(inputs, frames, refresh_hz):
    if not math.isfinite(refresh_hz) or refresh_hz <= 0:
        raise ValueError('Refresh rate must be positive and finite')
    budget = 1000 / refresh_hz
    frames = sorted(frames, key=lambda row: row['at'])
    results = []
    for position, command in enumerate(inputs):
        deadline = command['deadline']
        superseded = next((later['started'] for later in inputs[position + 1:]
                           if later['scenario'] == command['scenario']
                           and later['expected'] != command['expected']), None)
        if superseded is not None:
            deadline = min(deadline, superseded)
        presented = next((frame for frame in frames
                          if command['started'] <= frame['stagedAt'] <= frame['at'] <= deadline
                          and frame.get('scope') == command['scenario']
                          and all(frame['state'].get(key) == value
                                  for key, value in command['expected'].items())), None)
        delivered = command.get('deliveryCompleted', True)
        status = 'presented' if presented and command.get('changed', True) and delivered else 'timeout'
        results.append({**command, 'status': status, 'supersededAt': superseded,
                        'firstPresentationMs': (presented['at'] - command['started']) * 1000
                            if status == 'presented' else None,
                        'failure': None if status == 'presented' else
                            'input-delivery-barrier-timeout' if not delivered else
                            'no-logical-change' if not command.get('changed', True) else
                            'no-matching-presented-frame-before-deadline'})
    # 上一已呈现帧仍在播放动画时，保留到下一帧的完整间隔。
    # 静止后首次输入前的等待不属于动画帧间隔。
    gaps = [(right['at'] - left['at']) * 1000 for left, right in zip(frames, frames[1:], strict=False)
            if left.get('moving') and left.get('scope') is not None
            and left.get('scope') == right.get('scope')]
    navigation = [row['firstPresentationMs'] for row in results
                  if row['status'] == 'presented' and row['kind'] == 'navigation']
    transitions = [row['firstPresentationMs'] for row in results
                   if row['status'] == 'presented' and row['kind'] != 'navigation']
    gap_stats = summarize_ms(gaps)
    nav_stats, transition_stats = summarize_ms(navigation), summarize_ms(transitions)

    def threshold(value, limit):
        return {'valueMs': value, 'limitMs': limit, 'passed': value is not None and value <= limit,
                'status': 'insufficient-data' if value is None else 'passed' if value <= limit else 'failed'}

    presented = sum(row['status'] == 'presented' for row in results)
    thresholds = {
        'activeFrameP95': threshold(gap_stats['p95Ms'], 1.25 * budget),
        'activeFrameP99': threshold(gap_stats['p99Ms'], 2 * budget),
        'activeFrameMax': threshold(gap_stats['maxMs'], 3 * budget),
        'navigationFirstP95': threshold(nav_stats['p95Ms'], 2 * budget),
        'pageModalFirstP95': threshold(transition_stats['p95Ms'], 3 * budget),
        'allInputsPresented': {'sent': len(inputs), 'presented': presented,
                               'passed': bool(inputs) and presented == len(inputs)}}
    return {'frameBudgetMs': budget,
            'inputs': {'sent': len(inputs), 'presented': presented, 'failed': len(inputs) - presented,
                       'presentationRate': presented / len(inputs) if inputs else None},
            'frames': {'continuousSwapCount': len(frames), 'activeGapCount': len(gaps),
                       'gapsOverThreeBudgets': sum(gap > 3 * budget for gap in gaps)},
            'activeFrameGapMs': gap_stats, 'navigationFirstPresentationMs': nav_stats,
            'pageModalFirstPresentationMs': transition_stats, 'activeFrameGapsMs': gaps,
            'inputResults': results, 'thresholdResults': thresholds}


def resources():
    result = {'cpuSeconds': time.process_time(), 'pssKiB': None, 'rssKiB': None}
    try:
        values = dict(line.split(':', 1) for line in
                      Path('/proc/self/smaps_rollup').read_text().splitlines() if ':' in line)
        result.update(pssKiB=int(values['Pss'].split()[0]), rssKiB=int(values['Rss'].split()[0]))
    except (OSError, ValueError, KeyError):
        pass
    return result


def idle_redraw_threshold(samples):
    return {'passed': all(row['swaps'] <= row['expectedMaximumClockSwaps'] for row in samples),
            'observedSwaps': [row['swaps'] for row in samples],
            'maximumClockSwaps': [row['expectedMaximumClockSwaps'] for row in samples]}


def trace_stage(label):
    if os.environ.get('UDECK_MOTION_TRACE') == '1':
        print(f'[motion-trace {time.perf_counter():.6f}] {label}', file=sys.stderr, flush=True)


def analyze_output_power(text, screen):
    outputs = {}
    for line in text.splitlines():
        parts = line.rsplit(None, 1)
        if len(parts) == 2 and parts[1] in ('on', 'off'):
            outputs[parts[0]] = parts[1]
    state = outputs.get(screen, 'unknown')
    if state == 'unknown' and outputs and all(value == 'off' for value in outputs.values()):
        state = 'off'
    return {'screen': screen, 'outputs': outputs, 'status': state, 'passed': state != 'off'}


def display_power_preflight(platform_name, screen):
    result = analyze_output_power('', screen)
    utility = shutil.which('wlopm') if platform_name == 'wayland' else None
    if utility:
        try:
            query = subprocess.run([utility], capture_output=True, text=True, timeout=3, check=False)
            result = analyze_output_power(query.stdout, screen)
            result['queryExitCode'] = query.returncode
        except (OSError, subprocess.TimeoutExpired) as error:
            result['queryError'] = str(error)
    return result


def run_probe(options, directory):
    trace_stage('startup imports')
    # 源码和临时路径先于产品导入生效；保留调用方的 QSG 配置。
    for key, suffix in (('XDG_CONFIG_HOME', 'config'), ('XDG_DATA_HOME', 'data'),
                        ('XDG_CACHE_HOME', 'cache'), ('XDG_STATE_HOME', 'state')):
        os.environ[key] = str(directory / suffix)
    os.environ.setdefault('QT_QUICK_CONTROLS_STYLE', 'Basic')
    sys.path.insert(0, str(options.source))
    from PySide6 import __version__ as pyside_version
    from PySide6.QtCore import (
        QCoreApplication,
        QEvent,
        QEventLoop,
        QObject,
        Qt,
        QTimer,
        QUrl,
        qVersion,
    )
    from PySide6.QtGui import QGuiApplication, QKeyEvent
    from PySide6.QtQml import QQmlApplicationEngine
    from shiboken6 import delete, getCppPointer, isValid

    from udeck import main
    from udeck.controller import ShellController
    from udeck.core import ConfigStore
    from udeck.mock import MockBackend

    trace_stage('startup application-create')
    application = QGuiApplication([])
    application.setApplicationName('uDeck motion probe ' + str(os.getpid()))
    screen = application.primaryScreen()
    power = display_power_preflight(application.platformName(), screen.name() if screen else '')
    trace_stage('startup output-power ' + json.dumps(power))
    if not power['passed']:
        return {'status': 'failed', 'source': str(options.source),
                'error': 'Probe output power is off; enable the display before measuring motion.',
                'preflight': {'displayPower': power}}
    config = ConfigStore(directory / 'settings.json')
    config.data['preferences'].update(language='en', theme=options.theme, uiSounds=False)
    trace_stage('startup controller-create')
    controller = ShellController(MockBackend(), config=config, mock=True)
    controller.data['files'] = [
        {'id': '/home/demo/Motion-' + str(index), 'path': '/home/demo/Motion-' + str(index),
         'name': f'Motion {index:02d}.txt', 'directory': False, 'icon': 'text-x-generic',
         'kind': 'text', 'mime': 'text/plain', 'size': 1024, 'sizeLabel': '1 KiB'}
        for index in range(36)]
    mock_windows = [{'id': str(index), 'appId': 'motion.' + str(index),
                     'name': f'Motion app {index:02d}', 'active': False} for index in range(12)]
    controller._windows_changed(mock_windows)
    controller.runtime_console.timer.stop()
    errors = []
    engine = QQmlApplicationEngine()
    engine.warnings.connect(lambda warnings: errors.extend(w.toString() for w in warnings))
    engine.addImageProvider('desktop', main.IconProvider())
    for key, value in (('controller', controller), ('windowedPreview', True), ('headlessPreview', True)):
        engine.rootContext().setContextProperty(key, value)
    trace_stage('startup engine-load')
    engine.load(QUrl.fromLocalFile(str(Path(main.__file__).parent / 'qml/Main.qml')))
    trace_stage('startup engine-loaded')
    if not engine.rootObjects():
        controller.close()
        raise RuntimeError('QML window failed: ' + '\n'.join(errors))
    window = engine.rootObjects()[0]
    window.setTitle(application.applicationName())
    if application.platformName() not in ('offscreen', 'minimal'):
        # Wayland 不向被正式全屏窗口遮盖的探针持续发送帧回调。
        # 仅将此独立窗口置为全屏；退出时由合成器恢复前一窗口。
        window.showFullScreen()
        window.requestActivate()

    def visual(name):
        found = window.findChild(QObject, name)
        if found is None:
            raise RuntimeError('Missing QML measurement surface: ' + name)
        return found

    surfaces = {page: visual(name) for page, name in (
        ('home', 'homeScreen'), ('apps', 'applicationGrid'), ('files', 'fileGrid'),
        ('windows', 'consoleList'))}
    modal = visual('modalShade')
    console = visual('consoleScreen')
    recorder = PresentationRecorder()
    inputs, frames, after_animations, observer_costs = [], recorder.frames, [], []
    epoch = time.perf_counter()

    class Observer:
        scope = None
        animations = []
        inventory = {}
        cached_targets = set()
        rows = []
        tracks = []

        def refresh_animations(self):
            # ListView 代理的视觉父对象与 QObject 父对象不同；合并两棵树。
            objects = list(window.findChildren(QObject))
            pending = [window.contentItem()]
            while pending:
                item = pending.pop()
                objects.append(item)
                objects.extend(item.findChildren(QObject))
                pending.extend(item.childItems())
            unique = {getCppPointer(obj)[0]: obj for obj in objects}
            self.rows = [obj for obj in unique.values() if obj.objectName().startswith('consoleRow-')]
            self.animations = [obj for obj in unique.values()
                               if 'Animation' in obj.metaObject().className()
                               and obj.metaObject().indexOfProperty('running') >= 0]
            self.cached_targets.update(obj.property('target').objectName() for obj in self.animations
                                       if obj.property('target') is not None)
            self.tracks = []
            for obj in self.animations:
                target, field = obj.property('target'), obj.property('property')
                if target is None or not field:
                    continue
                sources, parent = [obj], obj.parent()
                while parent is not None and 'Animation' in parent.metaObject().className():
                    sources.append(parent)
                    parent = parent.parent()
                self.tracks.append({'animation': obj, 'target': target, 'field': field,
                                    'runningSources': sources, 'kind': self.motion_kind(obj)})

        def visual_state(self):
            page = window.property('renderedPage')
            surface = surfaces.get(page)
            index = surface.property('index' if page == 'home' else 'currentIndex') if surface else None
            return {'page': page, 'index': index, 'modal': bool(modal.property('shown')),
                    'rowCount': int(surfaces['windows'].property('count')),
                    'exitFocused': bool(console.property('exitFocused'))}

        def moving(self, track):
            animation, target = track['animation'], track['target']
            if not isValid(animation) or not isValid(target):
                return False
            if not any(isValid(source) and source.property('running') for source in track['runningSources']):
                return False
            destination = animation.property('to')
            if not isinstance(destination, (int, float)):
                return False
            value = target.property(track['field'])
            return isinstance(value, (int, float)) and abs(value - destination) > .001

        def motion_kind(self, animation):
            target = animation.property('target')
            while target is not None:
                name = target.objectName()
                if 'Focus' in name:
                    return 'focus'
                if name in ('homeStrip', 'fileGrid', 'consoleList', 'applicationGrid'):
                    return 'scroll'
                if name.startswith('consoleRow-'):
                    return 'reflow'
                if name in ('pageContent', 'modalShade'):
                    return 'page' if name == 'pageContent' else 'modal'
                target = target.parent()
            return 'other'

        def after_animating(self):
            sample_started = time.perf_counter()
            # 此处只读真实 QML 选择；控制器的预期状态在输入记录中单独保存。
            active = [track for track in self.tracks if self.moving(track)]
            kinds = sorted({track['kind'] for track in active})
            if any(isValid(row) and abs(row.property('visualY') - row.property('y')) > .001 for row in self.rows):
                kinds = sorted(set(kinds) | {'reflow'})
            for track in active:
                obj = track['animation']
                if getCppPointer(obj)[0] not in self.inventory:
                    target = obj.property('target')
                    self.inventory[getCppPointer(obj)[0]] = {
                        'class': obj.metaObject().className(), 'target': target.objectName() if target is not None else None,
                        'parent': obj.parent().objectName() if obj.parent() is not None else None,
                        'property': obj.property('property'), 'from': str(obj.property('from')), 'to': str(obj.property('to'))}
            sample = {'stagedAt': time.perf_counter() - epoch, 'scope': self.scope,
                      'moving': bool(kinds), 'motionKinds': kinds, 'state': self.visual_state(),
                      'trackedAnimationCount': len(self.animations), 'trackedRowCount': len(self.rows)}
            if self.scope and 'console-' in self.scope:
                sample['consoleRows'] = [
                    {'name': row.objectName(), 'index': row.property('index'),
                     'y': row.property('y'), 'visualY': row.property('visualY')}
                    for row in self.rows if isValid(row)]
            recorder.stage(sample)
            after_animations.append(sample)
            observer_costs.append((time.perf_counter() - sample_started) * 1000)

        def synchronizing(self):
            recorder.synchronize()

        def swapped(self):
            # DirectConnection 在发出信号的线程取时；不从渲染线程读取 Qt 对象。
            recorder.swap(time.perf_counter() - epoch)

    observer = Observer()
    observer.refresh_animations()
    window.afterAnimating.connect(observer.after_animating)
    window.beforeSynchronizing.connect(observer.synchronizing, Qt.ConnectionType.DirectConnection)
    window.frameSwapped.connect(observer.swapped, Qt.ConnectionType.DirectConnection)
    trace_stage('startup observers-connected')

    def wait(milliseconds):
        # qWait 持有 GIL 等待渲染；渲染线程的 Python 信号槽需获取 GIL。
        # Qt 事件循环在等待时释放 GIL，让同步和呈现槽完成。
        loop = QEventLoop()
        timer = QTimer()
        timer.setSingleShot(True)
        timer.setTimerType(Qt.TimerType.PreciseTimer)
        timer.timeout.connect(loop.quit)
        timer.start(max(1, math.ceil(milliseconds)))
        loop.exec()

    def wait_until(predicate, seconds=3):
        deadline = time.perf_counter() + seconds
        while not predicate() and time.perf_counter() < deadline:
            wait(5)
        if not predicate():
            raise TimeoutError('Probe window did not reach its setup state')

    def logical_state():
        return {'page': controller.navigation.page, 'index': controller.navigation.index,
                'modal': bool(controller.modal), 'rowCount': controller.consoleModel.rowCount(),
                'exitFocused': bool(controller.console_exit_focused)}

    class InputBarrier(QObject):
        event_type = QEvent.Type(QEvent.registerEventType())
        loop = None
        completed = False

        def eventFilter(self, target, event):
            if target is window and event.type() == self.event_type:
                self.completed = True
                self.loop.quit()
                return True
            return False

    barrier = InputBarrier()
    window.installEventFilter(barrier)

    def key_click(key):
        # 相同接收者、相同优先级的事件按投递顺序处理。
        # 屏障确认 press/release 已经过窗口事件路径，不同步调用 qWait。
        loop = QEventLoop()
        timeout = QTimer()
        timeout.setSingleShot(True)
        timeout.setTimerType(Qt.TimerType.PreciseTimer)
        timeout.timeout.connect(loop.quit)
        barrier.loop, barrier.completed = loop, False
        for event_type in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
            QCoreApplication.postEvent(window, QKeyEvent(event_type, key, Qt.KeyboardModifier.NoModifier))
        QCoreApplication.postEvent(window, QEvent(barrier.event_type))
        timeout.start(max(1, int(options.timeout * 1000)))
        loop.exec()
        timeout.stop()
        return barrier.completed

    def idle_sample():
        trace_stage('idle begin')
        observer.scope = None
        wait(400)
        started, first = time.perf_counter(), resources()
        swaps = len(frames)
        wait(options.idle_seconds * 1000)
        elapsed, last = time.perf_counter() - started, resources()
        trace_stage('idle end')
        return {'startedAt': started - epoch, 'endedAt': time.perf_counter() - epoch,
                'seconds': elapsed, 'before': first, 'after': last,
                'cpuPercentOneCore': (last['cpuSeconds'] - first['cpuSeconds']) / elapsed * 100,
                'swaps': len(frames) - swaps,
                'expectedMaximumClockSwaps': math.ceil(options.idle_seconds * 3) + 2}

    def prepare(page, index=0, reset_console=False):
        trace_stage(f'setup begin {page} index={index} active={window.isActive()} '
                    f'exposed={window.isExposed()} visible={window.isVisible()}')
        observer.scope = None
        if reset_console:
            controller._windows_changed(mock_windows)
        controller.setPage(page)
        controller.select(index)
        controller.runtime_console.timer.stop()
        observer.refresh_animations()
        wait(400)
        wait_until(lambda: window.property('renderedPage') == page)
        trace_stage(f'setup end {page}')

    keymap = {'left': Qt.Key_Left, 'right': Qt.Key_Right, 'up': Qt.Key_Up, 'down': Qt.Key_Down,
              'next-page': Qt.Key_PageDown, 'previous-page': Qt.Key_PageUp,
              'modal-open': Qt.Key_F1, 'modal-close': Qt.Key_Escape, 'accept': Qt.Key_Return}
    scenarios = []
    measurement_started = None

    def sequence(name, actions, interval_ms, kind='navigation'):
        trace_stage('sequence begin ' + name)
        if application.platformName() not in ('offscreen', 'minimal') and not window.isExposed():
            raise RuntimeError('Independent probe is not exposed; check output power and foreground.')
        if time.perf_counter() - measurement_started >= options.duration:
            return False
        observer.scope = name
        observer.refresh_animations()
        due = time.perf_counter()
        previous_started = None
        scenario_start = len(inputs)
        for action in actions:
            while time.perf_counter() < due:
                wait(min(4, (due - time.perf_counter()) * 1000))
            if time.perf_counter() - measurement_started >= options.duration:
                scenarios.append({'name': name, 'planned': len(actions),
                                  'sent': len(inputs) - scenario_start, 'complete': False})
                return False
            before = logical_state()
            started = time.perf_counter() - epoch
            command = {'id': len(inputs), 'scenario': name, 'kind': kind, 'action': action,
                           'inputMethod': 'QCoreApplication.postEvent(QKeyEvent)',
                           'started': started, 'deadline': started + options.timeout,
                           'expected': before, 'changed': False, 'deliveryCompleted': False,
                           'intendedIntervalMs': interval_ms,
                           'scheduledAt': due - epoch,
                           'actualIntervalMs': (started - previous_started) * 1000
                                if previous_started is not None else None,
                           'scheduleDelayMs': max(0, (epoch + started - due) * 1000)}
            inputs.append(command)
            delivered = key_click(keymap[action])
            expected = logical_state()
            command.update(expected=expected, changed=before != expected, deliveryCompleted=delivered)
            previous_started = started
            # 迟到后不追赶；每次实际发送之间保留目标最小间隔。
            due = epoch + started + interval_ms / 1000
        wait(max(400, options.timeout * 1000))
        scenarios.append({'name': name, 'planned': len(actions),
                          'sent': len(inputs) - scenario_start, 'complete': True})
        observer.scope = None
        trace_stage('sequence end ' + name)
        return True

    before = resources()
    report = {}
    try:
        trace_stage('startup first-frame-wait')
        wait_until(lambda: len(frames) > 0, 5)
        trace_stage(f'startup first-frame-received active={window.isActive()} '
                    f'exposed={window.isExposed()} visible={window.isVisible()}')
        warmup_started, warmup_swaps = time.perf_counter(), len(frames)
        wait(options.warmup_seconds * 1000)
        startup_warmup = {'requestedSeconds': options.warmup_seconds,
                          'seconds': time.perf_counter() - warmup_started,
                          'swaps': len(frames) - warmup_swaps}
        idle_before = idle_sample()
        measurement_started = time.perf_counter()
        before = resources()
        completed = True
        for cycle in range(options.rounds):
            prefix = str(cycle) + ':'
            prepare('home', 0)
            if not sequence(prefix + 'home-boundary', ['right'] * 6 + ['left'] * 6, 120):
                completed = False
                break
            prepare('files', 0)
            if not sequence(prefix + 'files-scroll', ['down'] * 4 + ['up'] * 4 + ['right', 'left'], 120):
                completed = False
                break
            prepare('windows', 0, reset_console=True)
            if not sequence(prefix + 'console-scroll', ['down'] * 8 + ['up'] * 8, 120):
                completed = False
                break
            prepare('windows', 2, reset_console=True)
            if not sequence(prefix + 'console-reflow', ['right', 'accept'] * 3, 180, 'structure'):
                completed = False
                break
            for interval in (20, 50, 90):
                prepare('home', 3)
                if not sequence(prefix + f'rapid-reversal-{interval}ms', ['right', 'left'] * 6, interval):
                    completed = False
                    break
            if not completed:
                break
            prepare('home', 0)
            if not sequence(prefix + 'pages', ['next-page'] * 3 + ['previous-page'] * 3, 90, 'page'):
                completed = False
                break
            prepare('home', 0)
            if not sequence(prefix + 'modal', ['modal-open', 'modal-close'] * 3, 180, 'modal'):
                completed = False
                break
        elapsed = time.perf_counter() - measurement_started
        after = resources()
        idle_after = idle_sample()
        refresh_rate = float(window.screen().refreshRate())
        analysis = analyze_timeline(inputs, frames, refresh_rate)
        graphics_api = window.rendererInterface().graphicsApi()
        eligible = application.platformName() not in ('offscreen', 'minimal')
        analysis['thresholdResults']['coverageComplete'] = {'passed': completed, 'rounds': options.rounds}
        analysis['thresholdResults']['realDisplay'] = {'passed': eligible, 'platform': application.platformName()}
        analysis['thresholdResults']['qmlErrors'] = {'passed': not errors, 'count': len(errors)}
        idle_redraw = idle_redraw_threshold([idle_before, idle_after])
        analysis['thresholdResults']['idleNoContinuousRedraw'] = idle_redraw
        report = {'status': 'passed' if all(row['passed'] for row in analysis['thresholdResults'].values()) else 'failed',
                  'source': str(options.source), 'loadedModule': str(main.__file__),
                  'sourceSha256': {str(path.relative_to(options.source)): hashlib.sha256(path.read_bytes()).hexdigest()
                                   for path in sorted((options.source / 'udeck/qml').glob('*.qml'))},
                  'host': {'platform': platform.platform(), 'machine': platform.machine(), 'python': sys.version},
                  'qt': {'version': qVersion(), 'pysideVersion': pyside_version,
                         'platform': application.platformName(), 'graphicsApi': graphics_api.name,
                         'refreshRateHz': refresh_rate, 'windowSize': [window.width(), window.height()],
                         'environment': {key: os.environ.get(key) for key in (
                             'QT_QPA_PLATFORM', 'QT_QUICK_BACKEND', 'QSG_RHI_BACKEND', 'QSG_RENDER_LOOP',
                             'LIBGL_ALWAYS_SOFTWARE', 'UDECK_REDUCED_MOTION', 'QT_QUICK_CONTROLS_STYLE')}},
                  'isolation': {'mockBackend': True, 'privateDbus': True, 'temporaryXdg': True,
                                'hardwareInputOpened': False, 'productionProcessInjection': False},
                  'preflight': {'displayPower': power, 'windowExposedAtEnd': window.isExposed()},
                  'startupWarmup': startup_warmup,
                  'durationSeconds': elapsed, 'resources': {'before': before, 'after': after,
                      'cpuPercentOneCore': (after['cpuSeconds'] - before['cpuSeconds']) / elapsed * 100},
                  'idle': {'before': idle_before, 'after': idle_after,
                           'cpuPercentOneCoreGrowth': idle_after['cpuPercentOneCore'] - idle_before['cpuPercentOneCore'],
                           'pssGrowthKiB': (idle_after['after']['pssKiB'] - idle_before['after']['pssKiB'])
                              if idle_after['after']['pssKiB'] is not None and idle_before['after']['pssKiB'] is not None else None,
                           'continuousRedrawDetected': not idle_redraw['passed']},
                  'scenarios': scenarios, 'qmlErrors': errors, **analysis,
                  'animationTracking': {'cachedObjects': len(observer.animations),
                                        'cachedNumericTracks': len(observer.tracks),
                                        'cachedRows': len(observer.rows),
                                        'cachedTargets': sorted(observer.cached_targets),
                                        'runningInventory': list(observer.inventory.values()),
                                        'activeSamples': sum(row['moving'] for row in after_animations),
                                        'samplesByKind': {kind: sum(kind in row['motionKinds'] for row in after_animations)
                                                          for kind in ('focus', 'scroll', 'reflow', 'page', 'modal', 'other')},
                                        'observerCostMs': summarize_ms(observer_costs),
                                        'definition': 'Running numeric animations whose target value differs from destination, or Console rows whose visualY differs from y'},
                  'timeline': {'clock': 'perf_counter seconds since observer attachment',
                               'frameSwapped': frames, 'afterAnimating': after_animations},
                  'limits': ['Synthetic Qt key events reach this independent window only; a FIFO barrier confirms delivery.',
                             'beforeSynchronizing latches the afterAnimating state for its render frame before frameSwapped.',
                             'Signal timestamps do not measure physical-key or optical latency.',
                             'First-presentation percentiles describe successes; every missing frame remains a failure.',
                             'Active gaps start at a presented frame whose numeric Qt animation has not reached its target; idle waits are excluded.',
                             'No requestUpdate or forced rendering is used. cProfile is not enabled.']}
    except Exception as error:
        report = {'status': 'failed', 'error': str(error), 'traceback': traceback.format_exc(),
                  'source': str(options.source), 'scenarios': scenarios, 'qmlErrors': errors,
                  'preflight': {'displayPower': power, 'windowExposedAtEnd': window.isExposed()},
                  **analyze_timeline(inputs, frames, float(window.screen().refreshRate())),
                  'timeline': {'frameSwapped': frames, 'afterAnimating': after_animations}}
    finally:
        trace_stage('cleanup observers-disconnect')
        window.frameSwapped.disconnect(observer.swapped)
        window.beforeSynchronizing.disconnect(observer.synchronizing)
        window.afterAnimating.disconnect(observer.after_animating)
        trace_stage('cleanup engine-delete')
        delete(engine)
        trace_stage('cleanup controller-close')
        controller.close()
        trace_stage('cleanup process-events')
        application.processEvents()
        trace_stage('cleanup done')
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description='Measure isolated Qt motion without opening input devices.')
    parser.add_argument('--source', type=Path, default=Path(__file__).resolve().parents[1] / 'src',
                        help='Source directory containing udeck; use baseline/src for comparison')
    parser.add_argument('--output', type=Path, required=True, help='New JSON report path')
    parser.add_argument('--duration', type=float, default=60, help='Maximum scheduling duration in seconds')
    parser.add_argument('--rounds', '--cycles', type=int, default=1, dest='rounds')
    parser.add_argument('--timeout', type=float, default=.5, help='First-presentation timeout in seconds')
    parser.add_argument('--idle-seconds', type=float, default=3, help='Equal idle resource windows before and after actions')
    parser.add_argument('--warmup-seconds', type=float, default=5, help='Fixed startup warmup before the first idle window')
    parser.add_argument('--theme', choices=('classic', 'dark'), default='classic')
    parser.add_argument('--private-bus-child', action='store_true', help=argparse.SUPPRESS)
    options = parser.parse_args(argv)
    if (not math.isfinite(options.duration) or not 0 < options.duration <= 600
            or not 1 <= options.rounds <= 1000 or not math.isfinite(options.timeout)
            or not 0 < options.timeout <= 5 or not math.isfinite(options.idle_seconds)
            or not 0 < options.idle_seconds <= 60 or not math.isfinite(options.warmup_seconds)
            or not 0 < options.warmup_seconds <= 60):
        parser.error('Use duration in (0, 600], rounds in [1, 1000], timeout in (0, 5], idle/warmup-seconds in (0, 60]')
    options.source = options.source.resolve()
    options.output = options.output.resolve()
    if not (options.source / 'udeck/qml/Main.qml').is_file():
        parser.error('--source must contain udeck/qml/Main.qml')
    if options.output.exists():
        parser.error('Use a new output path; existing evidence is never overwritten')
    if not options.private_bus_child:
        runner = shutil.which('dbus-run-session')
        if not runner:
            parser.error('dbus-run-session is required for an isolated session bus')
        with tempfile.TemporaryDirectory(prefix='udeck-motion-bus-', dir='/tmp') as temporary:
            config = Path(temporary) / 'bus.conf'
            config.write_text('<busconfig><type>session</type><listen>unix:tmpdir=' + temporary
                + '</listen><auth>EXTERNAL</auth><policy context="default">'
                '<allow send_destination="*"/><allow receive_sender="*"/><allow own="*"/>'
                '</policy></busconfig>\n')
            command = [runner, '--config-file=' + str(config), '--', sys.executable,
                       str(Path(__file__).resolve()), '--source', str(options.source),
                       '--output', str(options.output), '--duration', str(options.duration),
                       '--rounds', str(options.rounds), '--timeout', str(options.timeout),
                       '--idle-seconds', str(options.idle_seconds), '--warmup-seconds', str(options.warmup_seconds),
                       '--theme', options.theme, '--private-bus-child']
            with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  text=True, start_new_session=True) as process:
                watchdog = False
                try:
                    stdout, stderr = process.communicate(timeout=options.duration + options.warmup_seconds
                                                         + options.idle_seconds * 2 + 45)
                except subprocess.TimeoutExpired:
                    watchdog = True
                    os.killpg(process.pid, signal.SIGTERM)
                    try:
                        stdout, stderr = process.communicate(timeout=3)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid, signal.SIGKILL)
                        stdout, stderr = process.communicate(timeout=3)
                returncode = process.returncode
        if options.output.exists():
            report = json.loads(options.output.read_text())
        else:
            report = {'status': 'failed', 'error': 'Private probe exited before producing a report'}
        if watchdog:
            report.update(status='failed', error='Independent probe exceeded its wall-time watchdog')
        report['launcher'] = {'exitCode': returncode, 'stdout': stdout, 'stderr': stderr,
                              'watchdogExpired': watchdog}
        options.output.parent.mkdir(parents=True, exist_ok=True)
        options.output.write_text(json.dumps(report, indent=2) + '\n')
        print(stdout, end='')
        if stderr:
            print(stderr, file=sys.stderr, end='')
        return returncode if returncode else 1 if report['status'] != 'passed' else 0
    if not os.environ.get('DBUS_SESSION_BUS_ADDRESS'):
        parser.error('The child requires its private session bus')
    diagnostic_trace = os.environ.get('UDECK_MOTION_TRACE') == '1'
    if diagnostic_trace:
        faulthandler.enable(file=sys.stderr, all_threads=True)
        faulthandler.dump_traceback_later(15, repeat=True, file=sys.stderr)
    trace_stage('private-bus-child start')
    report = None
    try:
        with tempfile.TemporaryDirectory(prefix='udeck-motion-') as temporary:
            report = run_probe(options, Path(temporary))
    except Exception as error:
        report = {'status': 'failed', 'source': str(options.source), 'error': str(error),
                  'traceback': traceback.format_exc()}
    finally:
        if diagnostic_trace:
            faulthandler.cancel_dump_traceback_later()
    report['diagnostics'] = {'traceEnabled': diagnostic_trace,
                             'tracebackIntervalSeconds': 15 if diagnostic_trace else None}
    trace_stage('report write')
    options.output.parent.mkdir(parents=True, exist_ok=True)
    options.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'status': report['status'], 'output': str(options.output),
                      'inputs': report.get('inputs'), 'thresholdResults': report.get('thresholdResults'),
                      'error': report.get('error')}), flush=True)
    return 0 if report['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
