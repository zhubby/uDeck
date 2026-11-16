"""
[INPUT]: 依赖共享应用控制器、游戏库、RetroEngine、原生存档与 Wayland 窗口接口。
[OUTPUT]: 提供 EmulatorController、启动预检及原有引擎辅助函数导入。
[POS]: 模拟器应用编排；进程协议由 engine.py 单独承担。
[PROTOCOL]: Update this header on change, then check AGENTS.md
"""

import copy
import hashlib
import json
import re
import shutil
import threading
import time
from pathlib import Path

from PySide6.QtCore import QThreadPool, Slot
from PySide6.QtGui import QGuiApplication

from udeck.apps.common.controller import AppController
from udeck.apps.common.state import atomic_json
from udeck.apps.emulator.browser import EmulatorBrowser
from udeck.apps.emulator.catalog import CoreCatalog, message_lines, probe_core, probe_key
from udeck.apps.emulator.engine import RetroEngine, content_hash
from udeck.apps.emulator.engine import config_quote as config_quote
from udeck.apps.emulator.engine import file_hash as file_hash
from udeck.apps.emulator.engine import stock_controls as stock_controls
from udeck.apps.emulator.game_info import game_info, play_seconds
from udeck.apps.emulator.library import EmulatorLibrary, confined_path, content_dependencies
from udeck.apps.emulator.library_management import EmulatorLibraryManagement
from udeck.apps.emulator.save_management import EmulatorSaveManagement
from udeck.apps.emulator.services import CoreInventoryTask, LaunchTask
from udeck.apps.emulator.settings import EmulatorSettings
from udeck.emulator_saves.store import CoreSaveStore, latest_save
from udeck.emulator_saves.store import SaveStore as SaveStore
from udeck.i18n import Msg, error_text, tr
from udeck.sounds import interaction


def disc_tracks(path):
    names = re.findall(r'^\s*FILE\s+(?:"([^"\n]+)"|(\S+))\s+', Path(path).read_text(errors="replace"), re.M | re.I)
    return [Path(path).parent / (quoted or plain) for quoted, plain in names]


def preflight(item, preferences, executable=None, catalog=None, validate_native=True, cancelled=lambda: False):
    executable = executable or shutil.which("retroarch")
    catalog = catalog or CoreCatalog.discover(preferences)
    system = Path(preferences.get("firmwareDirectory", str(Path.home() / ".config/retroarch/system")))
    missing, optional, dependencies = [], [], []
    core = None
    if not executable:
        missing.append(tr(Msg.RETROARCH_IS_NOT_INSTALLED))
    if not item.get("noContent"):
        path = Path(item["path"])
        try:
            confined_path(path, item.get("platformRoot", path.parent))
            if not path.is_file():
                missing.append(tr(Msg.GAME_SOURCE_IS_DISCONNECTED))
            else:
                dependencies = content_dependencies(path, item.get("platformRoot", path.parent), cancelled)
                missing.extend(tr(Msg.MISSING_DISC_TRACK_NAME, name=p.name) for p in dependencies if not p.is_file())
        except (OSError, ValueError) as error:
            missing.append(error_text(error))
    try:
        core = catalog.resolve(item, require_available=False)
        if not Path(core.path).is_file():
            raise ValueError(tr(Msg.MISSING_CORE_CORE, core=core.id))
        if validate_native and (core.status != "available" or probe_key(core.path) != core.signature):
            core.signature = probe_key(core.path)
            catalog.apply_probe(core.id, probe_core(core.path))
        if core.status != "available":
            missing.append(tr(Msg.CORE_CANNOT_BE_LOADED_CORE_REASON, core=core.id,
                              reason=core.reason or tr(Msg.CHECKING)))
        firmware = catalog.firmware_check(core, item["platform"], system)
        missing.extend(tr(Msg.MISSING_FIRMWARE_NAME, name=name) for name in firmware["required"])
        optional = firmware["optional"]
        if item.get("noContent") and not core.no_content:
            missing.append(tr(Msg.THIS_CORE_REQUIRES_CONTENT))
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


class EmulatorController(EmulatorLibraryManagement, EmulatorSaveManagement, EmulatorSettings, EmulatorBrowser, AppController):
    def create_library(self, app):
        self.catalog = CoreCatalog.discover(self.store.data["preferences"])
        return EmulatorLibrary(self.store, self.catalog, self)

    def __init__(self, directory=None, language_path=None):
        super().__init__("emulator", directory, language_path)
        self.engine = RetroEngine(self)
        self.engine.changed.connect(self.publish)
        self.engine.started.connect(self.game_playing)
        self.engine.paused.connect(self.pause_menu)
        self.engine.saved.connect(self.save_done)
        self.engine.loaded.connect(self.load_done)
        self.engine.failed.connect(self.game_failed)
        self.engine.finished.connect(self.game_exited)
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
        self.init_save_management()
        self.init_library_management()

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
        return [tr(Msg.RECENTLY_PLAYED), tr(Msg.EMU_PLAYLISTS), tr(Msg.FAVORITES)]

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
            raise RuntimeError(tr(Msg.A_GAME_IS_ALREADY_RUNNING))
        self.current = self.library.entry(identifier)
        self.store.data["preferences"].setdefault("entryChoices", {})[self.current["id"]] = self.current.get("entryId", identifier)
        self.cancel_launch()
        self.update_checks()
        self.enter("game-details")

    def extra_state(self):
        save_error = ""
        try:
            slots = self.save_store().manifest() if self.current and (self.engine.store or self.checks.get("coreHash")) else {}
        except (OSError, ValueError) as error:
            slots = {}
            save_error = tr(Msg.CANNOT_READ_SAVES_ERROR, error=error)
        return {"platform": self.platform, "gameStatus": self.engine.status,
                "gameChecks": self.checks, "saveSlots": list(slots),
                "gameBusy": bool(self.engine.pending) or self.launching or bool(self.sync_launch), "sourceMissing": self.source_missing,
                "saveError": save_error, "romRoot": self.library.root_path,
                "coreCount": len(self.catalog.cores), "coresPending": self.cores_pending,
                "scanHints": self.library.reports.get(self.library.root_id, []),
                "selectedGameInfo": game_info(self.selectedItem, self.catalog, self.store.data),
                **self.save_state(),
                **self.browser_state()}

    def start_game(self, resume=False):
        self.save_start_game(resume)

    def _start_game(self, resume=False):
        if self.library_task is not None or self.migration_pending:
            raise RuntimeError(tr(Msg.EMU_LIBRARY_BUSY))
        if self.library.identity_error:
            raise RuntimeError(self.library.identity_error)
        if self.launching or self.engine.running():
            raise RuntimeError(tr(Msg.A_GAME_IS_ALREADY_STARTING_OR_RUNNING))
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
                    self.menu(tr(Msg.RESUME_USES_ANOTHER_CORE), [
                        (tr(Msg.RESTORE_ORIGINAL_CORE), (lambda: self.restore_core(original)) if restore else None,
                         original + " · " + str(metadata.get("coreVersion", ""))),
                        (tr(Msg.START_FRESH), lambda: self.start_game(False)), (tr(Msg.CANCEL), self.pop_menu)],
                        tr(Msg.THE_SAVED_STATE_REQUIRES_ITS_ORIGINAL_CORE_AND_VERSION_YOUR_SAVES_ARE_KEPT))
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
        self.notice = tr(Msg.PREPARING_GAME)
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
            raise ValueError(tr(Msg.THE_GAME_OR_CORE_CHANGED_TRY_AGAIN))
        for path, stamp in self.checks.get("contentStamps", {}).items():
            stat = Path(path).stat()
            if [stat.st_size, stat.st_mtime_ns] != stamp:
                raise ValueError(tr(Msg.THE_FILE_HAS_CHANGED_REFRESH_THE_LIBRARY_BEFORE_OPENING_IT))
        if not self.prepare_save_launch():
            return
        saves = self.save_store()
        if self.launch_resume:
            if not self.checks["savestate"]:
                raise ValueError(tr(Msg.THIS_CORE_DOES_NOT_SUPPORT_SAVE_STATES))
            saves.load("auto", self.checks["contentHash"], self.checks["coreHash"])
        self.acquire_save_session()
        try:
            self.engine.start(item, self.checks, saves, self.launch_resume)
        except Exception:
            self.release_save_session()
            raise
        self.page = "game-running"
        self.source_missing = False
        self.persist()

    def game_playing(self):
        if self.game_started is not None:
            return
        self.game_started = time.monotonic()
        identifier = self.engine.item["id"]
        record = self.store.data["positions"].get(identifier)
        if not isinstance(record, dict):
            record = self.store.data["positions"][identifier] = {}
        record["lastPlayed"] = time.time()
        self.store.remember(identifier)
        self.attempt(self.persist)

    def cancel_launch(self):
        self.launch_generation += 1
        self.launching = False
        self.launch_cancel.set()
        if hasattr(self, "sync_launch"):
            self.sync_launch = None
            self.save_launch_ready = -1

    def require_current(self):
        if self.current.get("noContent"):
            return self.current
        try:
            return self.library.require(self.current.get("entryId", self.current["id"]))
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
            raise RuntimeError(tr(Msg.A_GAME_IS_ALREADY_RUNNING))
        platform = self.catalog.canonical(platform) if platform else next(
            (p for p in core.platforms if self.catalog.enabled(core, p)), None)
        if platform not in core.platforms or not self.catalog.enabled(core, platform):
            raise ValueError(tr(Msg.SELECTED_CORE_IS_UNAVAILABLE_CORE, core=identifier))
        self.current = {"id": "core:" + identifier, "title": core.name, "coreId": identifier,
                        "platform": platform, "noContent": True, "path": "", "format": "", "sourceId": ""}
        self.page = "game-details"
        self.start_game()

    def accept_file_path(self, path):
        path = Path(path)
        source = next((s for s in self.library.sources if s.id == self.library.root_id and Path(s.path) in path.parents), None)
        if not source:
            raise ValueError(tr(Msg.PLACE_THIS_GAME_INSIDE_A_PLATFORM_FOLDER_UNDER_PATH, path=self.library.root_path))
        relative = path.relative_to(source.path)
        platform = self.catalog.platform_for_directory(relative.parts[0]) if len(relative.parts) > 1 else None
        if not platform or not self.catalog.candidates(platform.id, path.suffix):
            raise ValueError(tr(Msg.NO_ENABLED_CORE_SUPPORTS_THIS_PLATFORM_FOLDER_AND_FORMAT))
        confined_path(path, Path(source.path) / relative.parts[0])

    def accept_file_paths(self, paths):
        self.require_library_idle()
        for path in paths:
            self.accept_file_path(path)
        known = {item["path"] for item in self.library.items}
        additions = [path for path in paths if str(path) not in known]
        if additions:
            self.preview_file_entries(additions)

    def uncover_game(self):
        if self.window:
            self.window.showMinimized()
        if self.isolated or not self.window or QGuiApplication.platformName() != "wayland":
            return
        from udeck.windows import WindowService

        windows = WindowService()
        try:
            windows.start()
            for entry in windows.entries():
                if entry.get("appId") == "com.libretro.RetroArch":
                    windows.request(entry["id"], "activate")
                    break
        finally:
            windows.close()

    def pause_game(self):
        if self.engine.status == "playing":
            self.uncover_game()
        self.engine.pause()

    def pause_menu(self):
        if not self.engine.running():
            return
        self.clear_menus()
        self.present.emit()
        options = [
            (tr(Msg.RESUME), self.resume_game if not self.source_missing else None,
             tr(Msg.RECONNECT_THE_SOURCE_FIRST) if self.source_missing else "")]
        if self.engine.metadata.get("savestate", True):
            options.extend([
            (tr(Msg.SAVE_STATE), (lambda: self.slots_menu(False)) if not self.source_missing else None),
            (tr(Msg.LOAD_STATE), (lambda: self.slots_menu(True)) if not self.source_missing else None),
            (tr(Msg.SAVE_AND_RETURN_TO_LIBRARY), self.save_exit if not self.source_missing else None),
            (tr(Msg.RETURN_WITHOUT_SAVING), self.confirm_quit)])
        else:
            options.append((tr(Msg.RETURN_TO_LIBRARY), self.quit_game))
        options.extend([(tr(Msg.CONTROLS), self.controls_menu), (tr(Msg.SETTINGS), self.settings)])
        self.menu(tr(Msg.GAME_PAUSED), options)

    def resume_game(self):
        if self.source_missing:
            raise OSError(tr(Msg.THE_SOURCE_IS_DISCONNECTED))
        self.engine.resume()
        self.clear_menus()
        self.uncover_game()

    def quit_game(self):
        self.engine.quit()
        # Wayland may suspend frame delivery to a fully covered RetroArch window,
        # blocking its command loop. Uncover it until game_exited presents us again.
        self.uncover_game()

    def slots_menu(self, load):
        slots = self.save_store().manifest()
        options = []
        for slot in ("1", "2", "3"):
            exists = slot in slots
            options.append((tr(Msg.SLOT_SLOT, slot=slot),
                            (lambda s=slot: self.confirm_slot(s, load)) if exists or not load else None,
                            tr(Msg.SAVED) if exists else tr(Msg.EMPTY)))
        self.menu(tr(Msg.LOAD_STATE) if load else tr(Msg.SAVE_STATE), options)

    def confirm_slot(self, slot, load):
        self.menu(tr(Msg.LOAD_THIS_STATE_PROMPT) if load else tr(Msg.REPLACE_THIS_SLOT_PROMPT) if slot in self.save_store().manifest() else tr(Msg.SAVE_IN_THIS_SLOT_PROMPT),
                  [(tr(Msg.CONFIRM), lambda: self.slot_action(slot, load)), (tr(Msg.CANCEL), self.pop_menu)],
                  tr(Msg.LOADING_REPLACES_PROGRESS_MADE_SINCE_THE_SAVED_STATE) if load else "")

    def slot_action(self, slot, load):
        self.require_current()
        self.pop_menu()
        self.engine.load(slot) if load else self.engine.save(slot)
        self.uncover_game()

    def save_done(self, slot):
        self.record_running_save(slot)
        self.notice = tr(Msg.STATE_SAVED)
        if self.exit_after_save:
            self.exit_after_save = False
            self.quit_game()
        else:
            self.pause_menu()

    def load_done(self):
        self.notice = tr(Msg.STATE_LOADED)
        if self.source_missing:
            self.pause_menu()
        else:
            self.attempt(self.resume_game)

    def save_exit(self):
        self.require_current()
        self.engine.save("auto")
        self.exit_after_save = True
        self.uncover_game()

    def confirm_quit(self):
        self.menu(tr(Msg.RETURN_WITHOUT_SAVING_PROMPT), [(tr(Msg.CONFIRM), self.quit_game), (tr(Msg.CANCEL), self.pop_menu)])

    def controls_menu(self):
        self.menu(tr(Msg.CONTROLS), [(tr(Msg.BACK), self.pop_menu)],
                  tr(Msg.GAMEPLAY_INPUT_INSTRUCTIONS))

    def game_failed(self, text):
        self.exit_after_save = False
        self.error = tr(Msg.EMULATOR_ERROR_ERROR, error=text)
        self.present.emit()
        self.publish()

    def game_exited(self, code):
        self.record_exited_sram(code)
        self.exit_after_save = False
        self.clear_menus()
        self.page = "game-details"
        if self.game_started is not None:
            record = self.store.data["positions"][self.engine.item["id"]]
            record["seconds"] = play_seconds(record.get("seconds")) + max(0, time.monotonic() - self.game_started)
            record["lastPlayed"] = time.time()
            self.game_started = None
        self.attempt(self.persist)
        self.present.emit()

    def context(self):
        if self.page == "game-details":
            self.detail_menu()
        elif self.engine.running():
            self.pause_game()
        else:
            options = [] if self.tab == 1 and self.platform == "All" else [
                (tr(Msg.TOGGLE_FAVORITE), self.toggle_favorite)]
            if self.tab == 1 and self.platform != "All":
                options.extend([(tr(Msg.EMU_DOWNLOAD_LIST_IMAGES), self.download_list_images),
                                (tr(Msg.CHOOSE_CORE), self.playlist_core_menu)])
            if not (self.tab == 1 and self.platform == "All") and self.selected:
                options.append((tr(Msg.EMU_DOWNLOAD_GAME_IMAGES), self.download_game_images))
            self.menu(tr(Msg.EMULATOR_ACTIONS), options + [
                       (tr(Msg.SEARCH), lambda: self.prompt(tr(Msg.SEARCH_LIBRARY), self.search, self.filter)),
                       (tr(Msg.CLEAR_SEARCH), lambda: self.search("")),
                       (tr(Msg.BROWSE_ROM_ROOT), self.show_rom_root),
                       (tr(Msg.REFRESH_LIBRARY), self.refresh)],
                       message_lines(self.library.reports.get(self.library.root_id, [])))

    def detail_menu(self):
        self.menu(self.current["title"], [
            (tr(Msg.CONTINUE), lambda: self.start_game(True)),
            (tr(Msg.RESTART), lambda: self.start_game()),
            (tr(Msg.CHOOSE_CORE), self.choose_game_core),
            (tr(Msg.EMU_SELECT_PLATFORM), self.select_game_platform),
            (tr(Msg.EMU_PREVIEW_IMAGES), self.preview_images),
            (tr(Msg.EMU_DOWNLOAD_GAME_IMAGES), self.download_game_images),
            (tr(Msg.EMU_SAVE_MANAGEMENT), self.save_management),
            (tr(Msg.TOGGLE_FAVORITE), self.toggle_favorite), (tr(Msg.SETTINGS), self.settings)],
            message_lines(self.checks.get("errors", [])))

    def toggle_favorite(self):
        if self.page == "library" and self.tab == 1 and self.platform == "All":
            return
        identifier = self.current["id"] if self.page == "game-details" else self.library.entry(self.selected)["id"]
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
        if self.library_task is not None:
            if action == "back":
                self.cancel_library_operation()
            return
        if self.launching and action == "accept":
            return
        if self.menus and self.menus[-1].get("picker") and action == "left":
            parent = self.menus[-1].get("pickerParent")
            if parent:
                self.attempt(parent)
            self.publish()
            return
        if not self.menus and self.page == "library" and action == "accept" and not self.rows():
            self.search("") if self.filter else self.settings()
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
                and self.menus[0]["title"] == tr(Msg.GAME_PAUSED) and self.menus[0]["options"][0]["disabled"]):
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
        self.save_poll()
        if (self.source_missing and not self.reconnect_checked and self.current
                and self.current["sourceId"] not in self.library.unavailable):
            self.reconnect_checked = True
            try:
                item = self.library.require(self.current.get("entryId", self.current["id"]))
                if content_hash(item) == self.engine.metadata.get("contentHash"):
                    self.source_missing = False
                    if len(self.menus) == 1 and self.menus[0]["title"] == tr(Msg.GAME_PAUSED):
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
        self.close_library_management()
        self.cancel_launch()
        self.core_generation += 1
        self.core_cancel.set()
        self.engine.close()
        self.close_save_management()
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
            self.attempt(self.pause_game)
        elif command in ("core-management", "rom-library", "rom-root"):
            self.attempt({"core-management": self.core_management, "rom-library": self.show_rom_root,
                          "rom-root": self.rom_picker}[command])
        else:
            super().command(command)
        self.publish()
