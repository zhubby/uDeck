"""
[INPUT]: 依赖会话监督器和独立 Python 子进程。
[OUTPUT]: 验证滚动预算、真实崩溃、正常退出和终止清理。
[POS]: 会话恢复的隔离回归；不操作正式桌面。
[PROTOCOL]: Update this header on change, then check AGENTS.md
"""

import json
import os
import signal
import subprocess
import sys
import time

import pytest

from udeck.session_supervisor import CrashBudget


def test_crash_budget_renews_after_stable_uptime_and_expires_old_failures():
    budget = CrashBudget(window=60, maximum=3)
    assert budget.retry(0, 1)
    assert budget.retry(2, 3)
    assert budget.retry(4, 65)
    assert len(budget.failures) == 1
    assert budget.retry(66, 67)
    assert not budget.retry(68, 69)
    assert budget.retry(129, 130)
    assert list(budget.failures) == [130]


def test_cleanup_forces_group_when_liveness_probe_is_not_permitted(monkeypatch):
    from udeck import session_supervisor

    signals = []

    def killpg(_pid, signum):
        signals.append(signum)
        if signum == 0:
            raise PermissionError

    class CrashedProcess:
        pid = 123

        @staticmethod
        def poll():
            return -signal.SIGSEGV

    monkeypatch.setattr(session_supervisor.os, 'killpg', killpg)
    session_supervisor.cleanup_process_group(CrashedProcess(), grace=.001)

    assert signals == [signal.SIGTERM, 0, signal.SIGKILL]


@pytest.mark.parametrize('crashes,expected,count', [(0, 0, 1), (2, 0, 3), (9, 1, 3)])
def test_private_crashes_restart_only_within_budget(tmp_path, crashes, expected, count):
    worker = tmp_path / 'worker.py'
    launches = tmp_path / 'launches.json'
    worker.write_text(f"""
import json, os, pathlib, signal, subprocess, sys
path = pathlib.Path({str(launches)!r})
count = json.loads(path.read_text()) if path.exists() else 0
path.write_text(json.dumps(count + 1))
if count < {crashes}:
    subprocess.Popen([sys.executable, '-c', 'import time;time.sleep(30)'])
    os.kill(os.getpid(), signal.SIGSEGV)
""")
    code = f"""
import sys
from udeck.session_supervisor import supervise
raise SystemExit(supervise([sys.executable, {str(worker)!r}], delay=.01,
    restore=lambda: print('restored', flush=True)))
"""
    result = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True,
                            env={**os.environ, 'PYTHONPATH': 'src'}, timeout=8)
    assert result.returncode == expected, result.stdout + result.stderr
    assert json.loads(launches.read_text()) == count
    assert result.stdout.count('restored') == count


def test_term_stops_private_desktop_without_restarting_and_restores(tmp_path):
    ready = tmp_path / 'pid'
    restored = tmp_path / 'restored'
    worker = f"import os,time,pathlib;pathlib.Path({str(ready)!r}).write_text(str(os.getpid()));time.sleep(30)"
    code = f"""
import pathlib, sys
from udeck.session_supervisor import supervise
raise SystemExit(supervise([sys.executable, '-c', {worker!r}], delay=.01,
    restore=lambda: pathlib.Path({str(restored)!r}).write_text('done')))
"""
    process = subprocess.Popen([sys.executable, '-c', code], env={**os.environ, 'PYTHONPATH': 'src'})
    try:
        deadline = time.monotonic() + 5
        while not ready.exists() and time.monotonic() < deadline:
            time.sleep(.01)
        assert ready.exists()
        pid = int(ready.read_text())
        process.send_signal(signal.SIGTERM)
        assert process.wait(timeout=5) == 0
        assert restored.read_text() == 'done'
        with pytest.raises(ProcessLookupError):
            os.kill(pid, 0)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
