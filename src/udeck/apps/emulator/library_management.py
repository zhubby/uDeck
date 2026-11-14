"""Existing handheld menus bridge to cancellable library workers and downloads."""

import copy
import json
import threading
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

from udeck.apps.common.state import AppState
from udeck.i18n import Msg, error_text, tr

from .migration import MigrationTransaction, plan_migration
from .playlists import PlaylistDocument, generate_playlists, update_entry
from .thumbnails import KINDS, ThumbnailDownloader


class LibrarySignals(QObject):
    done = Signal(object, object)


class LibraryTask(QRunnable):
    def __init__(self, operation):
        super().__init__()
        self.operation = operation
        self.signals = LibrarySignals()

    def run(self):
        try:
            self.signals.done.emit(self.operation(), None)
        except Exception as error:
            self.signals.done.emit(None, error_text(error))


class EmulatorLibraryManagement:
    def init_library_management(self):
        self.library_task = None
        self.library_callback = None
        self.library_publishing = False
        self.library_cancel = threading.Event()
        self.library_pool = QThreadPool(self)
        self.library_pool.setMaxThreadCount(1)
        self.library_closed = False
        self.thumbnail_downloader = ThumbnailDownloader(self)
        self.thumbnail_downloader.changed.connect(self.thumbnail_progress)
        self.thumbnail_downloader.finished.connect(self.thumbnails_finished)
        self.migration_journal = self.store.path.parent / "emulator-migration.json"
        self.migration_pending = False
        if self.migration_journal.exists():
            try:
                value = MigrationTransaction(self.migration_journal)._load()
                self.migration_pending = value.get("status") not in {"committed", "rolled-back"}
            except (OSError, ValueError) as error:
                self.migration_pending = True
                self.library.errors["migration"] = tr(Msg.EMU_PLAYLIST_INVALID, path=self.migration_journal) + ": " + error_text(error)
            if self.migration_pending:
                self.library.suspended = True
                self.library.cancel.set()
                self.library.generation += 1
                self.library.pending.clear()

    def require_library_idle(self, *, recovery=False):
        if self.library_task is not None or self.engine.running() or self.launching or self.save_jobs:
            raise RuntimeError(tr(Msg.EMU_LIBRARY_BUSY))
        if self.migration_pending and not recovery:
            raise RuntimeError(tr(Msg.EMU_MIGRATION_RECOVERY))
        if self.library.identity_error and not recovery:
            raise RuntimeError(self.library.identity_error)

    def library_work(self, operation, callback, *, publishing=False, recovery=False):
        self.require_library_idle(recovery=recovery)
        self.cancel_launch()
        self.library_cancel = threading.Event()
        self.library_callback = callback
        self.library_publishing = publishing
        self.library_task = LibraryTask(operation)
        self.library_task.signals.done.connect(self.library_work_done)
        self.library_pool.start(self.library_task)
        self.notice = tr(Msg.EMU_LIBRARY_WORKING)
        self.publish()

    def library_work_done(self, result, error):
        self.library_task = None
        callback, self.library_callback = self.library_callback, None
        publishing, self.library_publishing = self.library_publishing, False
        if self.library_closed:
            return
        self.notice = ""
        if error:
            self.error = error
            if self.library.suspended:
                try:
                    value = json.loads(self.migration_journal.read_text())
                    self.migration_pending = value.get("status") not in {"committed", "rolled-back"}
                except (OSError, ValueError):
                    self.migration_pending = True
                self.library.suspended = self.migration_pending
                if not self.migration_pending:
                    self.library.refresh()
        elif callback and (publishing or not self.library_cancel.is_set()):
            self.attempt(lambda: callback(result))
        self.publish()

    def cancel_library_operation(self):
        self.library_cancel.set()

    def preview_scan(self):
        root, directory = self.library.root_path, self.library.playlist_path
        catalog = copy.deepcopy(self.catalog)
        self.library_work(lambda: generate_playlists(root, directory, catalog, self.library_cancel.is_set),
                          self.scan_preview)

    def preview_file_entries(self, paths):
        paths = {str(path) for path in paths}
        catalog = copy.deepcopy(self.catalog)
        catalog.preferences.setdefault("engineEntries", []).extend(paths)
        root, directory = self.library.root_path, self.library.playlist_path
        self.library_work(lambda: generate_playlists(root, directory, catalog, self.library_cancel.is_set,
                                                    selected=paths),
                          lambda proposal: self.scan_preview(proposal, paths))

    def scan_preview(self, proposal, engine_entries=()):
        names = "\n".join(i["relative"] for i in proposal.additions[:6])
        self.menu(tr(Msg.EMU_SCAN_PREVIEW, count=len(proposal.additions)), [
            (tr(Msg.CONFIRM), (lambda: self.commit_scan(proposal, engine_entries)) if proposal.additions else self.pop_menu),
            (tr(Msg.CANCEL), self.pop_menu)], tr(Msg.EMU_SCAN_PREVIEW_BODY) + "\n" + names)
        if not proposal.additions:
            self.menus[-1]["body"] = "\n".join(map(str, proposal.hints[:6])) or tr(Msg.EMU_SCAN_PREVIEW_BODY)

    def commit_scan(self, proposal, engine_entries=()):
        def committed(_):
            if engine_entries:
                entries = self.store.data["preferences"].setdefault("engineEntries", [])
                entries.extend(sorted(set(engine_entries) - set(entries)))
                self.persist()
            self.clear_menus()
            self.notice = tr(Msg.EMU_LISTS_UPDATED)
            self.library.refresh()
        self.library_work(proposal.commit, committed, publishing=True)

    def library_directory_picker(self, key):
        self.require_library_idle()
        self.cancel_launch()
        attribute = {"playlistDirectory": "playlist_path", "thumbnailDirectory": "thumbnail_path"}[key]

        def chosen(path):
            self.require_library_idle()
            self.thumbnail_downloader.cancel()
            self.library.configure_directory(key, path)
            self.clear_menus()
            self.settings()
        self.path_picker(getattr(self.library, attribute), chosen)

    def preview_images(self):
        labels = (Msg.EMU_BOXART, Msg.EMU_SNAPSHOT, Msg.EMU_TITLE_SCREEN)
        self.menu(tr(Msg.EMU_PREVIEW_IMAGES), [(tr(label), lambda kind=kind: self.select_thumbnail(kind))
                                            for label, kind in zip(labels, KINDS, strict=True)])

    def select_thumbnail(self, kind):
        from .thumbnails import apply_thumbnails

        self.store.data["preferences"]["thumbnailType"] = kind
        self.library.reload_thumbnails()
        if self.current:
            apply_thumbnails(self.current, self.library.thumbnail_path, kind)
        self.persist()
        self.pop_menu()

    def download_game_images(self):
        item = self.current if self.page == "game-details" else self.library.entry(self.selected)
        self.download_images([item])

    def download_list_images(self):
        items = [i for i in self.library.items if i.get("playlistId") == self.platform]
        self.download_images(items)

    def download_images(self, items):
        self.require_library_idle()
        self.thumbnail_downloader.start(items, self.library.thumbnail_path)
        self.image_download_menu()

    def image_download_menu(self):
        self.menu(tr(Msg.EMU_IMAGE_DOWNLOADS), [
            (tr(Msg.CANCEL_DOWNLOAD), self.thumbnail_downloader.cancel),
            (tr(Msg.BACK), self.pop_menu)], self.thumbnail_status())
        self.menus[-1]["imageDownloads"] = True

    def thumbnail_status(self):
        status = self.thumbnail_downloader.status
        body = tr(Msg.EMU_IMAGE_PROGRESS, **{k: status.get(k, 0) for k in
                                           ("done", "total", "saved", "missing", "failed")})
        if status.get("cancelled"):
            body += "\n" + tr(Msg.OPERATION_CANCELLED)
        elif status and not self.thumbnail_downloader.running:
            body += "\n" + tr(Msg.DOWNLOAD_COMPLETE)
        return body

    def thumbnail_progress(self):
        if self.library_closed:
            return
        for menu in self.menus:
            if menu.get("imageDownloads"):
                menu["body"] = self.thumbnail_status()
                errors = self.thumbnail_downloader.status.get("errors", [])
                if errors:
                    menu["body"] += "\n" + "\n".join(errors[:2])
        self.publish()

    def thumbnails_finished(self):
        from .thumbnails import apply_thumbnails

        self.library.reload_thumbnails()
        if self.current:
            apply_thumbnails(self.current, self.library.thumbnail_path,
                             self.store.data["preferences"].get("thumbnailType", "Named_Boxarts"))
        self.publish()

    def playlist_core_menu(self):
        options = [(tr(Msg.EMU_PLAYLIST_CORE_DEFAULT), lambda: self.set_playlist_core(None))]
        options.extend((core.name, lambda identifier=core.id: self.set_playlist_core(identifier))
                       for core in self.catalog.cores.values() if core.status == "available" and self.catalog.enabled(core))
        self.menu(tr(Msg.CHOOSE_CORE), options)

    def set_playlist_core(self, identifier):
        playlist = next(p for p in self.library.playlists if p["id"] == self.platform)
        document = PlaylistDocument.load(playlist["path"])
        if document.original != playlist.get("signature"):
            raise ValueError(tr(Msg.EMU_PLAYLIST_CHANGED, path=document.path))
        core = self.catalog.cores.get(identifier) if identifier else None
        document.data.update(default_core_path=core.path if core else "DETECT",
                             default_core_name=core.name if core else "DETECT")
        document.save()
        playlist["signature"] = document.original
        self.library.refresh()
        self.pop_menu()

    def select_game_platform(self):
        options = [(name, lambda name=name: self.set_game_database(name))
                   for platform in self.catalog.platforms.values() for name in platform.databases]
        self.menu(tr(Msg.EMU_SELECT_PLATFORM), options)

    def set_game_database(self, name):
        from .thumbnails import apply_thumbnails

        update_entry(self.current, {"db_name": name + ".lpl"})
        self.current["dbName"] = name
        self.current["platform"] = self.catalog.platform_for_database(name).id
        apply_thumbnails(self.current, self.library.thumbnail_path,
                         self.store.data["preferences"].get("thumbnailType", "Named_Boxarts"))
        self.update_checks()
        self.library.refresh()
        self.pop_menu()

    def migrate_library(self, base=None, mappings=None):
        old_root = self.library.legacy_root or self.library.root_path
        base = Path(base) if base else Path.home() / "Games"
        catalog = copy.deepcopy(self.catalog)
        old_items = copy.deepcopy(self.library.items)
        if self.library.legacy_path.exists() and self.library.legacy_root:
            old_items = json.loads(self.library.legacy_path.read_text())["items"]

        def prepared(plan):
            if plan.choices:
                directory = next(iter(plan.choices))

                def choose(database):
                    self.pop_menu()
                    self.migrate_library(base, {**(mappings or {}), directory: database})
                self.menu(tr(Msg.EMU_MIGRATION_MAPPING, path=directory), [
                    (name, lambda name=name: choose(name)) for name in plan.choices[directory]])
            elif plan.issues:
                self.menu(tr(Msg.EMU_MIGRATE_LIBRARY), [(tr(Msg.BACK), self.pop_menu)],
                          "\n".join(map(str, plan.issues[:8])), body_lines=8)
            else:
                self.menu(tr(Msg.EMU_MIGRATION_PREVIEW, count=len(plan.moves)), [
                    (tr(Msg.CONFIRM), lambda: self.commit_migration(plan)), (tr(Msg.CANCEL), self.pop_menu)],
                    str(base) + "\n" + "\n".join(m["source"] + " → " + m["target"] for m in plan.moves[:3]))
        self.library_work(lambda: plan_migration(old_root, base, catalog, old_items, mappings,
                                               self.library_cancel.is_set), prepared)

    def commit_migration(self, plan):
        self.require_library_idle()
        self.library.cancel.set()
        self.library.generation += 1
        self.library.pending.clear()
        self.library.suspended = True
        self.thumbnail_downloader.cancel()
        self.store.save()
        self.store.flush()

        def migrate():
            state = AppState("emulator", self.store.path.parent)
            try:
                return MigrationTransaction(self.migration_journal, self.library_cancel.is_set).execute(plan, state)
            finally:
                state.close()
        self.library_work(migrate, self.migration_committed, publishing=True)

    def migration_committed(self, data):
        self.store.data.clear()
        self.store.data.update(data)
        self.catalog.preferences = self.store.data["preferences"]
        self.library.reload_configuration()
        self.migration_pending = False
        self.library.suspended = False
        self.current = None
        self.clear_menus()
        self.setTab(1)
        self.library.refresh()
        self.notice = tr(Msg.EMU_MIGRATION_COMPLETE)

    def recover_migration(self, resume=False):
        self.store.flush()

        def recover():
            transaction = MigrationTransaction(self.migration_journal)
            plan = transaction._load()["plan"]
            transaction.rollback()
            state = AppState("emulator", self.store.path.parent)
            try:
                return copy.deepcopy(state.data), plan
            finally:
                state.close()

        def recovered(result):
            data, plan = result
            self.store.data.clear()
            self.store.data.update(data)
            self.catalog.preferences = self.store.data["preferences"]
            self.library.reload_configuration()
            self.migration_pending = False
            self.library.suspended = False
            self.clear_menus()
            self.notice = tr(Msg.EMU_MIGRATION_RESTORED)
            if resume:
                self.migrate_library(plan["base"], plan.get("mappings"))
            else:
                self.library.refresh()
        self.library_work(recover, recovered, publishing=True, recovery=True)

    def close_library_management(self):
        self.library_closed = True
        self.library_cancel.set()
        self.thumbnail_downloader.cancel()
        self.library_pool.waitForDone(5000)
