"""External RetroArch ownership, preflight and atomically published save groups."""

import copy
import hashlib
import json
import os
import re
import shutil
import tempfile
import threading
import time
import uuid
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, QThreadPool, QTimer, Signal, Slot

from udeck.apps.common.controller import AppController
from udeck.apps.common.state import atomic_json
from udeck.apps.emulator.catalog import CoreCatalog, message_lines, probe_core, probe_key
from udeck.apps.emulator.library import EmulatorLibrary, confined_path, content_dependencies
from udeck.apps.emulator.services import CoreInventoryTask, LaunchTask
from udeck.apps.emulator.settings import EmulatorSettings
from udeck.i18n import error_text, tr
from udeck.sounds import interaction


def file_hash(path, cancelled=lambda: False):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            if cancelled():
                raise OSError(tr("Scan cancelled"))
            digest.update(chunk)
    return digest.hexdigest()


def disc_tracks(path):
    names = re.findall(r'^\s*FILE\s+(?:"([^"\n]+)"|(\S+))\s+', Path(path).read_text(errors="replace"), re.M | re.I)
    return [Path(path).parent / (quoted or plain) for quoted, plain in names]


def content_hash(item, cancelled=lambda: False):
    if item.get("noContent"):
        return hashlib.sha256(("no-content:" + item["coreId"]).encode()).hexdigest()
    base = file_hash(item["path"], cancelled)
    if Path(item["path"]).suffix.lower() not in (".cue", ".gdi", ".m3u"):
        return base
    digest = hashlib.sha256(base.encode())
    for track in content_dependencies(item["path"], item.get("platformRoot", Path(item["path"]).parent), cancelled):
        digest.update(file_hash(track, cancelled).encode())
    return digest.hexdigest()


def preflight(item, preferences, executable=None, catalog=None, validate_native=True, cancelled=lambda: False):
    executable = executable or shutil.which("retroarch")
    catalog = catalog or CoreCatalog.discover(preferences)
    system = Path(preferences.get("firmwareDirectory", str(Path.home() / ".config/retroarch/system")))
    missing, optional, dependencies = [], [], []
    core = None
    if not executable:
        missing.append(tr("RetroArch is not installed"))
    if not item.get("noContent"):
        path = Path(item["path"])
        try:
            confined_path(path, item.get("platformRoot", path.parent))
            if not path.is_file():
                missing.append(tr("Game source is disconnected"))
            else:
                dependencies = content_dependencies(path, item.get("platformRoot", path.parent), cancelled)
                missing.extend(tr("Missing disc track: {name}", name=p.name) for p in dependencies if not p.is_file())
        except (OSError, ValueError) as error:
            missing.append(error_text(error))
    try:
        core = catalog.resolve(item, require_available=False)
        if not Path(core.path).is_file():
            raise ValueError(tr("Missing core: {core}", core=core.id))
        if validate_native and (core.status != "available" or probe_key(core.path) != core.signature):
            core.signature = probe_key(core.path)
            catalog.apply_probe(core.id, probe_core(core.path))
        if core.status != "available":
            missing.append(tr("Core cannot be loaded: {core} · {reason}", core=core.id,
                              reason=core.reason or tr("Checking…")))
        firmware = catalog.firmware_check(core, item["platform"], system)
        missing.extend(tr("Missing firmware: {name}", name=name) for name in firmware["required"])
        optional = firmware["optional"]
        if item.get("noContent") and not core.no_content:
            missing.append(tr("This core requires content"))
    except (OSError, ValueError) as error:
        missing.append(error_text(error))
    checks = {"ready": not missing, "errors": missing, "core": core.path if core else "",
              "coreId": core.id if core else "", "coreHash": core.core_hash if core else "",
              "libraryName": core.library_name if core else "",
              "coreSignature": core.signature if core else "", "optionalFirmware": optional,
              "savestate": core.savestate if core else False, "firmware": str(system),
              "executable": executable or "", "noContent": bool(item.get("noContent")),
              "platform": catalog.canonical(item["platform"]), "content": item.get("path", "")}
    if validate_native and checks["ready"]:
        checks["contentHash"] = content_hash(item, cancelled)
        checks["contentStamps"] = {str(p): [p.stat().st_size, p.stat().st_mtime_ns]
                                  for p in dependencies + ([Path(item["path"])] if not item.get("noContent") else [])}
    return checks


class SaveStore:
    def __init__(self, root):
        self.root = Path(root)
        self.sram_root = self.root / "sram"

    def prepare_sram(self):
        self.sram_root.mkdir(parents=True, exist_ok=True, mode=0o700)

    def inspect(self, slot):
        name = self.manifest().get(str(slot))
        if not isinstance(name, str) or not re.fullmatch(r"[0-9a-f]{32}", name):
            raise ValueError(tr("This save slot is empty"))
        value = json.loads((self.root / name / "metadata.json").read_text())
        if not isinstance(value, dict):
            raise ValueError(tr("The save state is damaged"))
        return value

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
            slots = SaveStore.manifest(self)
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


class CoreSaveStore(SaveStore):
    def __init__(self, game_root, core_id, core_hash):
        if not re.fullmatch(r"[A-Za-z0-9_-]+", core_id) or not re.fullmatch(r"[0-9a-f]{64}", core_hash):
            raise ValueError(tr("Invalid core save identity"))
        self.game_root, self.core_id, self.core_hash = Path(game_root), core_id, core_hash
        super().__init__(self.game_root / "cores" / core_id / core_hash)
        self.sram_root = self.root.parent / "sram"


def latest_save(game_root, slot="auto"):
    root = Path(game_root)
    candidates = []
    for directory in root.glob("cores/*/*"):
        if directory.name == "sram":
            continue
        try:
            store = SaveStore(directory)
            metadata = store.inspect(slot)
            candidates.append((float(metadata.get("created", 0)), store, metadata))
        except (OSError, ValueError, TypeError):
            continue
    return max(candidates, key=lambda x: x[0])[1:] if candidates else (None, None)


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
        core_hash = checks.get("coreHash") or file_hash(checks["core"])
        self.metadata = {"contentHash": checks.get("contentHash") or content_hash(item), "coreHash": core_hash,
                         "game": item["id"], "core": checks["core"], "coreId": checks.get("coreId", ""),
                         "coreVersion": core_hash[:16], "savestate": checks.get("savestate", True)}
        self.runtime = tempfile.TemporaryDirectory(prefix="udeck-game-")
        root = Path(self.runtime.name)
        save_store.prepare_sram()
        sram = save_store.sram_root
        # RetroArch uses retro_system_info.library_name when there is no content.
        basename = (Path(item["path"]).stem if item.get("path") else
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
        options.update(stock_controls())
        config = root / "udeck.cfg"
        config.write_text("\n".join(f"{key} = {value}" for key, value in options.items()) + "\n")
        self.resume_on_start = resume
        self.item = item
        self.status, self.log, self.stdout, self.stderr, self.pending = "starting", "", "", "", None
        self.want_pause = False
        self.deadline = time.monotonic() + 20
        self.process.setProgram(checks["executable"])
        arguments = ["--verbose", "--appendconfig", str(config), "-L", checks["core"]]
        if not item.get("noContent"):
            arguments.append(item["path"])
        self.process.setArguments(arguments)
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
        if not self.metadata.get("savestate", True):
            raise RuntimeError(tr("This core does not support save states"))
        if self.pending or self.status != "paused":
            raise RuntimeError(tr("Pause the game and wait for the current operation"))
        stat = self.state_path.stat() if self.state_path.exists() else None
        self.pending = {"kind": "save", "slot": str(slot), "old": (stat.st_mtime_ns, stat.st_size) if stat else None,
                        "deadline": time.monotonic() + 15}
        self.send("SAVE_STATE")

    def load(self, slot):
        try:
            if not self.metadata.get("savestate", True):
                raise RuntimeError(tr("This core does not support save states"))
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


class EmulatorController(EmulatorSettings, AppController):
    def create_library(self, app):
        self.catalog = CoreCatalog.discover(self.store.data["preferences"])
        return EmulatorLibrary(self.store, self.catalog, self)

    def __init__(self, directory=None, language_path=None):
        super().__init__("emulator", directory, language_path)
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
        self.core_generation, self.launch_generation = 0, 0
        self.core_cancel = threading.Event()
        self.core_tasks, self.launch_tasks = {}, {}
        self.cores_pending = 0
        self.launching = False
        self.launch_item = None
        self.launch_cancel = threading.Event()
        self.tab = 0 if self.store.data["recent"] else 1

    def start(self):
        self.refresh_catalog(force=False)
        super().start()

    def refresh_catalog(self, force=True):
        self.core_cancel.set()
        self.core_cancel = threading.Event()
        self.core_generation += 1
        cache = {}
        if not force:
            try:
                value = json.loads(self.core_cache_path().read_text())
                cache = value if isinstance(value, dict) else {}
            except (OSError, ValueError):
                pass
        task = CoreInventoryTask(self.core_generation, copy.deepcopy(self.store.data["preferences"]),
                                 cache, self.core_cancel)
        task.signals.discovered.connect(self.catalog_discovered)
        task.signals.progress.connect(self.core_progress)
        task.signals.done.connect(self.catalog_finished)
        self.core_tasks[self.core_generation] = task
        self.cores_pending = len(self.catalog.cores)
        QThreadPool.globalInstance().start(task)
        self.publish()

    def core_cache_path(self):
        return self.store.path.parent / "emulator-core-cache.json"

    @Slot(int, object)
    def catalog_discovered(self, generation, catalog):
        if generation != self.core_generation:
            return
        catalog.preferences = self.store.data["preferences"]
        self.catalog = self.library.catalog = catalog
        self.cores_pending = sum(c.status == "unverified" for c in catalog.cores.values())
        self.update_checks()
        self.refresh_core_menu()
        self.publish()

    @Slot(int, str, object)
    def core_progress(self, generation, identifier, result):
        if generation != self.core_generation:
            return
        self.catalog.apply_probe(identifier, result)
        self.cores_pending = sum(c.status == "unverified" for c in self.catalog.cores.values())
        if self.current and not self.engine.running():
            self.update_checks()
        self.refresh_core_menu(identifier)
        self.publish()

    @Slot(int, object)
    def catalog_finished(self, generation, cache):
        self.core_tasks.pop(generation, None)
        if generation != self.core_generation:
            return
        self.cores_pending = 0
        self.attempt(lambda: atomic_json(self.core_cache_path(), cache))
        self.library.refresh()
        self.update_checks()
        self.refresh_core_menu()
        self.publish()

    def update_checks(self):
        if self.current and not self.engine.running():
            self.checks = preflight(self.current, self.store.data["preferences"],
                                    catalog=self.catalog, validate_native=False)

    def tabs(self):
        return [tr("Recently played"), tr("All platforms"), tr("Favorites")]

    def rows(self):
        rows = super().rows()
        rows = [r for r in rows if r["sourceId"] == self.library.root_id]
        if self.tab == 0:
            order = self.store.data["recent"]
            rows = [r for r in rows if r["id"] in order]
            rows.sort(key=lambda r: order.index(r["id"]))
        elif self.tab == 2:
            rows = [r for r in rows if r["id"] in self.store.data["favorites"]]
        if self.platform != "All":
            rows = [r for r in rows if self.catalog.canonical(r["platform"]) == self.platform]
        return [{**r, "subtitle": self.catalog.platforms[self.catalog.canonical(r["platform"])].title
                 if self.catalog.canonical(r["platform"]) in self.catalog.platforms else r["platform"]} for r in rows]

    def game_root(self):
        identifier = self.current["id"]
        if not re.fullmatch(r"[A-Za-z0-9:_-]+", identifier):
            identifier = hashlib.sha256(identifier.encode()).hexdigest()
        return self.store.path.parent / "emulator-saves" / identifier

    def save_store(self):
        if self.engine.running() and self.engine.store:
            return self.engine.store
        return CoreSaveStore(self.game_root(), self.checks.get("coreId", ""), self.checks.get("coreHash", ""))

    def open_item(self, identifier):
        if self.engine.running():
            raise RuntimeError(tr("A game is already running"))
        self.current = self.library.require(identifier)
        self.cancel_launch()
        self.update_checks()
        self.enter("game-details")

    def extra_state(self):
        save_error = ""
        try:
            slots = self.save_store().manifest() if self.current and (self.engine.store or self.checks.get("coreHash")) else {}
        except (OSError, ValueError) as error:
            slots = {}
            save_error = tr("Cannot read saves: {error}", error=error)
        return {"platform": self.platform, "gameStatus": self.engine.status,
                "gameChecks": self.checks, "saveSlots": list(slots),
                "gameBusy": bool(self.engine.pending) or self.launching, "sourceMissing": self.source_missing,
                "saveError": save_error, "romRoot": self.library.root_path,
                "coreCount": len(self.catalog.cores), "coresPending": self.cores_pending,
                "scanHints": self.library.reports.get(self.library.root_id, []),
                "emptyHint": tr("ROM root: {path}\nUse platform folders: gba/ · psp/ · psx/ · dreamcast/",
                                path=self.library.root_path)}

    def start_game(self, resume=False):
        if self.launching or self.engine.running():
            raise RuntimeError(tr("A game is already starting or running"))
        item = self.require_current()
        if resume:
            _, metadata = latest_save(self.game_root())
            if metadata:
                original = metadata.get("coreId") or Path(metadata.get("core", "")).name.removesuffix("_libretro.so")
                try:
                    selected = self.catalog.resolve(item)
                except ValueError:
                    selected = None
                saved_core = self.catalog.cores.get(original)
                if (not selected or selected.id != original or selected.core_hash != metadata.get("coreHash")):
                    restore = saved_core and saved_core.status == "available" and saved_core.core_hash == metadata.get("coreHash")
                    self.menu(tr("Resume uses another core"), [
                        (tr("Restore original core"), (lambda: self.restore_core(original)) if restore else None,
                         original + " · " + str(metadata.get("coreVersion", ""))),
                        (tr("Start fresh"), lambda: self.start_game(False)), (tr("Cancel"), self.pop_menu)],
                        tr("The saved state requires its original core and version. Your saves are kept."))
                    return
            else:
                resume = False
        self.launch_generation += 1
        self.launching, self.launch_item, self.launch_resume = True, dict(item), resume
        self.launch_cancel = threading.Event()
        task = LaunchTask(self.launch_generation, dict(item), copy.deepcopy(self.store.data["preferences"]),
                          copy.deepcopy(self.catalog), self.launch_cancel)
        task.signals.done.connect(self.launch_finished)
        self.launch_tasks[self.launch_generation] = task
        QThreadPool.globalInstance().start(task)
        self.clear_menus()
        self.notice = tr("Preparing game…")
        self.publish()

    def restore_core(self, identifier):
        prefs = self.store.data["preferences"]
        prefs.setdefault("coreEnabled", {})[identifier] = True
        prefs.setdefault("gameCores", {})[self.current["id"]] = identifier
        self.persist()
        self.library.refresh()
        self.start_game(True)

    @Slot(int, object)
    def launch_finished(self, generation, checks):
        self.launch_tasks.pop(generation, None)
        if generation != self.launch_generation:
            return
        self.launching = False
        self.checks, self.notice = checks, ""
        if not checks["ready"]:
            self.error = message_lines(checks["errors"])
            self.publish()
            return
        self.attempt(self.complete_launch)
        self.publish()

    def complete_launch(self):
        item = self.require_current()
        if item["id"] != self.launch_item["id"] or probe_key(self.checks["core"]) != self.checks["coreSignature"]:
            raise ValueError(tr("The game or core changed. Try again."))
        for path, stamp in self.checks.get("contentStamps", {}).items():
            stat = Path(path).stat()
            if [stat.st_size, stat.st_mtime_ns] != stamp:
                raise ValueError(tr("The file has changed. Refresh the library before opening it."))
        saves = self.save_store()
        if self.launch_resume:
            if not self.checks["savestate"]:
                raise ValueError(tr("This core does not support save states"))
            saves.load("auto", self.checks["contentHash"], self.checks["coreHash"])
        self.engine.start(item, self.checks, saves, self.launch_resume)
        self.page = "game-running"
        self.game_started = time.monotonic()
        self.source_missing = False
        self.store.remember(item["id"])
        self.persist()

    def cancel_launch(self):
        self.launch_generation += 1
        self.launching = False
        self.launch_cancel.set()

    def require_current(self):
        if self.current.get("noContent"):
            return self.current
        try:
            return self.library.require(self.current["id"])
        except OSError:
            # Keep an already opened detail/resume request after a core switch.
            # The original source and file identity must still match.
            source = next((s for s in self.library.sources if s.id == self.current.get("sourceId")), None)
            if not source or not source.available():
                raise
            confined_path(self.current["path"], source.path)
            path = confined_path(self.current["path"], self.current.get("platformRoot", source.path))
            stat = path.stat()
            if [stat.st_size, stat.st_mtime_ns] != self.current["stamp"]:
                raise
            return self.current

    def run_core(self, identifier, platform=None):
        core = self.catalog.cores[identifier]
        if self.engine.running():
            raise RuntimeError(tr("A game is already running"))
        platform = self.catalog.canonical(platform) if platform else next(
            (p for p in core.platforms if self.catalog.enabled(core, p)), None)
        if platform not in core.platforms or not self.catalog.enabled(core, platform):
            raise ValueError(tr("Selected core is unavailable: {core}", core=identifier))
        self.current = {"id": "core:" + identifier, "title": core.name, "coreId": identifier,
                        "platform": platform, "noContent": True, "path": "", "format": "", "sourceId": ""}
        self.page = "game-details"
        self.start_game()

    def accept_file_path(self, path):
        path = Path(path)
        source = next((s for s in self.library.sources if s.id == self.library.root_id and Path(s.path) in path.parents), None)
        if not source:
            raise ValueError(tr("Place this game inside a platform folder under {path}", path=self.library.root_path))
        relative = path.relative_to(source.path)
        platform = self.catalog.platform_for_directory(relative.parts[0]) if len(relative.parts) > 1 else None
        if not platform or not self.catalog.candidates(platform.id, path.suffix):
            raise ValueError(tr("No enabled core supports this platform folder and format"))
        confined_path(path, Path(source.path) / relative.parts[0])
        if platform.mode in ("manual", "dos"):
            entries = self.store.data["preferences"].setdefault("engineEntries", [])
            if str(path) not in entries:
                entries.append(str(path))
                self.persist()
                self.library.refresh()

    def pause_menu(self):
        if not self.engine.running():
            return
        self.clear_menus()
        self.present.emit()
        options = [
            (tr("Resume"), self.resume_game if not self.source_missing else None,
             tr("Reconnect the source first") if self.source_missing else "")]
        if self.engine.metadata.get("savestate", True):
            options.extend([
            (tr("Save state"), (lambda: self.slots_menu(False)) if not self.source_missing else None),
            (tr("Load state"), (lambda: self.slots_menu(True)) if not self.source_missing else None),
            (tr("Save and return to library"), self.save_exit if not self.source_missing else None),
            (tr("Return without saving"), self.confirm_quit)])
        else:
            options.append((tr("Return to library"), self.engine.quit))
        options.extend([(tr("Controls"), self.controls_menu), (tr("Settings"), self.settings)])
        self.menu(tr("Game paused"), options)

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
        self.require_current()
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
        self.require_current()
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
            self.menu(tr("Emulator actions"), [(tr("Platform filter"), self.platform_menu),
                       (tr("Toggle favorite"), self.toggle_favorite),
                       (tr("Search"), lambda: self.prompt(tr("Search library"), self.search, self.filter)),
                       (tr("Browse ROM root"), self.show_rom_root),
                       (tr("Refresh library"), self.refresh)],
                       message_lines(self.library.reports.get(self.library.root_id, [])))

    def detail_menu(self):
        self.menu(self.current["title"], [
            (tr("Continue"), lambda: self.start_game(True)),
            (tr("Restart"), lambda: self.start_game()),
            (tr("Choose core"), self.choose_game_core),
            (tr("Toggle favorite"), self.toggle_favorite), (tr("Settings"), self.settings)],
            message_lines(self.checks.get("errors", [])))

    def platform_menu(self):
        platforms = [p for p in self.catalog.platforms.values() if self.catalog.platform_cores(p.id)
                     or any(self.catalog.canonical(i["platform"]) == p.id for i in self.library.items)]
        self.menu(tr("Platform filter"), [(tr("All"), lambda: self.set_platform("All"))] +
                  [(p.title, lambda p=p: self.set_platform(p.id), p.directory + "/")
                   for p in sorted(platforms, key=lambda p: p.title.casefold())])

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

    def back(self):
        self.cancel_launch()
        super().back()

    @Slot(int)
    def setTab(self, index):
        self.cancel_launch()
        super().setTab(index)

    @Slot(str)
    @interaction
    def dispatch(self, action):
        if self.launching and action == "accept":
            return
        if self.menus and self.menus[-1].get("picker") and action == "left":
            parent = self.menus[-1].get("pickerParent")
            if parent:
                self.attempt(parent)
            self.publish()
            return
        if not self.menus and self.page == "library" and action == "accept" and not self.rows():
            self.settings()
            return
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
        self.cancel_launch()
        self.core_generation += 1
        self.core_cancel.set()
        self.engine.close()
        super().close()

    @Slot()
    def requestClose(self):
        if self.engine.running():
            self.engine.pause()
        else:
            super().requestClose()

    @Slot(str)
    @interaction
    def command(self, command):
        if command == "pause-game":
            self.attempt(self.engine.pause)
        elif command in ("core-management", "rom-library", "rom-root"):
            self.attempt({"core-management": self.core_management, "rom-library": self.show_rom_root,
                          "rom-root": self.rom_picker}[command])
        else:
            super().command(command)
        self.publish()
