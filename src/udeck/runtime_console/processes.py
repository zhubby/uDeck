"""
[INPUT]: 依赖 Linux proc、进程启动时刻与 pidfd 信号。
[OUTPUT]: 提供身份验证、整机快照、应用资源聚合和进程树终止。
[POS]: Console 的无 Qt 数据层；不以进程名推断应用归属。
[PROTOCOL]: Update this header on change, then check AGENTS.md
"""

import os
import signal
from collections import Counter
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Identity:
    pid: int
    start: int


@dataclass(frozen=True)
class Process:
    identity: Identity
    parent: int
    uid: int
    ticks: int
    rss: int
    state: str


@dataclass
class Snapshot:
    processes: dict
    total_ticks: int
    idle_ticks: int
    uptime: float
    memory_total: int
    memory_available: int
    ticks_per_second: int


def read_process(pid, proc=Path("/proc"), *, page_size=None):
    directory = Path(proc) / str(pid)
    text = (directory / "stat").read_text()
    fields = text[text.rindex(")") + 2:].split()
    return Process(Identity(int(pid), int(fields[19])), int(fields[1]), directory.stat().st_uid,
                   int(fields[11]) + int(fields[12]), max(0, int(fields[21])) * (page_size or os.sysconf("SC_PAGE_SIZE")),
                   fields[0])


def read_snapshot(proc=Path("/proc"), *, ticks_per_second=None, page_size=None):
    proc = Path(proc)
    counters = [int(value) for value in (proc / "stat").read_text().splitlines()[0].split()[1:9]]
    if len(counters) < 4:
        raise ValueError("Invalid CPU counters")
    memory = {}
    for line in (proc / "meminfo").read_text().splitlines():
        name, _, value = line.partition(":")
        if name in ("MemTotal", "MemAvailable"):
            memory[name] = int(value.split()[0]) * 1024
    processes = {}
    for directory in proc.iterdir():
        if not directory.name.isdigit():
            continue
        try:
            value = read_process(int(directory.name), proc, page_size=page_size)
            processes[value.identity.pid] = value
        except (OSError, ValueError, IndexError):
            continue
    return Snapshot(processes, sum(counters), counters[3] + (counters[4] if len(counters) > 4 else 0),
                    float((proc / "uptime").read_text().split()[0]), memory.get("MemTotal", 0),
                    memory.get("MemAvailable", 0), ticks_per_second or os.sysconf("SC_CLK_TCK"))


def partition(snapshot, roots):
    valid = {key: identity for key, identity in roots.items()
             if snapshot.processes.get(identity.pid) is not None
             and snapshot.processes[identity.pid].identity == identity}
    counts = Counter(identity.pid for identity in valid.values())
    owners = {identity.pid: key for key, identity in valid.items() if counts[identity.pid] == 1}
    groups = {key: [] for key in roots}
    for process in snapshot.processes.values():
        current, seen = process.identity.pid, set()
        while current in snapshot.processes and current not in seen:
            if current in counts:
                if current in owners:
                    groups[owners[current]].append(process)
                break
            seen.add(current)
            current = snapshot.processes[current].parent
    return groups


def measure(current, previous, roots):
    denominator = current.total_ticks - previous.total_ticks if previous else 0
    result = {}
    for key, members in partition(current, roots).items():
        root = current.processes.get(roots[key].pid)
        valid = root is not None and root.identity == roots[key] and root in members
        delta = 0
        for process in members:
            old = previous.processes.get(process.identity.pid) if previous else None
            if old and old.identity == process.identity:
                delta += max(0, process.ticks - old.ticks)
        result[key] = {
            "cpuPercent": min(100.0, delta * 100 / denominator) if valid and denominator > 0 else None,
            "memoryBytes": sum(p.rss for p in members) if valid else None,
            "uptimeSeconds": max(0, current.uptime - roots[key].start / current.ticks_per_second) if valid else None,
            "members": [p.identity for p in members],
        }
    return result


def system_metrics(current, previous):
    delta = current.total_ticks - previous.total_ticks if previous else 0
    idle = current.idle_ticks - previous.idle_ticks if previous else 0
    return {"cpuPercent": max(0.0, min(100.0, (delta - idle) * 100 / delta)) if delta > 0 else None,
            "memoryTotal": current.memory_total,
            "memoryUsed": max(0, current.memory_total - current.memory_available)}


def force_terminate(identity, protected, *, proc=Path("/proc")):
    if not hasattr(os, "pidfd_open") or not hasattr(signal, "pidfd_send_signal"):
        raise RuntimeError("Process identity signaling is unavailable")
    current = read_snapshot(proc)
    root = current.processes.get(identity.pid)
    if root is None or root.identity != identity or root.uid != os.getuid() or identity.pid <= 1:
        raise RuntimeError("Application exited or its process identity changed")
    roots = {"target": identity, **{f"protected-{i}": value for i, value in enumerate(protected)}}
    own = current.processes.get(os.getpid())
    if own:
        roots["console"] = own.identity
    members = partition(current, roots)["target"]
    if not members or any(p.identity.pid == os.getpid() or p.uid != os.getuid() for p in members):
        raise RuntimeError("Application process ownership is unavailable")

    def depth(process):
        value, seen = process.parent, set()
        while value in current.processes and value not in seen:
            seen.add(value)
            value = current.processes[value].parent
        return len(seen)

    members.sort(key=depth, reverse=True)
    descriptors = []
    try:
        # 先固定全部身份，再发送信号；任何复用都取消整次操作。
        for process in members:
            try:
                descriptor = os.pidfd_open(process.identity.pid, 0)
            except ProcessLookupError:
                continue
            descriptors.append((process, descriptor))
            try:
                refreshed = read_process(process.identity.pid, proc)
            except (OSError, ValueError, IndexError) as error:
                raise RuntimeError("Application process identity changed") from error
            if refreshed.identity != process.identity or refreshed.uid != os.getuid():
                raise RuntimeError("Application process identity changed")
        for _process, descriptor in descriptors:
            try:
                signal.pidfd_send_signal(descriptor, signal.SIGKILL)
            except ProcessLookupError:
                pass
    finally:
        for _process, descriptor in descriptors:
            os.close(descriptor)
