"""External RetroArch ownership, preflight and atomically published save groups."""

import hashlib
import json
import os
import re
import shutil
import tempfile
import time
import uuid
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, QTimer, Signal, Slot

from ..i18n import error_text, tr
from .controller import AppController
from .state import atomic_json

CORES = {"GB": ("gambatte_libretro.so", ()), "GBA": ("mgba_libretro.so", ()),
         "SNES": ("snes9x_libretro.so", ()), "NES": ("nestopia_libretro.so", ()),
         "PS1": ("pcsx_rearmed_libretro.so", ("scph5501.bin",))}


def file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def disc_tracks(path):
    names = re.findall(r'^\s*FILE\s+(?:"([^"\n]+)"|(\S+))\s+', Path(path).read_text(errors="replace"), re.M | re.I)
    return [Path(path).parent / (quoted or plain) for quoted, plain in names]


def content_hash(item):
    base = file_hash(item["path"])
    if item["format"] != "CUE":
        return base
    digest = hashlib.sha256(base.encode())
    for track in disc_tracks(item["path"]):
        digest.update(file_hash(track).encode())
    return digest.hexdigest()


def preflight(item, preferences, executable=None):
    executable = executable or shutil.which("retroarch")
    core_name, firmware = CORES.get(item["platform"], ("", ()))
    candidates = [Path(preferences.get("coreDirectory", "/usr/lib/aarch64-linux-gnu/libretro")),
                  Path("/usr/lib/x86_64-linux-gnu/libretro"), Path("/usr/lib/libretro")]
    core = next((p / core_name for p in candidates if core_name and (p / core_name).is_file()), None)
    system = Path(preferences.get("firmwareDirectory", str(Path.home() / ".config/retroarch/system")))
    missing = []
    if not executable:
        missing.append(tr("RetroArch is not installed"))
    if not Path(item["path"]).is_file():
        missing.append(tr("Game source is disconnected"))
    if not core:
        missing.append(tr("Missing core: {core}", core=core_name or item["platform"]))
    for name in firmware:
        if not (system / name).is_file():
            missing.append(tr("Missing firmware: {name}", name=name))
    if item["format"] == "CUE" and Path(item["path"]).is_file():
        for track in disc_tracks(item["path"]):
            if not track.is_file():
                missing.append(tr("Missing disc track: {name}", name=track.name))
    return {"ready": not missing, "errors": missing, "core": str(core) if core else core_name,
            "firmware": str(system), "executable": executable or ""}


class SaveStore:
    def __init__(self, root):
        self.root = Path(root)

    def manifest(self):
        try:
            slots = json.loads((self.root / "slots.json").read_text())
            if not isinstance(slots, dict):
                raise ValueError(tr("The save index is damaged"))
            return slots
        except FileNotFoundError:
            return {}

    def publish(self, slot, state_file, metadata, thumbnail=None):
        if not Path(state_file).is_file() or Path(state_file).stat().st_size == 0:
            raise OSError(tr("The core did not write a save state"))
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        name = uuid.uuid4().hex
        staging = self.root / ("." + name)
        staging.mkdir(mode=0o700)
        try:
            target = staging / "state"
            with Path(state_file).open("rb") as source, target.open("wb") as output:
                shutil.copyfileobj(source, output)
                output.flush()
                os.fsync(output.fileno())
            data = {**metadata, "version": 1, "sha256": file_hash(target), "created": time.time(),
                    "thumbnail": bool(thumbnail and Path(thumbnail).is_file())}
            if data["thumbnail"]:
                shutil.copyfile(thumbnail, staging / "thumbnail.png")
            atomic_json(staging / "metadata.json", data)
            os.replace(staging, self.root / name)
            slots = self.manifest()
            slots[str(slot)] = name
            atomic_json(self.root / "slots.json", slots)
            return data
        finally:
            if staging.exists():
                shutil.rmtree(staging)

    def load(self, slot, content_hash, core_hash):
        name = self.manifest().get(str(slot))
        if not isinstance(name, str) or len(name) != 32 or any(c not in "0123456789abcdef" for c in name):
            raise ValueError(tr("This save slot is empty"))
        directory = self.root / name
        metadata = json.loads((directory / "metadata.json").read_text())
        if not isinstance(metadata, dict):
            raise ValueError(tr("The save state is damaged"))
        if metadata.get("version") != 1 or metadata.get("contentHash") != content_hash or metadata.get("coreHash") != core_hash:
            raise ValueError(tr("This state belongs to another game or core version"))
        path = directory / "state"
        if file_hash(path) != metadata.get("sha256"):
            raise ValueError(tr("The save state is damaged"))
        return path, metadata


def config_quote(value):
    value = str(value)
    if any(x in value for x in ('"', '\n', '\r')):
        raise ValueError(tr("Unsupported quote or newline in emulator path"))
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
        self.process.errorOccurred.connect(lambda error: self.failed.emit(self.process.errorString()))
        self.timer = QTimer(self)
        self.timer.setInterval(150)
        self.timer.timeout.connect(self.poll)
        self.status, self.log, self.stdout = "idle", "", ""
        self.stderr = ""
        self.pending = None
        self.want_pause = False
        self.runtime = None
        self.store = None
        self.metadata = {}
        self.deadline = 0
        self.load_observed = False

    def start(self, item, checks, save_store, resume=False):
        if self.running():
            raise RuntimeError(tr("A game is already running"))
        self.store = save_store
        core_hash = file_hash(checks["core"])
        self.metadata = {"contentHash": content_hash(item), "coreHash": core_hash,
                         "game": item["id"], "core": checks["core"], "coreVersion": core_hash[:16]}
        self.runtime = tempfile.TemporaryDirectory(prefix="udeck-game-")
        root = Path(self.runtime.name)
        sram = save_store.root / "sram"
        sram.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.state_path = root / (Path(item["path"]).stem + ".state")
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
        options.update(stock_controls())
        config = root / "udeck.cfg"
        config.write_text("\n".join(f"{key} = {value}" for key, value in options.items()) + "\n")
        self.resume_on_start = resume
        self.item = item
        self.status, self.log, self.stdout, self.stderr, self.pending = "starting", "", "", "", None
        self.want_pause = False
        self.deadline = time.monotonic() + 20
        self.process.setProgram(checks["executable"])
        self.process.setArguments(["--verbose", "--appendconfig", str(config), "-L", checks["core"], item["path"]])
        self.process.start()
        self.timer.start()
        self.changed.emit()

    def running(self):
        return self.process.state() != QProcess.ProcessState.NotRunning

    def send(self, command):
        if not self.running() or self.process.write((command + "\n").encode()) < 0:
            raise OSError(tr("The emulator command channel is unavailable"))

    def read_stdout(self):
        self.stdout += bytes(self.process.readAllStandardOutput()).decode(errors="replace")
        while "\n" in self.stdout:
            line, self.stdout = self.stdout.split("\n", 1)
            if (self.pending and self.pending["kind"] == "load" and self.load_observed
                    and re.fullmatch(r"\d+\.\d+\.\d+[^\s]*", line.strip())):
                self.pending["barrier"] = True
            if line.startswith("GET_STATUS "):
                # Drain failure logs before accepting the reply after our load barrier.
                self.read_stderr()
                value = line[11:].split(" ", 1)[0]
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
                if (self.pending and self.pending["kind"] == "load"
                        and self.pending.get("barrier")):
                    self.pending = None
                    self.loaded.emit()
                self.changed.emit()

    def read_stderr(self):
        text = bytes(self.process.readAllStandardError()).decode(errors="replace")
        self.log = (self.log + text)[-64000:]
        self.stderr += text
        while "\n" in self.stderr:
            line, self.stderr = self.stderr.split("\n", 1)
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
                self.send("GET_STATUS")
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
        if not self.running():
            return
        if not self.pending or self.pending["kind"] != "load":
            self.send("GET_STATUS")
        if self.status == "starting" and time.monotonic() > self.deadline:
            self.timer.stop()
            self.failed.emit(tr("RetroArch did not report a loaded game. Check its log."))
        if self.pending:
            task = self.pending
            if time.monotonic() > task["deadline"]:
                self.pending = None
                self.failed.emit(tr("The emulator did not confirm the operation"))
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
            raise RuntimeError(tr("Pause the game and wait for the current operation"))
        if self.status == "paused":
            self.send("PAUSE_TOGGLE")

    def save(self, slot):
        if self.pending or self.status != "paused":
            raise RuntimeError(tr("Pause the game and wait for the current operation"))
        stat = self.state_path.stat() if self.state_path.exists() else None
        self.pending = {"kind": "save", "slot": str(slot), "old": (stat.st_mtime_ns, stat.st_size) if stat else None,
                        "deadline": time.monotonic() + 15}
        self.send("SAVE_STATE")

    def load(self, slot):
        try:
            if self.pending or self.status != "paused":
                raise RuntimeError(tr("Pause the game and wait for the current operation"))
            path, metadata = self.store.load(slot, self.metadata["contentHash"], self.metadata["coreHash"])
            self.read_stderr()
            shutil.copyfile(path, self.state_path)
            self.pending = {"kind": "load", "deadline": time.monotonic() + 15}
            self.load_observed = False
            self.send("LOAD_STATE")
        except (OSError, ValueError, RuntimeError) as error:
            self.failed.emit(error_text(error))

    def quit(self):
        self.send("QUIT")

    def exited(self, code, status):
        self.timer.stop()
        self.status, self.pending = "idle", None
        if code != 0:
            self.failed.emit(self.log[-1800:] or f"RetroArch exited with code {code}")
        self.finished.emit(code)
        self.changed.emit()

    def close(self):
        self.timer.stop()
        if self.running():
            self.send("QUIT")
            self.process.waitForFinished(3000)
        if self.runtime and not self.running():
            self.runtime.cleanup()


class GamesController(AppController):
    def __init__(self, directory=None, language_path=None):
        super().__init__("games", directory, language_path)
        self.engine = RetroEngine(self)
        self.engine.changed.connect(self.publish)
        self.engine.paused.connect(self.pause_menu)
        self.engine.saved.connect(self.save_done)
        self.engine.loaded.connect(self.load_done)
        self.engine.failed.connect(self.game_failed)
        self.engine.finished.connect(self.game_exited)
        self.platform = "All"
        self.exit_after_save = False
        self.game_started = None
        self.checks = {}
        self.source_missing = False
        self.reconnect_checked = False

    def tabs(self):
        return [tr("Recently played"), tr("All platforms"), tr("Favorites")]

    def rows(self):
        rows = super().rows()
        if self.tab == 0:
            order = self.store.data["recent"]
            rows = [r for r in rows if r["id"] in order]
            rows.sort(key=lambda r: order.index(r["id"]))
        elif self.tab == 2:
            rows = [r for r in rows if r["id"] in self.store.data["favorites"]]
        if self.platform != "All":
            rows = [r for r in rows if r["platform"] == self.platform]
        return [{**r, "subtitle": r["platform"]} for r in rows]

    def save_store(self):
        return SaveStore(self.store.path.parent / "game-saves" / self.current["id"])

    def open_item(self, identifier):
        if self.engine.running():
            raise RuntimeError(tr("A game is already running"))
        self.current = self.library.require(identifier)
        self.checks = preflight(self.current, self.store.data["preferences"])
        self.enter("game-details")

    def extra_state(self):
        save_error = ""
        try:
            slots = self.save_store().manifest() if self.current else {}
        except (OSError, ValueError) as error:
            slots = {}
            save_error = tr("Cannot read saves: {error}", error=error)
        return {"platform": self.platform, "gameStatus": self.engine.status,
                "gameChecks": self.checks, "saveSlots": list(slots),
                "gameBusy": bool(self.engine.pending), "sourceMissing": self.source_missing,
                "saveError": save_error}

    def start_game(self, resume=False):
        item = self.library.require(self.current["id"])
        self.checks = preflight(item, self.store.data["preferences"])
        if not self.checks["ready"]:
            raise RuntimeError("\n".join(map(str, self.checks["errors"])))
        self.engine.start(item, self.checks, self.save_store(), resume)
        self.clear_menus()
        self.page = "game-running"
        self.game_started = time.monotonic()
        self.source_missing = False
        self.store.remember(item["id"])
        self.persist()

    def pause_menu(self):
        if not self.engine.running():
            return
        self.clear_menus()
        self.present.emit()
        self.menu(tr("Game paused"), [
            (tr("Resume"), self.resume_game if not self.source_missing else None,
             tr("Reconnect the source first") if self.source_missing else ""),
            (tr("Save state"), (lambda: self.slots_menu(False)) if not self.source_missing else None),
            (tr("Load state"), (lambda: self.slots_menu(True)) if not self.source_missing else None),
            (tr("Controls"), self.controls_menu),
            (tr("Save and return to library"), self.save_exit if not self.source_missing else None),
            (tr("Return without saving"), self.confirm_quit)])

    def resume_game(self):
        if self.source_missing:
            raise OSError(tr("The source is disconnected"))
        self.engine.resume()
        self.clear_menus()
        self.desktop("Home") if not self.window else self.window.showMinimized()

    def slots_menu(self, load):
        slots = self.save_store().manifest()
        options = []
        for slot in ("1", "2", "3"):
            exists = slot in slots
            options.append((tr("Slot {slot}", slot=slot),
                            (lambda s=slot: self.confirm_slot(s, load)) if exists or not load else None,
                            tr("Saved") if exists else tr("Empty")))
        self.menu(tr("Load state") if load else tr("Save state"), options)

    def confirm_slot(self, slot, load):
        self.menu(tr("Load this state?") if load else tr("Replace this slot?") if slot in self.save_store().manifest() else tr("Save in this slot?"),
                  [(tr("Confirm"), lambda: self.slot_action(slot, load)), (tr("Cancel"), self.pop_menu)],
                  tr("Loading replaces progress made since the saved state.") if load else "")

    def slot_action(self, slot, load):
        self.library.require(self.current["id"])
        self.pop_menu()
        self.engine.load(slot) if load else self.engine.save(slot)

    def save_done(self, slot):
        self.notice = tr("State saved")
        if self.exit_after_save:
            self.exit_after_save = False
            self.engine.quit()
        else:
            self.pause_menu()

    def load_done(self):
        self.notice = tr("State loaded")
        if self.source_missing:
            self.pause_menu()
        else:
            self.attempt(self.resume_game)

    def save_exit(self):
        self.library.require(self.current["id"])
        self.engine.save("auto")
        self.exit_after_save = True

    def confirm_quit(self):
        self.menu(tr("Return without saving?"), [(tr("Confirm"), self.engine.quit), (tr("Cancel"), self.pop_menu)])

    def controls_menu(self):
        self.menu(tr("Controls"), [(tr("Back"), self.pop_menu)],
                  tr("During gameplay, all buttons belong to RetroArch. Ctrl+Alt+M opens this menu. Ctrl+Alt+Esc returns to the desktop."))

    def game_failed(self, text):
        self.exit_after_save = False
        self.error = tr("Emulator error: {error}", error=text)
        self.present.emit()
        self.publish()

    def game_exited(self, code):
        self.exit_after_save = False
        self.clear_menus()
        self.page = "game-details"
        if self.game_started:
            record = self.store.data["positions"].setdefault(self.current["id"], {})
            record["seconds"] = record.get("seconds", 0) + time.monotonic() - self.game_started
            self.game_started = None
        self.attempt(self.persist)
        self.present.emit()

    def context(self):
        if self.page == "game-details":
            self.detail_menu()
        elif self.engine.running():
            self.engine.pause()
        else:
            self.menu(tr("Games actions"), [(tr("Platform filter"), self.platform_menu),
                       (tr("Toggle favorite"), self.toggle_favorite),
                       (tr("Search"), lambda: self.prompt(tr("Search library"), self.search, self.filter)),
                       (tr("Sources"), self.sources_menu), (tr("Refresh library"), self.refresh)])

    def detail_menu(self):
        self.menu(self.current["title"], [
            (tr("Continue"), lambda: self.start_game(True) if "auto" in self.save_store().manifest() else self.start_game()),
            (tr("Restart"), lambda: self.start_game()),
            (tr("Toggle favorite"), self.toggle_favorite), (tr("Settings"), self.settings)],
            "\n".join(map(str, self.checks.get("errors", []))))

    def platform_menu(self):
        self.menu(tr("Platform filter"), [(p, lambda p=p: self.set_platform(p)) for p in ("All", *CORES)])

    def set_platform(self, platform):
        self.platform = platform
        self.pop_menu()

    def toggle_favorite(self):
        identifier = self.current["id"] if self.page == "game-details" else self.selected
        if identifier:
            values = self.store.data["favorites"]
            values.remove(identifier) if identifier in values else values.append(identifier)
            self.persist()
        self.pop_menu()

    def settings_options(self):
        return [(tr("Core folder"), lambda: self.folder_prompt("coreDirectory", "/usr/lib/aarch64-linux-gnu/libretro")),
                (tr("Firmware folder"), lambda: self.folder_prompt("firmwareDirectory", str(Path.home() / ".config/retroarch/system")))]

    def folder_prompt(self, key, default):
        def set_path(path):
            if not Path(path).expanduser().is_dir():
                raise ValueError(tr("Folder does not exist"))
            self.store.data["preferences"][key] = str(Path(path).expanduser().resolve())
            self.persist()
            if self.current:
                self.checks = preflight(self.current, self.store.data["preferences"])
        self.prompt(tr("Folder path"), set_path, self.store.data["preferences"].get(key, default))

    @Slot(str)
    def dispatch(self, action):
        if self.engine.running() and not self.menus:
            # Physical B remains a game button; only the dedicated shortcut pauses.
            return
        if self.engine.running() and self.menus and action == "back" and len(self.menus) == 1:
            self.attempt(self.resume_game)
        elif self.page == "game-details" and not self.menus and action == "accept":
            self.detail_menu()
        else:
            super().dispatch(action)
        if (self.engine.running() and not self.source_missing and len(self.menus) == 1
                and self.menus[0]["title"] == tr("Game paused") and self.menus[0]["options"][0]["disabled"]):
            self.refresh_pause_menu()
        self.publish()

    def refresh_pause_menu(self):
        index = self.menus[-1]["index"] if self.menus else 0
        self.pause_menu()
        if self.menus:
            self.menus[-1]["index"] = min(index, len(self.menus[-1]["options"]) - 1)
        self.publish()

    def poll(self):
        super().poll()
        if (self.source_missing and not self.reconnect_checked and self.current
                and self.current["sourceId"] not in self.library.unavailable):
            self.reconnect_checked = True
            try:
                item = self.library.require(self.current["id"])
                if content_hash(item) == self.engine.metadata.get("contentHash"):
                    self.source_missing = False
                    if len(self.menus) == 1 and self.menus[0]["title"] == tr("Game paused"):
                        self.refresh_pause_menu()
            except (OSError, ValueError):
                pass

    def stop_source(self):
        self.source_missing = True
        self.reconnect_checked = False
        if self.engine.running():
            self.engine.pause()
        self.attempt(self.persist)

    def close(self):
        self.engine.close()
        super().close()

    @Slot()
    def requestClose(self):
        if self.engine.running():
            self.engine.pause()
        else:
            super().requestClose()

    @Slot(str)
    def command(self, command):
        if command == "pause-game":
            self.attempt(self.engine.pause)
        else:
            super().command(command)
