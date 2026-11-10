#!/usr/bin/env python3
"""Measure private application instances on the current compositor and a private bus.

The tool creates its own D-Bus session. XDG state is isolated below --output;
existing application processes and user data are never reused or closed.
"""

import argparse
import ast
import contextlib
import hashlib
import json
import math
import os
import platform
import signal
import statistics
import subprocess
import sys
import time
from pathlib import Path


def call(app, method, *arguments):
    identifier = 'io.github.zhubby.uDeck.' + app.title()
    identity = ('wayland:' + os.environ['WAYLAND_DISPLAY'] if os.environ.get('WAYLAND_DISPLAY')
                else 'x11:' + os.environ['DISPLAY'] if os.environ.get('DISPLAY')
                else 'session:' + os.environ.get('XDG_SESSION_ID', 'headless'))
    service = identifier + '.Session_' + hashlib.sha256(identity.encode()).hexdigest()[:16]
    result = subprocess.run(['gdbus', 'call', '--session', '--dest', service,
                             '--object-path', '/' + identifier.replace('.', '/'),
                             '--method', identifier + '.Control.' + method, *arguments],
                            capture_output=True, text=True, timeout=5)
    if result.returncode:
        raise RuntimeError(result.stderr.strip())
    return ast.literal_eval(result.stdout)[0]


def resources(pid):
    processes = {}
    for path in Path('/proc').glob('[0-9]*'):
        try:
            fields = (path / 'stat').read_text().rsplit(')', 1)[1].split()
            processes[int(path.name)] = (int(fields[1]), path, fields)
        except (OSError, ValueError, IndexError):
            pass
    owned = {pid}
    while True:
        children = {p for p, (parent, *_rest) in processes.items() if parent in owned}
        if children <= owned:
            break
        owned |= children
    result = {'processCount': len(owned), 'pssKiB': 0, 'swapPssKiB': 0, 'cpuTicks': 0,
              'majorFaults': 0, 'readBytes': 0, 'writeBytes': 0, 'pssReadableProcesses': 0}
    for child in owned:
        if child not in processes:
            continue
        _parent, path, fields = processes[child]
        result['cpuTicks'] += int(fields[11]) + int(fields[12])
        result['majorFaults'] += int(fields[9])
        try:
            values = dict(line.split(':', 1) for line in (path / 'smaps_rollup').read_text().splitlines() if ':' in line)
            result['pssKiB'] += int(values.get('Pss', '0').split()[0])
            result['swapPssKiB'] += int(values.get('SwapPss', '0').split()[0])
            result['pssReadableProcesses'] += 1
        except (OSError, ValueError):
            pass
        try:
            values = dict(line.split(':', 1) for line in (path / 'io').read_text().splitlines())
            result['readBytes'] += int(values['read_bytes'])
            result['writeBytes'] += int(values['write_bytes'])
        except (OSError, ValueError, KeyError):
            pass
    return result


def system_resources():
    memory = dict(line.split(':', 1) for line in Path('/proc/meminfo').read_text().splitlines())
    cpu = [int(value) for value in Path('/proc/stat').read_text().splitlines()[0].split()[1:]]
    virtual = dict(line.split() for line in Path('/proc/vmstat').read_text().splitlines())
    return {'loadAverage': list(os.getloadavg()), 'cpuTicks': sum(cpu[:8]), 'ioWaitTicks': cpu[4],
            'swapInPages': int(virtual['pswpin']), 'swapOutPages': int(virtual['pswpout']),
            'memoryKiB': {key: int(memory[key].split()[0]) for key in
                          ('MemTotal', 'MemAvailable', 'SwapTotal', 'SwapFree')},
            'pressure': {kind: path.read_text().strip() for kind in ('cpu', 'io', 'memory')
                         if (path := Path('/proc/pressure') / kind).exists()}}


def wait_activation(app, generation):
    deadline = time.monotonic() + .5
    active_at = None
    while True:
        performance = json.loads(call(app, 'Diagnose')).get('performance', {})
        activation = performance.get('activation', {})
        if activation.get('generation', 0) > generation and activation.get('toFrameMs') is not None:
            return performance
        if activation.get('generation', 0) > generation and activation.get('toActiveMs') is not None:
            active_at = active_at or time.monotonic()
            if time.monotonic() - active_at >= .05:
                return performance
        if time.monotonic() > deadline:
            return performance if activation.get('generation', 0) > generation else {}
        time.sleep(.01)


def activation_latency(performance, started, stage):
    activation = performance.get('activation', {})
    if activation.get(stage) is None or 'startedAtMonotonic' not in performance:
        return None
    return ((performance['startedAtMonotonic'] + activation['requestedAt'] - started) * 1000
            + activation[stage])


def summary(samples):
    if not samples:
        return None
    values = sorted(samples)
    return {'count': len(values), 'medianMs': round(statistics.median(values), 3),
            'p95Ms': round(values[math.ceil(len(values) * .95) - 1], 3),
            'minMs': round(values[0], 3), 'maxMs': round(values[-1], 3)}


@contextlib.contextmanager
def activation_bridge(options):
    if not options.wayland_window_token:
        yield
        return
    ready = options.output / 'activation-bridge-ready.json'
    with (options.output / 'activation-bridge.log').open('w') as log:
        bridge = subprocess.Popen([sys.executable,
            str(Path(__file__).with_name('performance-wayland-bridge.py')),
            '--token', options.wayland_window_token, '--ready', str(ready)], stdout=log, stderr=log)
        try:
            deadline = time.monotonic() + 10
            while not ready.exists():
                if bridge.poll() is not None or time.monotonic() >= deadline:
                    raise RuntimeError('Private Wayland activation bridge did not start; see activation-bridge.log')
                time.sleep(.02)
            yield
        finally:
            if bridge.poll() is None:
                bridge.terminate()
            try:
                bridge.wait(timeout=5)
            except subprocess.TimeoutExpired:
                bridge.kill()
                bridge.wait(timeout=5)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--apps', nargs='+', default=['music', 'video', 'reader', 'browser', 'emulator', 'terminal'])
    parser.add_argument('--repeats', type=int, default=10)
    parser.add_argument('--cold-runs', type=int, default=3)
    parser.add_argument('--sample-seconds', type=float, default=2)
    parser.add_argument('--warm-mode', choices=('minimized', 'visible'), default='minimized')
    parser.add_argument('--wayland-window-token', help='Private activation bridge; requires uniquely tagged test window titles')
    parser.add_argument('--private-bus-child', action='store_true', help=argparse.SUPPRESS)
    options = parser.parse_args()
    if options.repeats < 1 or options.cold_runs < 1 or options.sample_seconds <= 0:
        parser.error('Run counts and sample duration must be positive')
    if not options.private_bus_child:
        return subprocess.call(['dbus-run-session', '--', sys.executable, str(Path(__file__).resolve()),
                                *sys.argv[1:], '--private-bus-child'])
    if not os.environ.get('DBUS_SESSION_BUS_ADDRESS'):
        parser.error('A private session bus is required')
    if options.output.exists() and any(options.output.iterdir()):
        parser.error('Use an empty output directory to keep each measurement independent')
    options.output.mkdir(parents=True, exist_ok=True)
    with activation_bridge(options):
        measure(options)


def measure(options):
    report = {'mode': 'new process with existing OS caches; private D-Bus and XDG state',
              'host': platform.node(), 'kernel': platform.release(), 'architecture': platform.machine(),
              'python': sys.version, 'graphicsEnvironment': {key: os.environ.get(key) for key in
                  ('WAYLAND_DISPLAY', 'DISPLAY', 'QT_QPA_PLATFORM', 'QT_QUICK_BACKEND',
                   'QSG_RHI_BACKEND', 'LIBGL_ALWAYS_SOFTWARE')},
              'privateWaylandActivationBridge': bool(options.wayland_window_token),
              'systemBefore': system_resources(), 'apps': {}}
    for app in options.apps:
        runs = []
        for run in range(options.cold_runs):
            directory = options.output / app / str(run)
            directory.mkdir(parents=True, exist_ok=True)
            env = {**os.environ, 'XDG_CONFIG_HOME': str(directory / 'config'),
                   'XDG_DATA_HOME': str(directory / 'data'), 'XDG_CACHE_HOME': str(directory / 'cache')}
            command = [sys.executable, '-m', 'udeck.terminal.main' if app == 'terminal' else 'udeck.apps.main']
            if app != 'terminal':
                command.append(app)
            command.extend(['--no-input', '--windowed'])
            before = time.monotonic()
            with (directory / 'application.log').open('w') as log:
                lifetime = 60 + options.sample_seconds + options.repeats * 20
                process = subprocess.Popen([*command, '--quit-after', str(lifetime)], env=env,
                                           stdout=log, stderr=log, start_new_session=True)
                try:
                    while True:
                        try:
                            diagnosed = json.loads(call(app, 'Diagnose'))
                            if diagnosed.get('performance', {}).get('stages', {}).get('firstFrame'):
                                break
                        except RuntimeError:
                            pass
                        if process.poll() is not None or time.monotonic() - before > 30:
                            raise RuntimeError((directory / 'application.log').read_text()[-4000:])
                        time.sleep(.02)
                    first = {'observedFirstFrameMs': round((time.monotonic() - before) * 1000, 3),
                             'warmMode': options.warm_mode if app != 'terminal' else 'visible',
                             'performance': diagnosed['performance']}
                    time.sleep(.3)
                    sampled_at = time.monotonic()
                    sampled = resources(process.pid)
                    system = system_resources()
                    time.sleep(options.sample_seconds)
                    elapsed = time.monotonic() - sampled_at
                    current = resources(process.pid)
                    after = system_resources()
                    first['resources'] = current
                    first['idleSample'] = {'seconds': elapsed,
                        'cpuPercentOfOneCore': max(0, current['cpuTicks'] - sampled['cpuTicks'])
                            / os.sysconf('SC_CLK_TCK') / elapsed * 100,
                        'readBytes': max(0, current['readBytes'] - sampled['readBytes']),
                        'writeBytes': max(0, current['writeBytes'] - sampled['writeBytes']),
                        'majorFaults': max(0, current['majorFaults'] - sampled['majorFaults']),
                        'systemIoWaitPercent': (after['ioWaitTicks'] - system['ioWaitTicks'])
                            / max(1, after['cpuTicks'] - system['cpuTicks']) * 100,
                        'systemSwapInPages': after['swapInPages'] - system['swapInPages'],
                        'systemSwapOutPages': after['swapOutPages'] - system['swapOutPages']}
                    launches, direct, activations, launch_frames, direct_frames = [], [], [], [], []
                    launch_active, direct_active = [], []
                    for _ in range(options.repeats):
                        if app != 'terminal' and options.warm_mode == 'minimized':
                            call(app, 'Action', 'home')
                            time.sleep(.03)
                        generation = json.loads(call(app, 'Diagnose'))['performance']['activation'].get('generation', 0)
                        started = time.monotonic()
                        second = subprocess.run(command, env=env, capture_output=True, text=True, timeout=10)
                        if second.returncode:
                            raise RuntimeError(second.stderr)
                        launches.append((time.monotonic() - started) * 1000)
                        performance = wait_activation(app, generation)
                        activation = performance.get('activation', {})
                        latency = activation_latency(performance, started, 'toFrameMs')
                        if latency is not None:
                            launch_frames.append(latency)
                        latency = activation_latency(performance, started, 'toActiveMs')
                        if latency is not None:
                            launch_active.append(latency)
                        if activation.get('toActiveMs') is not None:
                            activations.append(activation['toActiveMs'])
                        if app != 'terminal':
                            if options.warm_mode == 'minimized':
                                call(app, 'Action', 'home')
                                time.sleep(.03)
                            generation = activation.get('generation', 0)
                            started = time.monotonic()
                            call(app, 'Open', json.dumps({'command': '', 'files': []}))
                            direct.append((time.monotonic() - started) * 1000)
                            performance = wait_activation(app, generation)
                            latency = activation_latency(performance, started, 'toFrameMs')
                            if latency is not None:
                                direct_frames.append(latency)
                            latency = activation_latency(performance, started, 'toActiveMs')
                            if latency is not None:
                                direct_active.append(latency)
                    first['warmLauncher'] = summary(launches)
                    first['handlerToActive'] = summary(activations) if activations else None
                    first['independentClientOpen'] = summary(direct) if direct else None
                    first['warmLauncherToFrame'] = summary(launch_frames)
                    first['independentClientToFrame'] = summary(direct_frames)
                    first['warmLauncherToActive'] = summary(launch_active)
                    first['independentClientToActive'] = summary(direct_active)
                    first['finalDiagnostics'] = json.loads(call(app, 'Diagnose')).get('performance')
                    runs.append(first)
                finally:
                    if process.poll() is None:
                        os.killpg(process.pid, signal.SIGTERM)
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid, signal.SIGKILL)
                        process.wait(timeout=5)
            print(json.dumps({'app': app, 'run': run, **first}), flush=True)
        report['apps'][app] = runs
        report['systemAfter'] = system_resources()
        (options.output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    raise SystemExit(main())
