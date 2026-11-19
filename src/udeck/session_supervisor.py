"""
[INPUT]: 依赖桌面子进程、单调时钟和会话终止信号。
[OUTPUT]: 提供滚动崩溃预算、正常退出和有界子进程清理。
[POS]: labwc 会话的桌面监督器；每次退出后恢复会话配置。
[PROTOCOL]: Update this header on change, then check AGENTS.md
"""

import argparse
import os
import signal
import subprocess
import sys
import threading
import time
from collections import deque


class CrashBudget:
    def __init__(self, window=60.0, maximum=3):
        self.window, self.maximum = window, maximum
        self.failures = deque()

    def retry(self, started, ended):
        if ended - started >= self.window:
            self.failures.clear()
        while self.failures and ended - self.failures[0] >= self.window:
            self.failures.popleft()
        self.failures.append(ended)
        return len(self.failures) < self.maximum


def signal_process_group(process, signum):
    if os.name == 'posix':
        try:
            os.killpg(process.pid, signum)
        except ProcessLookupError:
            pass
        except PermissionError:
            if process.poll() is None:
                process.send_signal(signum)
    elif process.poll() is None:
        process.send_signal(signum)


def cleanup_process_group(process, grace=1.0):
    signal_process_group(process, signal.SIGTERM)
    if os.name != 'posix':
        return
    deadline = time.monotonic() + grace
    while time.monotonic() < deadline:
        try:
            os.killpg(process.pid, 0)
        except ProcessLookupError:
            return
        except PermissionError:
            pass
        time.sleep(.02)
    signal_process_group(process, signal.SIGKILL)


def supervise(command, *, budget=None, delay=1.0, restore=None):
    budget = budget or CrashBudget()
    stopping = threading.Event()
    previous = {}
    child = None

    def stop(_signal, _frame):
        stopping.set()
        if child is not None and child.poll() is None:
            signal_process_group(child, signal.SIGTERM)

    for number in (signal.SIGHUP, signal.SIGINT, signal.SIGTERM):
        previous[number] = signal.signal(number, stop)
    try:
        while not stopping.is_set():
            started = time.monotonic()
            try:
                child = subprocess.Popen(command, start_new_session=os.name == 'posix')
            except OSError as error:
                print(f'uDeck session: cannot start desktop: {error}', file=sys.stderr, flush=True)
                status = 127
            else:
                while child.poll() is None and not stopping.wait(.05):
                    pass
                if stopping.is_set():
                    try:
                        child.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        signal_process_group(child, signal.SIGKILL)
                        child.wait()
                status = child.wait()
                cleanup_process_group(child)
            ended = time.monotonic()
            child = None
            if restore:
                restore()
            if stopping.is_set() or status == 0:
                return 0
            if not budget.retry(started, ended):
                print('uDeck session: rapid crash limit reached', file=sys.stderr, flush=True)
                return 1
            print(f'uDeck session: desktop exited ({status}); restarting', file=sys.stderr, flush=True)
            stopping.wait(delay)
        return 0
    finally:
        for number, handler in previous.items():
            signal.signal(number, handler)


def restore_session():
    try:
        subprocess.run([sys.executable, '-m', 'udeck.session_config', 'restore'],
                       timeout=10, check=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        print(f'uDeck session: configuration restore failed: {error}', file=sys.stderr, flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description='Supervise the uDeck desktop session')
    parser.add_argument('command', nargs=argparse.REMAINDER)
    options = parser.parse_args(argv)
    command = options.command or ['udeck']
    if command[0] == '--':
        command = command[1:]
    if not command:
        parser.error('A desktop command is required')
    return supervise(command, restore=restore_session)


if __name__ == '__main__':
    raise SystemExit(main())
