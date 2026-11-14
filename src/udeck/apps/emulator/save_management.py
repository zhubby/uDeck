"""Button-first native saves and a non-blocking bridge to cloud history."""

import copy
import re
import subprocess
import time
import uuid
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QThreadPool, Slot

from udeck.emulator_saves.client import SaveCloudClient, SaveTask
from udeck.emulator_saves.native import SaveManager
from udeck.i18n import Msg, tr


class EmulatorSaveManagement:
    def init_save_management(self):
        self.save_manager = SaveManager(self.store.path.parent)
        self.save_cloud = SaveCloudClient(self.store.path.parent, self)
        self.save_cloud.changed.connect(self.save_cloud_result)
        self.save_jobs = {}
        self.save_pool = QThreadPool(self)
        self.save_pool.setMaxThreadCount(1)
        self.save_closed = False
        self.running_save_context = None
        self.running_save_session = None
        self.save_launch_ready = -1
        self.sync_launch = None
        self.save_configuration_generation = 0

    def save_context(self, item=None, checks=None):
        from .controller import content_hash

        item = item if item is not None else self.current
        checks = checks if checks is not None else self.checks
        if not item or not checks.get("coreId") or not checks.get("coreHash"):
            raise ValueError(tr(Msg.EMU_SAVE_CORE_NEEDED))
        return {"gameId": item["id"], "title": item["title"], "platform": checks.get("platform") or item["platform"].lower(),
                "contentHash": checks.get("contentHash") or content_hash(item),
                "coreId": checks["coreId"], "coreHash": checks["coreHash"],
                "basename": Path(item["path"]).stem if item.get("path") else checks.get("libraryName") or checks["coreId"]}

    def save_work(self, operation, done=None, *, contextual=True, on_error=None, internal=False):
        if self.save_closed:
            return
        if self.save_jobs and not internal:
            raise RuntimeError(tr(Msg.EMU_SAVE_BUSY))
        item, checks = copy.deepcopy(self.current), copy.deepcopy(self.checks)
        owner = (item or {}).get("id") if contextual else None

        def work():
            context = self.save_context(item, checks) if contextual else None
            return operation(context) if contextual else operation()

        identifier = uuid.uuid4().hex
        task = SaveTask(identifier, work)
        self.save_jobs[identifier] = (task, done, on_error, owner, internal)
        task.signals.done.connect(self.save_work_done)
        self.save_pool.start(task)
        if not internal:
            self.notice = tr(Msg.EMU_SAVE_WORKING)
        self.publish()

    @Slot(str, object, object)
    def save_work_done(self, identifier, result, error):
        job = self.save_jobs.pop(identifier, None)
        if not job or self.save_closed:
            return
        _, done, on_error, owner, internal = job
        if owner and owner != (self.current or {}).get("id") and not internal:
            return
        if error:
            if on_error:
                self.attempt(lambda: on_error(error))
            else:
                self._save_failed(error)
        elif done:
            self.attempt(lambda: done(result))
        self.publish()

    def save_state(self):
        state = self.save_cloud.state
        phase = state.get("phase", "disabled")
        key = {"disabled": Msg.EMU_SAVE_DISABLED, "idle": Msg.EMU_SAVE_IDLE,
               "syncing": Msg.EMU_SAVE_SYNCING, "error": Msg.EMU_SAVE_ERROR,
               "conflict": Msg.EMU_SAVE_CONFLICT_STATUS}.get(phase, Msg.EMU_SAVE_STATUS)
        return {"saveSync": state, "saveManagementBusy": bool(self.save_jobs), "saveStatus": tr(key)}

    def save_management(self):
        running = self.engine.running()
        self.menu(tr(Msg.EMU_SAVE_MANAGEMENT), [
            (tr(Msg.EMU_SAVE_IMPORT), self.save_import_picker if not running else None),
            (tr(Msg.EMU_SAVE_EXPORT), self.save_export_menu if not running else None),
            (tr(Msg.EMU_SAVE_BACKUP), self.save_backup_game if not running else None),
            (tr(Msg.EMU_SAVE_HISTORY), self.save_history),
            (tr(Msg.CHOOSE_CORE), self.choose_game_core if not running else None),
            (tr(Msg.EMU_SAVE_SETTINGS), self.save_settings)],
            tr(Msg.EMU_SAVE_GAME_RUNNING) if running else "")

    def save_import_picker(self):
        self.path_picker(self.library.root_path, self.save_import_confirm, file_filter=lambda path:
                         bool(re.search(r"\.(?:state(?:\d+|\.auto)?|srm|rtc)$", path.name, re.I)))

    def save_import_confirm(self, path, slot=None):
        if self.engine.running():
            raise RuntimeError(tr(Msg.EMU_SAVE_GAME_RUNNING))
        is_state = bool(re.search(r"\.state(?:\d+|\.auto)?$", path, re.I))
        if is_state and slot is None:
            self.menu(tr(Msg.EMU_SAVE_CHOOSE_TARGET), [
                (tr(Msg.SLOT_SLOT, slot=s), lambda s=s: self.save_import_confirm(path, s)) for s in ("1", "2", "3")
            ] + [(tr(Msg.EMU_SAVE_AUTO), lambda: self.save_import_confirm(path, "auto"))])
            return
        label = tr(Msg.EMU_SAVE_AUTO) if slot == "auto" else tr(Msg.SLOT_SLOT, slot=slot) if is_state else tr(Msg.EMU_SAVE_SRAM)
        self.menu(tr(Msg.EMU_SAVE_IMPORT_CONFIRM), [
            (tr(Msg.CONFIRM), lambda: self.save_work(
                lambda ctx: self.save_manager.import_native(ctx, path, slot=slot or "1", confirmed=True),
                lambda _: self.save_finished(Msg.EMU_SAVE_IMPORTED))),
            (tr(Msg.CANCEL), self.pop_menu)],
            tr(Msg.EMU_SAVE_IMPORT_NOTICE, game=self.current["title"], core=self.checks.get("coreId", ""), slot=label, path=path), body_lines=10)

    def save_finished(self, message):
        self.clear_menus()
        self.notice = tr(message)
        self.save_management() if self.current else self.save_settings()
        if self.save_cloud.state["enabled"]:
            self.save_cloud.request("SyncNow")

    def save_export_menu(self):
        def loaded(slots):
            options = [(tr(Msg.EMU_SAVE_AUTO) if slot == "auto" else tr(Msg.SLOT_SLOT, slot=slot),
                        lambda s=slot: self.save_export_picker("state", s)) for slot in slots]
            options.append((tr(Msg.EMU_SAVE_SRAM), lambda: self.save_export_picker("sram", "")))
            self.menu(tr(Msg.EMU_SAVE_EXPORT), options)
        self.save_work(lambda ctx: list(self.save_manager.store(ctx).manifest()), loaded)

    def save_export_picker(self, kind, slot):
        self.path_picker(str(Path.home()), lambda path: self.save_export(path, kind, slot))

    def save_export(self, path, kind, slot, overwrite=False):
        def failed(error):
            if not isinstance(error, FileExistsError):
                raise error
            self.menu(tr(Msg.EMU_SAVE_EXPORT_REPLACE), [
                (tr(Msg.CONFIRM), lambda: self.save_export(path, kind, slot, True)),
                (tr(Msg.CANCEL), self.pop_menu)], tr(Msg.EMU_SAVE_EXPORT_NOTICE, path=path), body_lines=10)
        self.save_work(lambda ctx: self.save_manager.export_native(ctx, path, kind=kind, slot=slot, overwrite=overwrite),
                       lambda _: self.save_finished(Msg.EMU_SAVE_EXPORTED), on_error=failed)

    def save_backup_game(self):
        self.save_work(self.save_manager.backup, lambda _: self.save_finished(Msg.EMU_SAVE_BACKED_UP))

    def save_backup_all(self, on_complete=None):
        def complete(result):
            if result["errors"]:
                raise OSError("\n".join(result["errors"]))
            self.notice = tr(Msg.EMU_SAVE_BACKUP_SUMMARY, count=result["backedUp"], deferred=", ".join(result["deferred"]) or "0")
            if on_complete:
                on_complete()
            elif self.save_cloud.state["enabled"]:
                self.save_cloud.request("SyncNow")
        # Register pre-existing current-library saves, not just games launched
        # since this feature was installed.
        items, catalog = copy.deepcopy(self.library.items), copy.deepcopy(self.catalog)
        def all_games():
            from .controller import content_hash, file_hash
            deferred = []
            for item in items:
                game_root = self.save_manager.root / "emulator-saves" / item["id"] / "cores"
                if not game_root.is_dir():
                    continue
                try:
                    identity = content_hash(item)
                except (OSError, ValueError):
                    deferred.append(item["title"])
                    continue
                for core_root in game_root.iterdir():
                    if not core_root.is_dir() or core_root.name not in catalog.cores:
                        continue
                    hashes = [p.name for p in core_root.iterdir() if p.is_dir() and re.fullmatch(r"[0-9a-f]{64}", p.name)]
                    if not hashes and (core_root / "sram").is_dir():
                        core = catalog.cores[core_root.name]
                        hashes = [core.core_hash or file_hash(core.path)]
                    for core_hash in hashes:
                        self.save_manager.register({"gameId": item["id"], "title": item["title"],
                            "basename": Path(item["path"]).stem, "platform": item["platform"].lower(),
                            "contentHash": identity, "coreId": core_root.name, "coreHash": core_hash})
            result = self.save_manager.backup_all()
            result["deferred"] = sorted(set(result["deferred"] + deferred))
            return result
        self.save_work(all_games, complete, contextual=False)

    def save_history(self):
        def loaded(value):
            context, entries = value
            self.save_history_menu(context, entries)
        self.save_work(lambda ctx: (ctx, self.save_manager.history.entries(ctx)), loaded)

    def save_history_menu(self, context, entries):
        options = []
        for entry in entries:
            compatible = entry["kind"] == "sram" or entry["context"]["coreHash"] == context["coreHash"]
            label = self.save_history_label(entry)
            options.append((label, (lambda e=entry: self.save_restore_confirm(context, e)) if compatible and not self.engine.running() else None,
                            "" if compatible else tr(Msg.EMU_SAVE_CORE_MISMATCH)))
        self.menu(tr(Msg.EMU_SAVE_HISTORY), options, "" if entries else tr(Msg.EMU_SAVE_NO_HISTORY))

    @staticmethod
    def save_history_label(entry):
        slot = tr(Msg.EMU_SAVE_SRAM) if entry["kind"] == "sram" else tr(Msg.EMU_SAVE_AUTO) if entry["slot"] == "auto" else tr(Msg.SLOT_SLOT, slot=entry["slot"])
        return tr(Msg.EMU_SAVE_HISTORY_ROW, device=entry["deviceName"],
                  time=datetime.fromtimestamp(entry["created"]).strftime("%Y-%m-%d %H:%M:%S"), slot=slot)

    def save_restore_confirm(self, context, entry):
        self.menu(tr(Msg.EMU_SAVE_RESTORE_CONFIRM), [
            (tr(Msg.CONFIRM), lambda: self.save_work(lambda: self.save_manager.restore(context, entry["id"]),
                lambda _: self.save_finished(Msg.EMU_SAVE_RESTORED), contextual=False)),
            (tr(Msg.CANCEL), self.pop_menu)], tr(Msg.EMU_SAVE_RESTORE_TARGET, game=context["title"],
                 core=context["coreId"], version=self.save_history_label(entry)) + "\n" + tr(Msg.EMU_SAVE_RESTORE_NOTICE), body_lines=10)

    def save_settings(self):
        self.menu(tr(Msg.EMU_SAVE_SETTINGS), self.save_settings_options, tr(Msg.EMU_SAVE_CLOUD_DESCRIPTION), settings=True)

    def save_settings_options(self):
        state, option = self.save_cloud.state, self.setting_option
        return [
            option(tr(Msg.EMU_SAVE_BACKUP_ALL), self.save_backup_all, "document-save"),
            option(tr(Msg.EMU_SAVE_CLOUD), self.save_toggle_cloud, "network-server", checked=state["enabled"]),
            option(tr(Msg.EMU_SAVE_REMOTE), self.save_remote_picker, "network-server", state.get("remote") or tr(Msg.EMU_SAVE_NOT_SELECTED)),
            option(tr(Msg.EMU_SAVE_REMOTE_DIRECTORY), lambda: self.prompt(tr(Msg.EMU_SAVE_REMOTE_DIRECTORY),
                   lambda path: self.save_configure({"directory": path}), state.get("directory", "")), "folder", state.get("directory") or "/"),
            option(tr(Msg.EMU_SAVE_TEST_CONNECTION), self.save_test_connection, "network-transmit-receive"),
            option(tr(Msg.EMU_SAVE_SYNC_NOW), lambda: self.save_cloud.request("SyncNow"), "view-refresh"),
            option(tr(Msg.EMU_SAVE_OPEN_HISTORY), self.save_conflicts, "document-open-recent"),
            option(tr(Msg.EMU_SAVE_RCLONE_CONFIG), self.save_configure_rclone, "utilities-terminal"),
            option(tr(Msg.EMU_SAVE_STATUS), self.save_status_menu, "dialog-information", self.save_state()["saveStatus"])]

    def save_status_details(self):
        state = self.save_cloud.state
        lines = [self.save_state()["saveStatus"]]
        stats = state.get("progress", {})
        if state.get("phase") == "syncing":
            lines.append(tr(Msg.EMU_SAVE_TRANSFER_PROGRESS,
                            done=f"{(stats.get('bytes') or 0) / 1048576:.1f}",
                            total=f"{(stats.get('totalBytes') or 0) / 1048576:.1f}",
                            speed=f"{(stats.get('speed') or 0) / 1024:.1f}"))
        if state.get("lastSync"):
            lines.append(tr(Msg.EMU_SAVE_LAST_SYNC, time=datetime.fromtimestamp(state["lastSync"]).strftime("%Y-%m-%d %H:%M:%S")))
        if state.get("error"):
            lines.append(state["error"])
        return "\n".join(lines)

    def save_status_menu(self):
        self.menu(tr(Msg.EMU_SAVE_STATUS), [
            (tr(Msg.EMU_SAVE_SYNC_NOW), lambda: self.save_cloud.request("SyncNow")),
            (tr(Msg.EMU_SAVE_OPEN_HISTORY), self.save_conflicts),
            (tr(Msg.BACK), self.pop_menu)], self.save_status_details(), owner="save-sync-status", body_lines=10)

    def save_toggle_cloud(self):
        if not self.save_cloud.state.get("remote"):
            self.save_remote_picker()
            return
        self.save_configure({"enabled": not self.save_cloud.state["enabled"]})

    def save_configure(self, changes):
        self.save_configuration_generation += 1
        generation = self.save_configuration_generation
        value = {key: self.save_cloud.state.get(key, "") for key in ("enabled", "remote", "directory")}
        value.update(changes)
        def apply():
            if generation == self.save_configuration_generation and not self.save_closed:
                self.save_cloud.request("Configure", value)
        if value["enabled"] and not self.save_cloud.state["enabled"]:
            self.save_backup_all(on_complete=apply)
        else:
            apply()

    def save_remote_picker(self):
        def selected(result):
            if result.get("error"):
                raise OSError(result["error"])
            self.menu(tr(Msg.EMU_SAVE_REMOTE), [(remote, lambda r=remote: self.save_configure({"remote": r})) for remote in result["remotes"]]
                      + [(tr(Msg.EMU_SAVE_RCLONE_CONFIG), self.save_configure_rclone)])
        self.save_cloud.request("Remotes", callback=lambda result: self.attempt(lambda: selected(result)))

    def save_test_connection(self):
        def tested(result):
            if result.get("error"):
                self._save_failed(OSError(result["error"]))
            else:
                self.notice = tr(Msg.EMU_SAVE_CONNECTION_OK)
                self.publish()
        self.save_cloud.request("TestConnection", {key: self.save_cloud.state.get(key, "") for key in ("remote", "directory")}, tested)

    @staticmethod
    def save_configure_rclone():
        subprocess.Popen(["udeck-terminal", "--", "rclone", "config"], start_new_session=True)

    def save_conflicts(self):
        def loaded(results):
            options = []
            for context, result in results:
                for conflict in result["conflicts"]:
                    for entry in conflict["versions"]:
                        label = context["title"] + " · " + context["coreId"] + " · " + self.save_history_label(entry)
                        options.append((label, lambda c=context, e=entry: self.save_restore_confirm(c, e)))
            self.menu(tr(Msg.EMU_SAVE_CONFLICT), options, tr(Msg.EMU_SAVE_CONFLICT_NOTICE) if options else tr(Msg.EMU_SAVE_NO_HISTORY))
        self.save_work(lambda: [(ctx, self.save_manager.reconcile(ctx)) for ctx in self.save_manager.registered()], loaded, contextual=False)

    def save_start_game(self, resume=False):
        if self.sync_launch or self.launching or self.engine.running():
            raise RuntimeError(tr(Msg.A_GAME_IS_ALREADY_STARTING_OR_RUNNING))
        if not self.save_cloud.state["enabled"]:
            self._start_game(resume)
            return
        self.wait_for_cloud(resume)

    def wait_for_cloud(self, resume):
        self.cancel_launch()
        self.sync_launch = {"resume": resume, "deadline": time.monotonic() + 30,
                            "generation": self.launch_generation, "job": None, "prompted": False}
        gate = self.sync_launch
        self.clear_menus()
        self.notice = tr(Msg.EMU_SAVE_WAIT_SYNC)
        def requested(result):
            if self.sync_launch is gate and gate["generation"] == self.launch_generation:
                gate["job"] = result.get("jobId")
                self.save_cloud_result(result)
        self.save_cloud.request("SyncNow", callback=requested)
        self.publish()

    @Slot(object)
    def save_cloud_result(self, state):
        if self.save_closed:
            return
        self.save_cloud.state.update(state)
        for menu in self.menus:
            if menu["owner"] == "save-sync-status":
                menu["body"] = self.save_status_details()
        gate = self.sync_launch
        if gate and gate["generation"] == self.launch_generation:
            if state.get("phase") in ("error", "conflict"):
                self.save_wait_menu()
            elif (state.get("phase") == "idle" and gate["job"] is not None
                  and state.get("completedJob", 0) >= gate["job"]):
                self.save_offline_launch()
        self.publish()

    def save_wait_menu(self):
        gate = self.sync_launch
        if not gate or gate["prompted"]:
            return
        gate["prompted"] = True
        self.menu(tr(Msg.EMU_SAVE_SYNC_WAIT_TITLE), [
            (tr(Msg.EMU_SAVE_RETRY), lambda: self.wait_for_cloud(gate["resume"])),
            (tr(Msg.EMU_SAVE_WAIT), self.save_keep_waiting),
            (tr(Msg.EMU_SAVE_OFFLINE), self.save_offline_launch),
            (tr(Msg.EMU_SAVE_OPEN_HISTORY), self.save_conflicts),
            (tr(Msg.CANCEL), self.save_cancel_wait)], self.save_cloud.state.get("error", ""))

    def save_keep_waiting(self):
        if self.sync_launch:
            self.sync_launch.update(deadline=time.monotonic() + 30, prompted=False)
        self.clear_menus()

    def save_cancel_wait(self):
        self.cancel_launch()
        self.clear_menus()
        self.notice = ""

    def save_offline_launch(self):
        gate = self.sync_launch
        if not gate:
            return
        self.sync_launch = None
        self.clear_menus()
        self._start_game(gate["resume"])

    def save_poll(self):
        if self.save_closed:
            return
        self.save_cloud.refresh()
        if self.sync_launch and time.monotonic() >= self.sync_launch["deadline"]:
            self.save_wait_menu()

    def prepare_save_launch(self):
        if self.save_launch_ready == self.launch_generation:
            return True
        context = self.save_context(self.launch_item, self.checks)
        generation = self.launch_generation
        self.launching = True
        def ready(result):
            if generation != self.launch_generation:
                return
            self.launching = False
            if result["deferred"]:
                raise RuntimeError(tr(Msg.EMU_SAVE_BUSY))
            if result["conflicts"]:
                self.save_history_menu(context, [v for c in result["conflicts"] for v in c["versions"]])
                return
            self.save_launch_ready = generation
            self.attempt(self.complete_launch)
        def failed(error):
            if generation == self.launch_generation:
                self.launching = False
                self._save_failed(error)
        self.save_work(lambda: self.save_manager.reconcile(context), ready, contextual=False, on_error=failed, internal=True)
        return False

    def acquire_save_session(self):
        context = self.save_context(self.launch_item, self.checks)
        session = self.save_manager.session(context)
        session.__enter__()
        self.running_save_context, self.running_save_session = context, session

    def release_save_session(self):
        if self.running_save_session:
            self.running_save_session.__exit__(None, None, None)
        self.running_save_context = self.running_save_session = None

    def record_running_save(self, slot):
        context = copy.deepcopy(self.running_save_context)
        if context:
            generation = self.save_manager.store(context).manifest()[str(slot)]
            self.save_work(lambda: self.save_manager.record_state(context, slot, generation=generation), self.save_after_record,
                           contextual=False, internal=True)

    def save_after_record(self, result):
        if self.save_cloud.state["enabled"]:
            self.save_cloud.request("SyncNow")

    def record_exited_sram(self, code):
        context = copy.deepcopy(self.running_save_context)
        self.release_save_session()
        if context and code == 0 and self.engine.sram_committed:
            self.save_work(lambda: self.save_manager.backup_sram(context), self.save_after_record,
                           contextual=False, internal=True)

    def close_save_management(self):
        self.save_closed = True
        self.sync_launch = None
        self.save_cloud.close()
        self.release_save_session()
