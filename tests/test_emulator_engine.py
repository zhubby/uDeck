"""
[INPUT]: 依赖真实 QProcess、隔离 stdin 前端与 RetroEngine。
[OUTPUT]: 验证游戏表面配置、轮询背压、状态通知与读档屏障。
[POS]: 模拟器进程协议回归；不连接设备图形会话。
[PROTOCOL]: Update this header on change, then check AGENTS.md
"""

import sys
import time
from pathlib import Path

import pytest
from PySide6.QtCore import QProcess
from PySide6.QtTest import QTest

from udeck.apps.emulator.controller import RetroEngine, SaveStore


def wait_for(predicate, seconds=5):
    deadline = time.monotonic() + seconds
    while not predicate() and time.monotonic() < deadline:
        QTest.qWait(10)
    assert predicate()


@pytest.fixture
def frontend(tmp_path):
    commands = tmp_path / "commands"
    script = tmp_path / "frontend"
    script.write_text(f"#!{sys.executable}\ncommands_path = {str(commands)!r}\n" + '''
import pathlib, re, sys
args = sys.argv[1:]
config = pathlib.Path(args[args.index("--appendconfig") + 1]).read_text()
root = pathlib.Path(re.search(r'^savestate_directory = "(.*)"$', config, re.M)[1])
state = root / "original.state"
status = "PLAYING"
for command in sys.stdin:
    command = command.strip()
    with open(commands_path, "a") as log:
        log.write(command + "\\n")
    if command == "QUIT":
        break
    if command == "ACK_STATUS":
        print("GET_STATUS " + status, flush=True)
    elif command == "PAUSE_TOGGLE":
        status = "PAUSED" if status == "PLAYING" else "PLAYING"
    elif command == "LOAD_STATE":
        print(f'[State]: Loading state "{state}"', file=sys.stderr, flush=True)
    elif command == "ACK_VERSION":
        print("1.20.0", flush=True)
''')
    script.chmod(0o700)
    core = tmp_path / "core.so"
    core.write_bytes(b"isolated core identity")
    rom = tmp_path / "original.rom"
    rom.write_bytes(b"original test content")
    item = {"id": "original", "path": str(rom)}
    checks = {"core": str(core), "firmware": str(tmp_path), "executable": str(script)}
    engine = RetroEngine()
    failures = []
    engine.failed.connect(lambda error: failures.append(str(error)))
    engine.start(item, checks, SaveStore(tmp_path / "saves"))
    engine.timer.stop()
    assert engine.process.waitForStarted(2000)
    try:
        yield engine, commands, item, checks, failures
    finally:
        engine.close()
        if engine.running():
            engine.process.kill()
            engine.process.waitForFinished(1000)


def checkpoint(engine, commands):
    marker = f"CHECKPOINT_{time.monotonic_ns()}"
    engine.send(marker)
    wait_for(lambda: commands.exists() and marker in commands.read_text().splitlines(), seconds=10)
    return commands.read_text().splitlines()


def test_frontend_receives_game_only_configuration(frontend):
    engine, _, _, _, _ = frontend
    arguments = engine.process.arguments()
    config = Path(arguments[arguments.index("--appendconfig") + 1])
    options = dict(line.split(" = ", 1) for line in config.read_text().splitlines())
    assert {key: options.get(key) for key in (
        "menu_driver", "ui_companion_enable", "ui_companion_start_on_boot", "ui_companion_toggle",
        "input_menu_toggle", "input_menu_toggle_btn", "input_menu_toggle_axis", "input_menu_toggle_gamepad_combo",
    )} == {
        "menu_driver": '"null"',
        "ui_companion_enable": "false",
        "ui_companion_start_on_boot": "false",
        "ui_companion_toggle": "false",
        "input_menu_toggle": '"nul"',
        "input_menu_toggle_btn": '"nul"',
        "input_menu_toggle_axis": '"nul"',
        "input_menu_toggle_gamepad_combo": "0",
    }
    assert options["stdin_cmd_enable"] == "true"


@pytest.mark.parametrize("paused", [False, True])
def test_unanswered_status_queries_stay_bounded_without_blocking_controls(frontend, paused):
    engine, commands, _, _, failures = frontend
    engine.send("ACK_STATUS")
    wait_for(lambda: engine.status == "playing")
    if paused:
        engine.pause()
        engine.send("ACK_STATUS")
        wait_for(lambda: engine.status == "paused")

    for _ in range(2000):
        engine.poll()
    assert checkpoint(engine, commands).count("GET_STATUS") == 1

    # 无回复时仍让暂停或续玩指令通过同一管道。
    engine.resume() if paused else engine.pause()
    assert checkpoint(engine, commands).count("PAUSE_TOGGLE") == (2 if paused else 1)
    engine.send("ACK_STATUS")
    wait_for(lambda: engine.status == ("playing" if paused else "paused"))
    for _ in range(2000):
        engine.poll()
    assert checkpoint(engine, commands).count("GET_STATUS") == 2
    engine.quit()
    wait_for(lambda: not engine.running())
    assert commands.read_text().splitlines()[-1] == "QUIT"
    assert not failures


@pytest.mark.parametrize("initial,reply,changed,paused,started", [
    ("playing", "PLAYING", 0, 0, 0),
    ("paused", "PAUSED", 0, 0, 0),
    ("playing", "PAUSED", 1, 1, 0),
    ("starting", "PLAYING", 1, 0, 1),
])
def test_repeated_status_replies_publish_only_state_transitions(
        monkeypatch, initial, reply, changed, paused, started):
    engine = RetroEngine()
    engine.resume_on_start = False
    engine.status = initial
    notifications, pauses, starts = [], [], []
    engine.changed.connect(lambda: notifications.append(engine.status))
    engine.paused.connect(lambda: pauses.append(engine.status))
    engine.started.connect(lambda: starts.append(engine.status))
    monkeypatch.setattr(engine.process, "readAllStandardOutput", lambda: (f"GET_STATUS {reply}\n" * 2000).encode())
    monkeypatch.setattr(engine.process, "readAllStandardError", lambda: b"")
    try:
        engine.read_stdout()
        assert len(notifications) == changed
        assert len(pauses) == paused
        assert len(starts) == started
    finally:
        engine.close()


def test_load_waits_for_version_barrier_before_requesting_confirmation(frontend):
    engine, commands, _, _, failures = frontend
    engine.send("ACK_STATUS")
    wait_for(lambda: engine.status == "playing")
    engine.pause()
    engine.send("ACK_STATUS")
    wait_for(lambda: engine.status == "paused")
    engine.state_path.write_bytes(b"saved progress")
    engine.store.publish("1", engine.state_path, engine.metadata)
    loaded, notifications = [], []
    engine.loaded.connect(lambda: loaded.append(True))
    engine.changed.connect(lambda: notifications.append((engine.status, bool(engine.pending))))
    engine.poll()
    engine.load("1")
    wait_for(lambda: commands.exists() and "VERSION" in commands.read_text().splitlines())
    assert checkpoint(engine, commands).count("GET_STATUS") == 1

    engine.send("ACK_STATUS")
    checkpoint(engine, commands)
    assert not loaded and engine.pending and not notifications
    engine.send("ACK_VERSION")
    wait_for(lambda: commands.read_text().splitlines().count("GET_STATUS") == 2)
    for _ in range(2000):
        engine.poll()
    assert checkpoint(engine, commands).count("GET_STATUS") == 2
    assert not loaded and engine.pending
    engine.send("ACK_STATUS")
    wait_for(lambda: loaded)
    assert engine.status == "paused" and engine.pending is None and not failures
    assert notifications == [("paused", False)]


def test_restart_can_query_status_after_exit_with_an_unanswered_query(frontend):
    engine, commands, item, checks, failures = frontend
    engine.poll()
    assert checkpoint(engine, commands).count("GET_STATUS") == 1
    engine.quit()
    wait_for(lambda: not engine.running())
    engine.start(item, checks, engine.store)
    engine.timer.stop()
    assert engine.process.waitForStarted(2000)
    engine.poll()
    assert checkpoint(engine, commands).count("GET_STATUS") == 2
    engine.send("ACK_STATUS")
    wait_for(lambda: engine.status == "playing")
    assert not failures


def test_failed_start_does_not_keep_an_outstanding_status_query(frontend):
    engine, commands, item, checks, failures = frontend
    engine.poll()
    checkpoint(engine, commands)
    engine.quit()
    wait_for(lambda: not engine.running())
    engine.start(item, {**checks, "executable": str(commands.parent / "missing")}, engine.store)
    wait_for(lambda: engine.process.state() == QProcess.ProcessState.NotRunning)
    assert failures
    engine.start(item, checks, engine.store)
    engine.timer.stop()
    assert engine.process.waitForStarted(2000)
    engine.poll()
    assert checkpoint(engine, commands).count("GET_STATUS") == 2
    engine.send("ACK_STATUS")
    wait_for(lambda: engine.status == "playing")
