"""
[INPUT]: 依赖隔离的 proc 文件树和应用进程身份。
[OUTPUT]: 验证整机 CPU、进程树 RSS、存活时间和终止身份校验。
[POS]: Console 运行统计的纯 Python 回归边界。
[PROTOCOL]: Update this header on change, then check AGENTS.md
"""

import os
import subprocess
import sys
import time
from dataclasses import replace

import pytest


def write_process(root, pid, *, parent=1, start=100, ticks=10, rss=8, name="game (core)"):
    directory = root / str(pid)
    directory.mkdir(exist_ok=True)
    fields = ["S", str(parent)] + ["0"] * 48
    fields[11], fields[12] = str(ticks), "0"
    fields[19], fields[21] = str(start), str(rss)
    (directory / "stat").write_text(f"{pid} ({name}) " + " ".join(fields))


@pytest.fixture
def proc(tmp_path):
    (tmp_path / "stat").write_text("cpu 100 0 100 700 100 0 0 0 0 0\n")
    (tmp_path / "uptime").write_text("20.00 30.00\n")
    (tmp_path / "meminfo").write_text("MemTotal: 4096 kB\nMemAvailable: 1024 kB\n")
    write_process(tmp_path, 101, start=1000)
    write_process(tmp_path, 102, parent=101, start=1200)
    write_process(tmp_path, 103, parent=102, start=1300)
    write_process(tmp_path, 104, parent=101, start=1400)
    return tmp_path


def test_process_tree_metrics_exclude_a_separate_application(proc):
    from udeck.runtime_console.processes import Identity, measure, read_snapshot

    first = read_snapshot(proc, ticks_per_second=100, page_size=4096)
    write_process(proc, 101, start=1000, ticks=30)
    write_process(proc, 102, parent=101, start=1200, ticks=40)
    write_process(proc, 103, parent=102, start=1300, ticks=60)
    write_process(proc, 104, parent=101, start=1400, ticks=20)
    (proc / "stat").write_text("cpu 160 0 140 700 100 0 0 0 0 0\n")
    second = read_snapshot(proc, ticks_per_second=100, page_size=4096)
    result = measure(second, first, {"terminal": Identity(101, 1000), "browser": Identity(102, 1200)})
    assert result["terminal"]["cpuPercent"] == pytest.approx(30)
    assert result["browser"]["cpuPercent"] == pytest.approx(80)
    assert result["terminal"]["memoryBytes"] == 2 * 8 * 4096
    assert result["browser"]["memoryBytes"] == 2 * 8 * 4096
    assert result["terminal"]["uptimeSeconds"] == 10
    assert result["browser"]["uptimeSeconds"] == 8
    assert second.memory_total == 4096 * 1024
    assert second.memory_available == 1024 * 1024


def test_first_cpu_sample_and_reused_pid_are_unavailable(proc):
    from udeck.runtime_console.processes import Identity, measure, read_snapshot

    first = read_snapshot(proc, ticks_per_second=100)
    root = {"emulator": Identity(101, 1000)}
    assert measure(first, None, root)["emulator"]["cpuPercent"] is None
    write_process(proc, 101, start=1800, ticks=500)
    current = read_snapshot(proc, ticks_per_second=100)
    assert measure(current, first, root)["emulator"]["memoryBytes"] is None


def test_shared_host_process_cannot_be_attributed_to_one_of_its_applications(proc):
    from udeck.runtime_console.processes import Identity, measure, read_snapshot

    current = read_snapshot(proc, ticks_per_second=100)
    result = measure(current, None, {"one": Identity(101, 1000), "two": Identity(101, 1000)})
    assert result["one"]["memoryBytes"] is None and result["two"]["memoryBytes"] is None
    assert not result["one"]["members"] and not result["two"]["members"]


def test_malformed_or_disappearing_process_does_not_break_other_readings(proc):
    from udeck.runtime_console.processes import read_snapshot

    (proc / "102/stat").write_text("102 (broken) incomplete")
    snapshot = read_snapshot(proc)
    assert 101 in snapshot.processes and 102 not in snapshot.processes


def test_force_termination_revalidates_pid_after_opening_pidfd(proc, monkeypatch):
    from udeck.runtime_console import processes

    opened, signaled, closed = [], [], []
    def open_fd(pid, flags=0):
        opened.append(pid)
        if pid == 101:
            write_process(proc, 101, start=9999)
        return pid + 1000
    monkeypatch.setattr(processes.os, "pidfd_open", open_fd, raising=False)
    monkeypatch.setattr(processes.signal, "pidfd_send_signal", lambda *args: signaled.append(args), raising=False)
    monkeypatch.setattr(processes.os, "close", closed.append)
    with pytest.raises(RuntimeError):
        processes.force_terminate(processes.Identity(101, 1000), [], proc=proc)
    assert 101 in opened and not signaled
    assert set(closed) == {pid + 1000 for pid in opened}


def test_force_termination_excludes_independent_app_and_signals_children_first(proc, monkeypatch):
    from udeck.runtime_console import processes

    signaled = []
    monkeypatch.setattr(processes.os, "pidfd_open", lambda pid, flags=0: pid + 1000, raising=False)
    monkeypatch.setattr(processes.signal, "pidfd_send_signal", lambda fd, *args: signaled.append(fd - 1000), raising=False)
    monkeypatch.setattr(processes.os, "close", lambda fd: None)
    processes.force_terminate(processes.Identity(101, 1000), [processes.Identity(102, 1200)], proc=proc)
    assert signaled == [104, 101]


def test_processes_owned_by_other_users_are_not_signal_targets(proc, monkeypatch):
    from udeck.runtime_console import processes

    sample = processes.read_snapshot(proc)
    sample.processes[101] = replace(sample.processes[101], uid=os.getuid() + 1)
    monkeypatch.setattr(processes, "read_snapshot", lambda *args, **kwargs: sample)
    with pytest.raises(RuntimeError):
        processes.force_terminate(processes.Identity(101, 1000), [], proc=proc)


@pytest.mark.skipif(sys.platform != "linux" or not hasattr(os, "pidfd_open"), reason="Linux pidfd integration")
def test_real_force_termination_ends_child_and_parent_and_preserves_another_app(tmp_path):
    from udeck.runtime_console.processes import force_terminate, read_process

    child_file = tmp_path / "child-pid"
    program = ('import pathlib,subprocess,sys,time; child=subprocess.Popen([sys.executable,"-c","import time; time.sleep(300)"]); '
               'pathlib.Path(sys.argv[1]).write_text(str(child.pid)); time.sleep(300)')
    parent = subprocess.Popen([sys.executable, "-c", program, str(child_file)])
    other = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(300)"])
    child_fd = None
    try:
        deadline = time.monotonic() + 3
        while not child_file.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        child_pid = int(child_file.read_text())
        child_fd = os.pidfd_open(child_pid)
        force_terminate(read_process(parent.pid).identity, [read_process(other.pid).identity])
        assert parent.wait(timeout=3) == -9
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            try:
                if read_process(child_pid).state == "Z":
                    break
            except FileNotFoundError:
                break
            time.sleep(0.01)
        else:
            pytest.fail("Application child survived force termination")
        assert other.poll() is None
    finally:
        for process in (parent, other):
            if process.poll() is None:
                process.kill()
            process.wait(timeout=3)
        if child_fd is not None:
            import signal
            try:
                signal.pidfd_send_signal(child_fd, signal.SIGKILL)
            except ProcessLookupError:
                pass
            os.close(child_fd)
