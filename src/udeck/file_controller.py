import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path

from PySide6.QtCore import QFileSystemWatcher, Qt, QTimer

from .core import move_index
from .file_jobs import FileJob, distinct_sources
from .file_locations import mounted_locations, unmount, user_locations
from .file_model import FileListModel
from .file_preview import preview
from .file_trash import TrashStore
from .files import FileOperations, query_entries
from .i18n import Msg, tr

SORT_LABELS = {"name": tr(Msg.NAME), "modified": tr(Msg.MODIFIED), "size": tr(Msg.SIZE)}
KIND_LABELS = {"all": tr(Msg.ALL_FILES), "audio": tr(Msg.AUDIO), "video": tr(Msg.VIDEO), "image": tr(Msg.IMAGES),
               "book": tr(Msg.BOOKS), "text": tr(Msg.TEXT), "archive": tr(Msg.ARCHIVES), "other": tr(Msg.OTHER_FILES)}


class FileControls:
    def _init_file_controls(self):
        self._file_model = FileListModel(self)
        self._file_entries = []
        self._file_view_entries = self.data["files"]
        self.file_query = ""
        self.file_section = "list"
        self.file_columns = 5
        self.file_place_index = 0
        self.file_breadcrumb_index = 0
        self.file_marked = set()
        self.file_selection = False
        self.file_task = {}
        self._file_job_cancel = threading.Event()
        self._file_job_clipboard = None
        self._file_job_audible = False
        self._file_watched_selection = None
        self._file_job_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="udeck-transfer")
        self._file_scan_token = 0
        self._file_pending_browse = None
        self._files_closing = False
        self._file_preview_text = ""
        self._file_places_base = [{"id": "home", "path": str(Path.home()), "name": tr(Msg.HOME_FOLDER), "icon": "user-home"},
                                  {"id": "root", "path": "/", "name": tr(Msg.FILE_SYSTEM), "icon": "drive-harddisk"},
                                  {"id": "trash", "path": "trash:///", "name": tr(Msg.TRASH), "icon": "user-trash"}]
        self.trash_store = TrashStore()
        self._file_watcher = QFileSystemWatcher(self)
        self._file_watcher.directoryChanged.connect(self._request_files_refresh)
        self._file_watcher.fileChanged.connect(self._request_files_refresh)
        self._file_refresh_timer = QTimer(self)
        self._file_refresh_timer.setSingleShot(True)
        self._file_refresh_timer.setInterval(250)
        self._file_refresh_timer.timeout.connect(self._refresh_files)
        self._file_location_timer = QTimer(self)
        self._file_location_timer.setInterval(10000)
        self._file_location_timer.timeout.connect(self._request_files_refresh)
        self.fileJobProgress.connect(self._file_job_progress, Qt.ConnectionType.QueuedConnection)
        self.fileJobFinished.connect(self._file_job_finished, Qt.ConnectionType.QueuedConnection)

    def _file_sync(self):
        if self._file_view_entries is not self.data["files"]:
            self._file_entries = list(self.data["files"])
            self._file_view_entries = self.data["files"]
        self._file_model.set_entries(self.data["files"])
        self._file_model.ensure_index(self.navigation.index if self.navigation.page == "files" else 0)
        self._file_model.set_language(self.language)
        cut = (self.clipboard.get("paths") or [self.clipboard["path"]]) if self.clipboard and self.clipboard["move"] else []
        self._file_model.set_marks(self.file_marked, cut)
        current = self._file_current() if self.navigation.page == "files" else None
        path = current.get("path", current["id"]) if current else None
        if path != self._file_watched_selection:
            self._file_watch()

    def _file_places(self):
        places = list(self._file_places_base)
        seen = {entry["path"] for entry in places}
        for path in self.config.data["fileManager"]["bookmarks"]:
            if path not in seen:
                places.append({"id": "bookmark:" + path, "path": path, "name": Path(path).name or "/",
                               "icon": "folder-favorites", "bookmark": True})
                seen.add(path)
        return places

    def _file_breadcrumbs(self):
        directory = self.data["directory"]
        if directory == "trash:///":
            return [{"name": tr(Msg.TRASH), "path": directory}]
        path = Path(directory)
        paths = [*reversed(path.parents), path]
        return [{"name": entry.name or "/", "path": str(entry)} for entry in paths][-32:]

    def _file_active(self):
        return self.file_task.get("state") in ("preparing", "running", "cancelling")

    def _file_state(self):
        preferences = self.config.data["fileManager"]
        task = {key: value for key, value in self.file_task.items() if key not in ("sources", "errors", "completed", "skipped")}
        task["active"] = self._file_active()
        if task:
            task["summary"] = self._file_task_summary()
            sources = self.file_task.get("sources", [])
            first = sources[0] if sources else ""
            task["sourceLabel"] = tr(Msg.FROM_PATH, path=task.get("current") or (first.get("path", "") if isinstance(first, dict) else first))
            destination = task.get("directory") or (tr(Msg.TRASH) if task.get("action") == "trash" else tr(Msg.ORIGINAL_LOCATIONS))
            task["destinationLabel"] = tr(Msg.TO_PATH, path=destination)
            task["fileCountLabel"] = tr(Msg.DONE_TOTAL_FILE_S, done=task.get("doneFiles", 0), total=task.get("totalFiles", 0))
            remaining = task.get("eta", -1)
            task["etaLabel"] = tr(Msg.SECONDS_S_REMAINING, seconds=max(0, int(remaining))) if remaining >= 0 else ""
        clipboard = self.clipboard or {}
        paths = clipboard.get("paths") or ([clipboard["path"]] if clipboard else [])
        return {"count": len(self.data["files"]), "query": self.file_query,
                "sort": preferences["sort"], "sortLabel": SORT_LABELS[preferences["sort"]],
                "descending": preferences["descending"], "filter": preferences["kind"],
                "filterLabel": KIND_LABELS[preferences["kind"]], "places": self._file_places(),
                "section": self.file_section, "placeIndex": self.file_place_index,
                "breadcrumbs": self._file_breadcrumbs(), "breadcrumbIndex": self.file_breadcrumb_index,
                "selectionMode": self.file_selection, "selectedCount": len(self.file_marked),
                "current": self._file_current() or {},
                "isTrash": self.data["directory"] == "trash:///", "task": task,
                "clipboardCount": len(paths), "clipboardMove": clipboard.get("move", False),
                "clipboardLabel": ", ".join(Path(path).name for path in paths[:3]),
                "networkAccess": self.network_access}

    def _file_apply_query(self, selected=None):
        previous = self._file_current()
        selected = selected or (previous["id"] if previous else None)
        preferences = self.config.data["fileManager"]
        self.data["files"] = query_entries(self._file_entries, query=self.file_query, sort=preferences["sort"],
                                            descending=preferences["descending"], kind=preferences["kind"])
        self._file_view_entries = self.data["files"]
        if self.navigation.page == "files":
            position = next((index for index, entry in enumerate(self.data["files"]) if entry["id"] == selected), self.navigation.index)
            self.navigation.select(max(0, min(position, len(self.data["files"]) - 1)))
        self.file_marked.intersection_update(entry["id"] for entry in self.data["files"])
        self._file_sync()

    def _file_current(self):
        entries = self.data["files"]
        return entries[max(0, min(self.navigation.index, len(entries) - 1))] if entries else None

    def _file_selected(self):
        if self.file_selection:
            return [entry for entry in self.data["files"] if entry["id"] in self.file_marked]
        current = self._file_current()
        return [current] if current else []

    def _file_preferences(self, **values):
        previous = deepcopy(self.config.data["fileManager"])
        self.config.data["fileManager"].update(values)
        try:
            self.config.save()
        except OSError as error:
            self.config.data["fileManager"] = previous
            self.notify(error)
            return
        self._file_apply_query()

    def _request_files_refresh(self, *_arguments):
        if not self.mock and not self._files_closing and self.navigation.page == "files":
            self._file_refresh_timer.start()
            if not self._file_location_timer.isActive():
                self._file_location_timer.start()

    def _refresh_files(self):
        if self.mock or self._files_closing or self.navigation.page != "files":
            return
        if self.busy or self.modal:
            self._file_refresh_timer.start(500)
            return
        directory = self.data["directory"]
        if directory != "trash:///" and not Path(directory).is_dir():
            self.notify(tr(Msg.FOLDER_IS_NO_LONGER_AVAILABLE_RETURNED_TO_HOME_FOLDER))
            directory = str(Path.home())
        self._browse(directory)

    def _file_watch(self):
        current = self._file_current() if self.navigation.page == "files" else None
        self._file_watched_selection = current.get("path", current["id"]) if current else None
        watched = self._file_watcher.directories() + self._file_watcher.files()
        if watched:
            self._file_watcher.removePaths(watched)
        if self.mock or self.data["directory"] == "trash:///":
            return
        paths = [self.data["directory"]]
        selected = current
        if selected and not selected.get("directory"):
            paths.append(selected["path"])
        self._file_watcher.addPaths([path for path in paths if Path(path).exists()])

    def _browse_files(self, directory, select_path=None):
        directory = str(directory) if str(directory) == "trash:///" else str(Path(directory).absolute())
        if self.mock:
            changed = directory != self.data["directory"]
            self.data["directory"] = directory
            if changed:
                self.file_query, self.file_marked, self.file_selection = "", set(), False
                self.navigation.select(0)
            if changed:
                self.file_section = "list"
            self.file_breadcrumb_index = len(self._file_breadcrumbs()) - 1
            self._publish()
            return
        self._file_scan_token += 1
        token = self._file_scan_token
        if self.busy:
            self._file_pending_browse = (directory, select_path)
            return
        old_directory = self.data["directory"]
        selected = self._file_current()
        self.directory_positions[old_directory] = {"id": selected["id"] if selected else None, "index": self.navigation.index}

        def read():
            entries = self.trash_store.entries() if directory == "trash:///" else self.operations.list_directory(directory, self.show_hidden)
            return entries, user_locations() + mounted_locations()

        def loaded(result):
            if token != self._file_scan_token:
                return
            entries, places = result
            self._file_places_base = places
            if directory != old_directory:
                self.file_query, self.file_marked, self.file_selection = "", set(), False
            self.data["directory"] = directory
            self._file_entries = entries
            saved = self.directory_positions.get(directory, {})
            if self.navigation.page == "files":
                self.navigation.select(saved.get("index", 0))
            self._file_apply_query(select_path or saved.get("id"))
            if directory != old_directory:
                self.file_section = "list"
            self.file_breadcrumb_index = len(self._file_breadcrumbs()) - 1
            self.file_place_index = min(self.file_place_index, max(0, len(self._file_places()) - 1))
            self._file_watch()

        self._run(tr(Msg.READ_FOLDER), read, loaded, report_success=False)

    def _file_pending(self):
        if self._file_pending_browse and not self.busy and not self._files_closing:
            directory, selected = self._file_pending_browse
            self._file_pending_browse = None
            self._browse(directory, selected)

    def _file_dispatch(self, action):
        if self.navigation.zone == "tabs":
            return False
        if action in ("left", "right", "up", "down"):
            previous = (self.navigation.index, self.navigation.zone, self.file_section,
                        self.file_place_index, self.file_breadcrumb_index)
            if self.file_section == "list":
                if action == "up" and self.navigation.index < self.file_columns:
                    self.file_section = "breadcrumbs"
                else:
                    self.navigation.select(move_index(self.navigation.index, action, len(self.data["files"]), self.file_columns))
            elif self.file_section == "breadcrumbs":
                if action == "up":
                    self.navigation.zone = "tabs"
                elif action == "down":
                    self.file_section = "list"
                else:
                    self.file_breadcrumb_index = max(0, min(self.file_breadcrumb_index + (-1 if action == "left" else 1), len(self._file_breadcrumbs()) - 1))
            current = (self.navigation.index, self.navigation.zone, self.file_section,
                       self.file_place_index, self.file_breadcrumb_index)
            if current != previous:
                self.feedback("navigate")
        elif action == "accept" and self.file_section != "list":
            entries = self._file_breadcrumbs()
            index = self.file_breadcrumb_index
            if entries:
                self.feedback("accept")
                self.file_section = "list"
                self._browse(entries[index]["path"])
        elif action == "accept" and self.file_selection:
            selected = self._file_current()
            if selected:
                self.file_marked.symmetric_difference_update({selected["id"]})
                self.feedback("accept")
        elif action == "back" and self.file_selection:
            self.feedback("back")
            self.file_selection, self.file_marked = False, set()
        elif action == "back" and self.data["directory"] == "trash:///":
            self._browse(Path.home())
        elif action == "search":
            self._text_prompt(tr(Msg.SEARCH_FILES), tr(Msg.SEARCH_NAMES_IN_THIS_FOLDER_SUBFOLDERS_ARE_NOT_INDEXED), "file-search", self.file_query)
        elif action.startswith("file-"):
            self._file_command(action[5:])
        else:
            return False
        self._publish()
        return True

    def _file_context(self, item):
        def option(label, command, **values):
            return {"label": label, "action": "files", "command": command, **values}
        options = [option(tr(Msg.LOCATIONS), "locations")]
        trash = self.data["directory"] == "trash:///"
        if item:
            if trash:
                options.extend([option(tr(Msg.RESTORE_SELECTED_ITEMS), "restore"), option(tr(Msg.RESTORE_TO_FOLDER), "restore-to")])
            else:
                options.extend([{"label": tr(Msg.OPEN), "action": "open-file", "item": item},
                                option(tr(Msg.OPEN_WITH), "open-with"),
                                option(tr(Msg.RENAME), "rename", disabled=len(self._file_selected()) != 1),
                                option(tr(Msg.COPY), "copy"), option(tr(Msg.CUT), "cut"),
                                option(tr(Msg.MOVE_TO_TRASH), "trash")])
            options.append(option(tr(Msg.PREVIEW_AND_DETAILS), "preview"))
        options.extend([option(tr(Msg.FINISH_SELECTION) if self.file_selection else tr(Msg.SELECT_MULTIPLE_ITEMS), "selection"),
                        option(tr(Msg.SELECT_ALL), "select-all"), option(tr(Msg.SEARCH_FILES), "search"),
                        option(tr(Msg.SORT_AND_FILTER), "organize"), option(tr(Msg.GO_TO_FOLDER), "go")])
        if not trash:
            options.extend([{"label": tr(Msg.NEW_FOLDER), "action": "mkdir"},
                            {"label": tr(Msg.OPEN_TERMINAL_HERE), "action": "open-terminal", "directory": self.data["directory"]},
                            option(tr(Msg.REMOVE_BOOKMARK) if self.data["directory"] in self.config.data["fileManager"]["bookmarks"] else tr(Msg.BOOKMARK_THIS_FOLDER), "bookmark")])
            if self.clipboard:
                options.extend([option(tr(Msg.PASTE_INTO_CURRENT_FOLDER), "paste"), option(tr(Msg.CLEAR_CLIPBOARD), "clear-clipboard")])
        if self.file_query:
            options.append(option(tr(Msg.CLEAR_SEARCH), "clear-search"))
        if self.file_task:
            options.append(option(tr(Msg.FILE_TASK), "task"))
        options.extend([{"label": tr(Msg.HIDE_HIDDEN_FILES) if self.show_hidden else tr(Msg.SHOW_HIDDEN_FILES), "action": "hidden"},
                        {"label": tr(Msg.REFRESH), "action": "refresh-files"}])
        self._menu(tr(Msg.FILE_ACTIONS), options)

    def _file_command(self, action, value="", option=None):
        option = option or {}
        selected = self._file_selected()
        if action.startswith("network-"):
            self._network_command(action[8:], value)
        elif action == "location":
            self.file_section = "list"
            self._browse(value)
        elif action == "locations":
            places = self._file_places()
            options = [{"label": place["name"], "subtitle": " · ".join(filter(None, [place.get("details"), place["path"]])),
                        "action": "files", "command": "location", "value": place["path"]} for place in places]
            if any(place.get("mount") for place in places):
                options.append({"label": tr(Msg.SAFELY_UNMOUNT), "action": "files", "command": "unmount-locations"})
            self._menu(tr(Msg.LOCATIONS), options)
        elif action == "unmount-locations":
            options = [{"label": place["name"], "subtitle": place["path"], "action": "files", "command": "unmount", "place": place}
                       for place in self._file_places() if place.get("mount")]
            self._menu(tr(Msg.SAFELY_UNMOUNT), options)
        elif action == "search":
            self._file_dispatch("search")
        elif action == "clear-search":
            self.file_query = ""
            self._file_apply_query()
        elif action == "sort" and value in SORT_LABELS:
            self._file_preferences(sort=value)
        elif action == "filter" and value in KIND_LABELS:
            self._file_preferences(kind=value)
        elif action == "descending":
            self._file_preferences(descending=not self.config.data["fileManager"]["descending"])
        elif action == "organize":
            options = [{"label": tr(Msg.SORT_VALUE, value=label), "action": "files", "command": "sort", "value": key}
                       for key, label in SORT_LABELS.items()]
            options.append({"label": tr(Msg.REVERSE_ORDER), "action": "files", "command": "descending"})
            options.extend({"label": label, "action": "files", "command": "filter", "value": key}
                           for key, label in KIND_LABELS.items())
            self._menu(tr(Msg.SORT_AND_FILTER), options)
        elif action == "go":
            self._text_prompt(tr(Msg.GO_TO_FOLDER), tr(Msg.ENTER_AN_ABSOLUTE_FOLDER_PATH), "file-location", self.data["directory"] if self.data["directory"] != "trash:///" else str(Path.home()))
        elif action == "bookmark":
            path = value or self.data["directory"]
            if path != "trash:///":
                bookmarks = list(self.config.data["fileManager"]["bookmarks"])
                if path in bookmarks:
                    bookmarks.remove(path)
                elif len(bookmarks) < 64:
                    bookmarks.append(path)
                self._file_preferences(bookmarks=bookmarks)
        elif action == "selection":
            self.file_selection = not self.file_selection
            self.file_marked.clear()
        elif action == "mark":
            self.file_selection = True
            current = self._file_current()
            if current:
                self.file_marked.symmetric_difference_update({current["id"]})
        elif action == "select-all":
            self.file_selection = True
            self.file_marked = {entry["id"] for entry in self.data["files"]}
        elif action in ("copy", "cut") and selected and self.data["directory"] != "trash:///":
            paths = distinct_sources([entry["path"] for entry in selected])
            self.clipboard = {"path": paths[0], "paths": paths, "move": action == "cut"}
            self.feedback("accept")
            self.file_marked.clear()
            self.file_selection = False
            self.notify(tr(Msg.CLIPBOARD_COUNT_ITEM_S, count=len(paths)))
        elif action == "clear-clipboard":
            self.clipboard = None
        elif action in ("paste", "paste-keep", "paste-skip", "paste-replace"):
            self._file_paste({"paste-keep": "keep", "paste-skip": "skip", "paste-replace": "replace"}.get(action, "error"))
        elif action == "confirm-replace":
            self._confirm(tr(Msg.REPLACE_FILES), tr(Msg.EXISTING_FILES_WILL_BE_REPLACED_FOLDERS_ARE_NEVER_MERGED_OR_OVERWRITTEN),
                          {"action": "files", "command": "paste-replace"})
        elif action == "trash" and selected and self.data["directory"] != "trash:///":
            self._confirm(tr(Msg.MOVE_TO_TRASH_PROMPT), tr(Msg.COUNT_ITEM_S_NO_PERMANENT_DELETION_WILL_BE_PERFORMED, count=len(selected)),
                          {"action": "files", "command": "trash-confirm", "items": selected})
        elif action == "trash-confirm":
            entries = option.get("items", [])
            self._file_start_job("trash", distinct_sources([entry["path"] for entry in entries]), "")
        elif action == "restore" and selected and all(entry.get("trash") for entry in selected):
            self._confirm(tr(Msg.RESTORE_SELECTED_ITEMS), tr(Msg.RESTORE_ORIGINAL_LOCATIONS_EXISTING_FILES_ARE_KEPT_CONFLICTS_GET_A_NEW_NAME),
                          {"action": "files", "command": "restore-confirm", "items": selected})
        elif action == "restore-to" and selected and all(entry.get("trash") for entry in selected):
            self._text_prompt(tr(Msg.RESTORE_TO_FOLDER), tr(Msg.ENTER_AN_EXISTING_FOLDER_ON_THE_SAME_FILE_SYSTEM), "file-restore", str(Path.home()), items=selected)
        elif action == "restore-confirm":
            self._file_start_job("restore", option.get("items", []), "")
        elif action == "preview" and selected:
            self._file_preview(selected[0])
        elif action == "open-with" and selected:
            self._file_open_with(selected[0])
        elif action == "open-default":
            item = option["item"]
            if self.mock:
                self.notify(tr(Msg.PREVIEW_OPEN_PREFIX) + item["name"])
            else:
                self._run(tr(Msg.OPEN_FILE), lambda: self.operations.open(item["path"]))
        elif action == "open-using":
            item = option["item"]
            if not self.mock:
                self._run(tr(Msg.OPEN_FILE), lambda: self.catalog.launch(value, [item["path"]]))
            else:
                self.notify(tr(Msg.PREVIEW_OPEN_PREFIX) + item["name"])
        elif action == "task" and self.file_task:
            self._file_show_task()
        elif action == "cancel-task":
            self._file_cancel_task()
        elif action == "unmount":
            place = option["place"]
            self._confirm(tr(Msg.SAFELY_UNMOUNT), place["path"], {"action": "files", "command": "unmount-confirm", "place": place})
        elif action == "unmount-confirm":
            self._file_unmount(option["place"])
        elif action == "rename" and selected and len(selected) == 1:
            self._execute_option({"action": "rename", "item": selected[0]})
        elif action == "refresh":
            self._browse(self.data["directory"])
        self._publish()

    def _file_submit(self, modal, text):
        purpose = modal.get("purpose")
        if purpose == "network-share-root" or purpose in ("sharing-web-root", "sharing-smb-root"):
            self._sharing_submit("smb" if purpose == "sharing-smb-root" else "web", text)
        elif purpose == "file-search":
            self.file_query = text.strip()
            self.navigation.select(0)
            self._file_apply_query()
        elif purpose == "file-location":
            path = Path(text).expanduser()
            if not path.is_absolute() or "\x00" in text:
                self.notify(tr(Msg.ENTER_AN_ABSOLUTE_FOLDER_PATH))
            else:
                self.file_section = "list"
                self._browse(path)
        elif purpose == "file-restore":
            path = Path(text).expanduser()
            if not path.is_absolute() or "\x00" in text:
                self.notify(tr(Msg.ENTER_AN_ABSOLUTE_FOLDER_PATH))
            else:
                self._file_start_job("restore", modal["items"], str(path))
        else:
            return False
        self._publish()
        return True

    def _file_paste(self, policy="error"):
        if not self.clipboard or self.data["directory"] == "trash:///":
            return
        if self.busy or self._file_active():
            self.notify(tr(Msg.WAIT_FOR_THE_CURRENT_FILE_OPERATION_TO_FINISH))
            return
        if self.mock:
            self.notify(tr(Msg.PREVIEW_PASTE_SIMULATED_NO_REAL_FILES_ACCESSED))
            return
        paths = distinct_sources(self.clipboard.get("paths") or [self.clipboard["path"]])
        directory = self.data["directory"]
        conflicts = [path for path in paths if (Path(directory) / Path(path).name).exists()
                     or (Path(directory) / Path(path).name).is_symlink()]
        if conflicts and policy == "error":
            options = [{"label": tr(Msg.CANCEL), "action": "none"},
                       {"label": tr(Msg.KEEP_BOTH), "action": "files", "command": "paste-keep"},
                       {"label": tr(Msg.SKIP_EXISTING), "action": "files", "command": "paste-skip"}]
            if not any(Path(path).is_dir() or (Path(directory) / Path(path).name).is_dir() for path in conflicts):
                options.append({"label": tr(Msg.REPLACE_FILES), "action": "files", "command": "confirm-replace"})
            self._menu(tr(Msg.NAME_CONFLICTS), options, body=tr(Msg.COUNT_CONFLICT_S_FOLDERS_ARE_NEVER_MERGED_OR_OVERWRITTEN, count=len(conflicts)))
            return
        self._file_start_job("move" if self.clipboard["move"] else "copy", paths, directory, policy)

    def _file_start_job(self, action, sources, directory, policy="error"):
        if self.mock:
            self.notify(tr(Msg.PREVIEW_ACTION_SIMULATED_NO_HARDWARE_CHANGES))
            return
        if self._file_active() or self.busy or not sources:
            self.notify(tr(Msg.WAIT_FOR_THE_CURRENT_FILE_OPERATION_TO_FINISH))
            return
        identifier = uuid.uuid4().hex
        self._file_job_cancel = threading.Event()
        self._file_job_clipboard = self.clipboard if action == "move" else None
        self._file_job_audible = bool(self._feedback_depth)
        self.file_task = {"id": identifier, "action": action, "sources": sources, "directory": directory,
                          "state": "preparing", "phase": "preparing", "doneBytes": 0, "totalBytes": 0,
                          "doneFiles": 0, "totalFiles": 0, "completedItems": 0, "skippedItems": 0}
        job = FileJob(self.operations, action, sources, directory, self._file_job_cancel,
                      lambda update: self.fileJobProgress.emit((identifier, update)), policy=policy, trash=self.trash_store)
        self._file_show_task()
        self._file_job_executor.submit(job.run).add_done_callback(
            lambda future: self.fileJobFinished.emit((identifier, future.result())) if not future.cancelled() else None)
        self._publish()

    def _file_task_summary(self):
        task = self.file_task
        if not task:
            return ""
        if task.get("state") == "cancelling":
            return tr(Msg.CANCELLING_SAFELY_COMPLETED_ITEMS_ARE_KEPT)
        if task.get("phase") == "preparing":
            return tr(Msg.PREPARING_FILE_TASK_CALCULATING_SIZE)
        if task.get("state") == "cancelled":
            return tr(Msg.CANCELLED_COUNT_COMPLETED_ITEM_S_WERE_KEPT, count=task.get("completedItems", 0))
        if task.get("state") in ("completed", "failed"):
            return tr(Msg.DONE_COMPLETED_SKIPPED_SKIPPED_FAILED_FAILED, done=task.get("completedItems", 0),
                      skipped=task.get("skippedItems", 0), failed=len(task.get("errors", [])))
        return tr(Msg.DONE_TOTAL_SPEED_S, done=FileOperations.format_size(task.get("doneBytes", 0)),
                  total=FileOperations.format_size(task.get("totalBytes", 0)),
                  speed=FileOperations.format_size(task.get("speed", 0)))

    def _file_show_task(self):
        labels = {"copy": tr(Msg.COPYING), "move": tr(Msg.MOVING), "trash": tr(Msg.MOVE_TO_TRASH), "restore": tr(Msg.RESTORE_SELECTED_ITEMS)}
        task = self.file_task
        if task:
            if not self._file_active() and task.get("errors"):
                self._menu(tr(Msg.FILE_TASK_ERRORS), [{"label": Path(error["path"]).name, "subtitle": error["reason"],
                                                    "wrapSubtitle": True, "action": "none"} for error in task["errors"]],
                           body=self._file_task_summary())
            else:
                self._push({"kind": "progress" if self._file_active() else "information", "title": labels[task["action"]],
                            "fileTaskId": task["id"], "body": self._file_task_summary(), "task": self._file_state()["task"]})

    def _file_cancel_task(self):
        if self._file_active():
            self.file_task["state"] = "cancelling"
            self._file_job_cancel.set()
            self._file_job_progress((self.file_task["id"], {}))

    def _file_job_progress(self, message):
        identifier, update = message
        if self._files_closing or identifier != self.file_task.get("id") or not self._file_active():
            return
        cancelling = self.file_task.get("state") == "cancelling"
        self.file_task.update(update)
        if cancelling:
            self.file_task["state"] = "cancelling"
        for modal in self._modals:
            if modal.get("fileTaskId") == identifier:
                modal.update(body=self._file_task_summary(), task=self._file_state()["task"])
        self._publish()

    def _file_job_finished(self, message):
        identifier, result = message
        if self._files_closing or identifier != self.file_task.get("id"):
            return
        foreground = self.modal.get("fileTaskId") == identifier
        self.file_task.update(result)
        if self.file_task["action"] == "move" and self.clipboard and self.clipboard is self._file_job_clipboard:
            completed = {entry["source"] for entry in result["completed"]}
            paths = self.clipboard.get("paths") or [self.clipboard["path"]]
            remaining = [path for path in paths if path not in completed]
            self.clipboard = {"paths": remaining, "path": remaining[0], "move": True} if remaining else None
        for index in range(len(self._modals) - 1, -1, -1):
            if self._modals[index].get("fileTaskId") == identifier:
                self._remove_modal(index)
        self.notify(self._file_task_summary())
        self._file_job_clipboard = None
        if self._file_job_audible:
            self.soundRequested.emit("back" if result.get("state") == "cancelled" else "error" if result["errors"] else "success")
            self._file_job_audible = False
        if result["errors"] and foreground:
            self._file_show_task()
        if self.navigation.page == "files":
            self._request_files_refresh()
        self._publish()

    def _file_modal(self, action):
        modal = self.modal
        if modal.get("fileTaskId") and modal.get("kind") == "progress":
            if action == "back":
                self._file_cancel_task()
            elif action == "accept":
                self._pop()
            self._publish()
            return True
        if modal.get("kind") == "file-preview":
            if action == "back":
                self._pop()
            elif action in ("up", "down", "left", "right"):
                self.filePreviewScroll.emit({"up": -80, "down": 80, "left": -200, "right": 200}[action])
            elif action == "accept" and not modal["item"].get("directory") and not modal["item"].get("trash"):
                item = modal["item"]
                self._pop()
                self._activate_file(item)
            self._publish()
            return True
        return False

    def _activate_file(self, item):
        if item.get("directory") and not item.get("trash"):
            self._browse(item["path"])
        elif self.mock:
            self.notify(tr(Msg.PREVIEW_OPEN_PREFIX) + item["name"])
        elif item.get("trash"):
            self._file_preview(item)
        else:
            self._run(tr(Msg.OPEN_FILE), lambda: self.operations.open(item["path"]))

    def _file_preview(self, item):
        owner = self.navigation.page, self.data["directory"]
        def loaded(result):
            if (self.navigation.page, self.data["directory"]) != owner or self.modal:
                return
            self._file_preview_text = result.pop("previewText", "")
            if item.get("trash"):
                details = result["body"].split("\n")
                result["body"] = item["originalPath"] + "\n" + details[1] + "\n" + tr(Msg.DELETED_DATE, date=item.get("deletedAt", ""))
            result.update(previewText=self._file_preview_text, item=item)
            self._push(result)
        if self.mock:
            loaded({"kind": "file-preview", "title": item["name"], "body": item["path"], "previewType": "metadata"})
        else:
            self._run(tr(Msg.PREVIEW_AND_DETAILS), lambda: preview(item["path"], name=item["name"]), loaded, report_success=False)

    def _file_open_with(self, item):
        handlers = self.catalog.handlers(item.get("mime", "application/octet-stream")) if not self.mock else []
        options = [{"label": tr(Msg.SYSTEM_DEFAULT_APPLICATION), "action": "files", "command": "open-default", "item": item}]
        options.extend({"label": entry["name"], "action": "files", "command": "open-using", "value": entry["id"], "item": item}
                       for entry in handlers)
        self._menu(tr(Msg.OPEN_WITH), options, body=tr(Msg.THIS_DOES_NOT_CHANGE_DEFAULT_FILE_ASSOCIATIONS))

    def _file_unmount(self, place):
        if self.mock:
            self.notify(tr(Msg.PREVIEW_ACTION_SIMULATED_NO_HARDWARE_CHANGES))
            return
        root = Path(place["path"]).resolve()
        sources = self.file_task.get("sources", []) if self._file_active() else []
        targets = [entry["path"] if isinstance(entry, dict) else entry for entry in sources]
        if self._file_active() and self.file_task.get("directory"):
            targets.append(self.file_task["directory"])
        if any(Path(path).resolve().is_relative_to(root) for path in targets):
            raise ValueError(tr(Msg.A_FILE_TASK_IS_USING_THIS_DEVICE_WAIT_FOR_IT_TO_FINISH))
        if self.data["directory"] != "trash:///" and Path(self.data["directory"]).resolve().is_relative_to(root):
            self.data["directory"] = str(Path.home())
            self._file_entries, self.data["files"] = [], []
            self.file_query, self.file_marked, self.file_selection = "", set(), False
            self.file_section = "list"
            self.file_breadcrumb_index = len(self._file_breadcrumbs()) - 1
            if self.navigation.page == "files":
                self.navigation.select(0)
            self._file_watch()
        self._run(tr(Msg.SAFELY_UNMOUNT), lambda: unmount(place), lambda result: self._browse(self.data["directory"]))

    def _close_files(self):
        self._files_closing = True
        self._file_job_cancel.set()
        self._file_refresh_timer.stop()
        self._file_location_timer.stop()
        watched = self._file_watcher.directories() + self._file_watcher.files()
        if watched:
            self._file_watcher.removePaths(watched)
        self._file_job_executor.shutdown(wait=True, cancel_futures=True)
