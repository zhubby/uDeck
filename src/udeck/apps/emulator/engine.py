"""
[INPUT]: 依赖 QProcess、内容依赖扫描与原生存档文件操作。
[OUTPUT]: 提供 RetroEngine、内容哈希与禁用原生菜单的游戏配置。
[POS]: 受控游戏进程协议边界；uDeck 提供菜单并订阅存读档结果。
[PROTOCOL]: Update this header on change, then check AGENTS.md
"""

import hashlib
import re
import shutil
import signal
import tempfile
import time
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, QTimer, Signal

from udeck.apps.emulator.library import content_dependencies
from udeck.emulator_saves.files import copy_file, native_tree, replace_tree
from udeck.i18n import Msg, error_text, tr


def file_hash(path, cancelled=lambda: False):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            if cancelled():
                raise OSError(tr(Msg.SCAN_CANCELLED))
            digest.update(chunk)
    return digest.hexdigest()


def content_hash(item, cancelled=lambda: False):
    if item.get("noContent"):
        return hashlib.sha256(("no-content:" + item["coreId"]).encode()).hexdigest()
    base = file_hash(item["path"], cancelled)
    if item.get("archiveMember"):
        return hashlib.sha256((base + "#" + item["archiveMember"]).encode()).hexdigest()
    if Path(item["path"]).suffix.lower() not in (".cue", ".gdi", ".m3u"):
        return base
    digest = hashlib.sha256(base.encode())
    for track in content_dependencies(item["path"], item.get("platformRoot", Path(item["path"]).parent), cancelled):
        digest.update(file_hash(track, cancelled).encode())
    return digest.hexdigest()


def config_quote(value):
    value = str(value)
    if any(x in value for x in ('"', '\n', '\r')):
        raise ValueError(tr(Msg.UNSUPPORTED_QUOTE_OR_NEWLINE_IN_EMULATOR_PATH))
    return '"' + value + '"'


def stock_controls(sysfs=Path("/sys/class/input")):
    """Only apply the known stock mapping to the actual uConsole joypad."""
    for node in sorted(sysfs.glob("js*")):
        device = node / "device"
        try:
            identity = ((device / "id/vendor").read_text().strip(),
                        (device / "id/product").read_text().strip(),
                        (device / "uniq").read_text().strip())
            if identity != ("1eaf", "0024", "20230713") or (device / "name").read_text().strip() != "ClockworkPI uConsole":
                continue
            return {"input_joypad_driver": '"udev"', "input_player1_joypad_index": node.name[2:],
                    "input_player1_a_btn": '"1"', "input_player1_b_btn": '"2"',
                    "input_player1_x_btn": '"0"', "input_player1_y_btn": '"3"',
                    **{f"input_player1_{direction}_btn": f'"h0{direction}"'
                       for direction in ("up", "down", "left", "right")}}
        except OSError:
            continue
    return {}


class RetroEngine(QObject):
    changed = Signal()
    started = Signal()
    paused = Signal()
    finished = Signal(int)
    saved = Signal(str)
    loaded = Signal()
    failed = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.process = QProcess(self)
        self.process.readyReadStandardOutput.connect(self.read_stdout)
        self.process.readyReadStandardError.connect(self.read_stderr)
        self.process.finished.connect(self.exited)
        self.process.errorOccurred.connect(self.process_error)
        self.timer = QTimer(self)
        self.timer.setInterval(150)
        self.timer.timeout.connect(self.poll)
        self.quit_timer = QTimer(self)
        self.quit_timer.setSingleShot(True)
        self.quit_timer.setInterval(1000)
        self.quit_timer.timeout.connect(self.terminate)
        self.quitting = self.terminating = False
        self.status, self.log, self.stdout = "idle", "", ""
        self.stderr = ""
        self.pending = None
        self.want_pause = False
        self.status_requested = False
        self.runtime = None
        self.store = None
        self.metadata = {}
        self.deadline = 0
        self.load_observed = False
        self.sram_runtime = None
        self.sram_committed = False

    def start(self, item, checks, save_store, resume=False):
        if self.running():
            raise RuntimeError(tr(Msg.A_GAME_IS_ALREADY_RUNNING))
        self.quit_timer.stop()
        self.quitting = self.terminating = False
        self.store = save_store
        core_hash = checks.get("coreHash") or file_hash(checks["core"])
        self.metadata = {"contentHash": checks.get("contentHash") or content_hash(item), "coreHash": core_hash,
                         "game": item["id"], "core": checks["core"], "coreId": checks.get("coreId", ""),
                         "coreVersion": core_hash[:16], "savestate": checks.get("savestate", True)}
        self.runtime = tempfile.TemporaryDirectory(prefix="udeck-game-")
        root = Path(self.runtime.name)
        save_store.prepare_sram()
        sram = root / "sram"
        sram.mkdir(mode=0o700)
        for name, source in native_tree(save_store.sram_root).items():
            copy_file(source, sram / name)
        self.sram_runtime, self.sram_committed = sram, False
        # RetroArch uses retro_system_info.library_name when there is no content.
        basename = (item.get("basename") or Path(item["path"]).stem if item.get("path") else
                    checks.get("libraryName") or checks.get("coreId", "core"))
        self.state_path = root / (basename + ".state")
        options = {"stdin_cmd_enable": "true", "network_cmd_enable": "false", "config_save_on_exit": "false",
                   "pause_nonactive": "false", "savestate_auto_save": "false", "savestate_auto_load": "false",
                   "savestate_auto_index": "false", "savestate_file_compression": "false",
                   "savestate_thumbnail_enable": "true", "savestate_directory": config_quote(root),
                   "sort_savestates_enable": "false", "sort_savefiles_enable": "false",
                   "savestates_in_content_dir": "false", "savefiles_in_content_dir": "false",
                   "savefile_directory": config_quote(sram), "screenshot_directory": config_quote(root),
                   "system_directory": config_quote(checks["firmware"]), "state_slot": "0",
                   "input_exit_emulator": '"nul"', "video_fullscreen": "true", "user_language": "0"}
        options["quit_press_twice"] = "false"
        options["content_history_size"] = "0"
        options["history_list_enable"] = "false"
        options.update({"content_runtime_log": "false", "content_runtime_log_aggregate": "false",
                        "core_options_path": config_quote(root / "core-options.cfg"),
                        "core_options_directory": config_quote(root / "core-options"),
                        "game_specific_options": "false", "auto_overrides_enable": "false",
                        "auto_remaps_enable": "false", "auto_shaders_enable": "false"})
        # 菜单由 uDeck 提供，禁止继承原生菜单入口。
        options.update({"menu_driver": '"null"', "ui_companion_enable": "false",
                        "ui_companion_start_on_boot": "false", "ui_companion_toggle": "false",
                        "input_menu_toggle": '"nul"', "input_menu_toggle_btn": '"nul"',
                        "input_menu_toggle_axis": '"nul"', "input_menu_toggle_gamepad_combo": "0"})
        options.update(stock_controls())
        config = root / "udeck.cfg"
        config.write_text("\n".join(f"{key} = {value}" for key, value in options.items()) + "\n")
        self.resume_on_start = resume
        self.item = item
        self.status, self.log, self.stdout, self.stderr, self.pending = "starting", "", "", "", None
        self.want_pause = False
        self.status_requested = False
        self.deadline = time.monotonic() + 20
        self.process.setProgram(checks["executable"])
        arguments = ["--verbose", "--appendconfig", str(config), "-L", checks["core"]]
        if not item.get("noContent"):
            arguments.append(item.get("contentPath") or item["path"])
        self.process.setArguments(arguments)
        self.process.start()
        self.timer.start()
        self.changed.emit()

    def running(self):
        return self.process.state() != QProcess.ProcessState.NotRunning

    def send(self, command):
        if command == "GET_STATUS" and self.status_requested:
            return
        if not self.running() or self.process.write((command + "\n").encode()) < 0:
            raise OSError(tr(Msg.THE_EMULATOR_COMMAND_CHANNEL_IS_UNAVAILABLE))
        if command == "GET_STATUS":
            self.status_requested = True

    def read_stdout(self):
        self.stdout += bytes(self.process.readAllStandardOutput()).decode(errors="replace")
        lines = self.stdout.split("\n")
        self.stdout = lines.pop()
        for line in lines:
            if self.quitting:
                continue
            if (self.pending and self.pending["kind"] == "load" and self.load_observed
                    and re.fullmatch(r"\d+\.\d+\.\d+[^\s]*", line.strip())):
                self.pending["barrier"] = True
                # VERSION 确认此前指令已消费，再查询读档后的状态。
                self.status_requested = False
                self.send("GET_STATUS")
            if line.startswith("GET_STATUS "):
                self.status_requested = False
                # Drain failure logs before accepting the reply after our load barrier.
                self.read_stderr()
                value = line[11:].split(" ", 1)[0]
                previous_status = self.status
                starting = self.status == "starting"
                if value.startswith("PAUSED"):
                    first = self.status != "paused"
                    self.status = "paused"
                    self.want_pause = False
                    if self.resume_on_start:
                        self.resume_on_start = False
                        self.load("auto")
                    elif first:
                        self.paused.emit()
                elif value.startswith("PLAYING"):
                    first = self.status == "starting"
                    self.status = "playing"
                    if first and self.resume_on_start:
                        self.pause()
                if starting and self.status in ("playing", "paused"):
                    self.started.emit()
                state_changed = self.status != previous_status
                if (self.pending and self.pending["kind"] == "load"
                        and self.pending.get("barrier")):
                    self.pending = None
                    self.loaded.emit()
                    state_changed = True
                if state_changed:
                    self.changed.emit()

    def read_stderr(self):
        text = bytes(self.process.readAllStandardError()).decode(errors="replace")
        self.log = (self.log + text)[-64000:]
        self.stderr += text
        lines = self.stderr.split("\n")
        self.stderr = lines.pop()
        for line in lines:
            if not self.pending:
                continue
            if any(phrase in line.lower() for phrase in
                   ("failed to load state", "failed to save state", "does not support save states")):
                self.pending = None
                self.failed.emit(line[-1000:])
                continue
            if str(self.state_path) not in line:
                continue
            if self.pending["kind"] == "load" and "[State]: Loading state" in line and not self.load_observed:
                self.load_observed = True
                # The stdin poll runs on the main loop after the synchronous deserialize
                # callback. VERSION separates earlier status replies from this barrier.
                self.send("VERSION")
            elif self.pending["kind"] == "save":
                match = re.search(r'\[State\]: Saving state ".*", (\d+) bytes\.', line)
                if match:
                    self.pending["expected"] = int(match.group(1))

    def state_closed(self):
        descriptors = Path(f"/proc/{self.process.processId()}/fd")
        if not descriptors.is_dir():
            return True
        try:
            return not any(p.resolve() == self.state_path for p in descriptors.iterdir())
        except OSError:
            return False

    def poll(self):
        if not self.running() or self.quitting:
            return
        if not self.pending or self.pending["kind"] != "load":
            self.send("GET_STATUS")
        if self.status == "starting" and time.monotonic() > self.deadline:
            self.timer.stop()
            self.failed.emit(tr(Msg.RETROARCH_DID_NOT_REPORT_A_LOADED_GAME_CHECK_ITS_LOG))
        if self.pending:
            task = self.pending
            if time.monotonic() > task["deadline"]:
                self.pending = None
                self.failed.emit(tr(Msg.THE_EMULATOR_DID_NOT_CONFIRM_THE_OPERATION))
            elif task["kind"] == "save" and self.state_path.is_file():
                stamp = (self.state_path.stat().st_mtime_ns, self.state_path.stat().st_size)
                if (stamp[1] == task.get("expected") and stamp != task["old"]
                        and stamp == task.get("stable") and self.state_closed()):
                    self.pending = None
                    try:
                        thumbnail = Path(str(self.state_path) + ".png")
                        self.store.publish(task["slot"], self.state_path, self.metadata, thumbnail)
                        self.saved.emit(task["slot"])
                    except (OSError, ValueError) as error:
                        self.failed.emit(error_text(error))
                task["stable"] = stamp

    def pause(self):
        if self.status == "paused":
            self.paused.emit()
        elif self.status == "playing" and not self.want_pause:
            self.want_pause = True
            self.send("PAUSE_TOGGLE")

    def resume(self):
        if self.pending:
            raise RuntimeError(tr(Msg.PAUSE_THE_GAME_AND_WAIT_FOR_THE_CURRENT_OPERATION))
        if self.status == "paused":
            self.send("PAUSE_TOGGLE")

    def save(self, slot):
        if not self.metadata.get("savestate", True):
            raise RuntimeError(tr(Msg.THIS_CORE_DOES_NOT_SUPPORT_SAVE_STATES))
        if self.pending or self.status != "paused":
            raise RuntimeError(tr(Msg.PAUSE_THE_GAME_AND_WAIT_FOR_THE_CURRENT_OPERATION))
        stat = self.state_path.stat() if self.state_path.exists() else None
        self.pending = {"kind": "save", "slot": str(slot), "old": (stat.st_mtime_ns, stat.st_size) if stat else None,
                        "deadline": time.monotonic() + 15}
        self.send("SAVE_STATE")

    def load(self, slot):
        try:
            if not self.metadata.get("savestate", True):
                raise RuntimeError(tr(Msg.THIS_CORE_DOES_NOT_SUPPORT_SAVE_STATES))
            if self.pending or self.status != "paused":
                raise RuntimeError(tr(Msg.PAUSE_THE_GAME_AND_WAIT_FOR_THE_CURRENT_OPERATION))
            path, metadata = self.store.load(slot, self.metadata["contentHash"], self.metadata["coreHash"])
            self.read_stderr()
            shutil.copyfile(path, self.state_path)
            self.pending = {"kind": "load", "deadline": time.monotonic() + 15}
            self.load_observed = False
            self.send("LOAD_STATE")
        except (OSError, ValueError, RuntimeError) as error:
            self.failed.emit(error_text(error))

    def quit(self):
        if self.quitting or not self.running():
            return
        self.quitting = True
        self.pending = None
        self.status_requested = False
        self.timer.stop()
        self.quit_timer.start()
        try:
            self.send("QUIT")
        except OSError:
            self.terminate()

    def terminate(self):
        # Give the frontend a bounded chance to handle QUIT before SIGTERM.
        if self.quitting and self.running():
            self.terminating = True
            self.process.terminate()

    def process_error(self, error):
        if self.quitting and error == QProcess.ProcessError.WriteError:
            return
        if self.terminating and error == QProcess.ProcessError.Crashed:
            return  # exited() still reports unexpected exit codes/signals.
        self.failed.emit(self.process.errorString())
        if error == QProcess.ProcessError.FailedToStart:
            self.timer.stop()
            self.quit_timer.stop()
            self.status, self.pending = "idle", None
            self.status_requested = False
            self.sram_committed = False
            self.finished.emit(-1)
            self.changed.emit()

    def exited(self, code, status):
        self.timer.stop()
        self.quit_timer.stop()
        self.sram_committed = False
        if code == 0 and status == QProcess.ExitStatus.NormalExit and self.sram_runtime is not None:
            try:
                replace_tree(self.store.sram_root, native_tree(self.sram_runtime))
                self.sram_committed = True
            except (OSError, ValueError) as error:
                self.failed.emit(error_text(error))
        self.status, self.pending = "idle", None
        self.status_requested = False
        expected_signal = self.terminating and status == QProcess.ExitStatus.CrashExit and code == signal.SIGTERM
        self.quitting = self.terminating = False
        if code != 0 and not expected_signal:
            self.failed.emit(self.log[-1800:] or f"RetroArch exited with code {code}")
        self.finished.emit(code)
        self.changed.emit()

    def close(self):
        self.timer.stop()
        if self.running():
            self.quit()
            if not self.process.waitForFinished(1000):
                self.terminate()
                self.process.waitForFinished(2000)
        self.quit_timer.stop()
        if self.runtime and not self.running():
            self.runtime.cleanup()
