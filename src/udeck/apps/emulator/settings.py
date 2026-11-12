"""Handheld Emulator settings, using the suite's existing focus and menu stack."""

from pathlib import Path

from PySide6.QtCore import QSignalBlocker

from udeck.apps.emulator.catalog import message_lines
from udeck.apps.emulator.library import confined_path, create_platform_directories
from udeck.i18n import Msg, tr


class EmulatorSettings:
    def settings(self):
        self.cancel_launch()
        self.menu(tr(Msg.SETTINGS), self.settings_options, self.scan_description(), icon="preferences-system", settings=True)

    def settings_options(self):
        option = self.setting_option
        core_folder = self.store.data["preferences"].get("coreDirectory", "/usr/lib/aarch64-linux-gnu/libretro")
        firmware_folder = self.store.data["preferences"].get("firmwareDirectory", str(Path.home() / ".config/retroarch/system"))
        return [
            option(tr(Msg.ROM_ROOT), self.rom_picker, "folder", self.library.root_path, path=True),
            option(tr(Msg.CREATE_PLATFORM_FOLDERS), self.confirm_platform_folders, "folder-new"),
            option(tr(Msg.CORE_MANAGEMENT), self.core_management, "applications-system", tr(Msg.COUNT_INSTALLED_CORES, count=len(self.catalog.cores))),
            option(tr(Msg.ADD_ENGINE_ENTRY), self.engine_platform_menu, "list-add"),
            option(tr(Msg.CORE_FOLDER), lambda: self.folder_picker("coreDirectory", "/usr/lib/aarch64-linux-gnu/libretro"), "folder", core_folder, path=True),
            option(tr(Msg.FIRMWARE_FOLDER), lambda: self.folder_picker("firmwareDirectory", str(Path.home() / ".config/retroarch/system")), "folder", firmware_folder, path=True),
            option(tr(Msg.REFRESH_LIBRARY), self.refresh, "view-refresh"),
            option(tr(Msg.CLOSE_APPLICATION), self.requestClose, "window-close")]

    def scan_description(self):
        return tr(Msg.SCANNING) if self.library.pending else (
            message_lines(e for e in self.library.errors.values() if e) or
            tr(Msg.PLATFORM_FOLDERS_ONLY_GBA_PSP_PSX_DREAMCAST))

    def rom_picker(self):
        self.path_picker(self.library.root_path, self.set_rom_root)

    def set_rom_root(self, path):
        self.library.configure_root(path)
        self.cancel_launch()
        self.tab, self.page = 1, "library"
        self.clear_menus()
        self.notice = tr(Msg.ROM_ROOT_UPDATED)

    def folder_picker(self, key, default):
        def chosen(path):
            value = str(Path(path).expanduser().resolve(strict=True))
            if not Path(value).is_dir():
                raise ValueError(tr(Msg.FOLDER_DOES_NOT_EXIST))
            self.store.data["preferences"][key] = value
            self.persist()
            self.pop_menu()
            if key == "coreDirectory":
                self.refresh_catalog()
            elif self.current and not self.engine.running():
                self.update_checks()
        self.path_picker(self.store.data["preferences"].get(key, default), chosen)

    def path_picker(self, start, callback, boundary=None, file_filter=None, replace=False):
        path = Path(start).expanduser()
        while not path.is_dir() and path != path.parent:
            path = path.parent
        if boundary is not None:
            path = confined_path(path, boundary)
        else:
            path = path.resolve(strict=True)
        # List before replacing the previous picker, so permission failures keep it.
        entries = sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.casefold()))
        if replace:
            self.pop_menu()
        def navigate(target):
            self.path_picker(target, callback, boundary, file_filter, replace=True)
        options = []
        if file_filter is None:
            options.append((tr(Msg.USE_THIS_FOLDER), lambda: callback(str(path)), "", "emblem-default"))
        if path != path.parent and (boundary is None or path != Path(boundary)):
            options.append((tr(Msg.PARENT_FOLDER), lambda: navigate(path.parent), "", "go-up"))
        if boundary is None:
            options.append((tr(Msg.ENTER_PATH), lambda: self.prompt(tr(Msg.FOLDER_PATH),
                           lambda text: self.picker_path(text, callback), str(path)), "", "document-edit"))
        for entry in entries:
            if entry.is_symlink() or entry.name.startswith("."):
                continue
            if entry.is_dir():
                options.append(self.setting_option(entry.name, lambda p=entry: navigate(p), "folder"))
            elif file_filter and file_filter(entry):
                options.append((entry.name, lambda p=entry: callback(str(p)), "", "application-x-executable"))
        options.append((tr(Msg.CANCEL), self.pop_menu, "", "go-previous"))
        self.menu(tr(Msg.CHOOSE_A_FILE) if file_filter else tr(Msg.CHOOSE_A_FOLDER), options, str(path), owner="picker", icon="folder")
        self.menus[-1].update(picker=True, pickerParent=(lambda: navigate(path.parent))
                             if path != path.parent and (boundary is None or path != Path(boundary)) else None)

    def picker_path(self, text, callback):
        path = Path(text).expanduser().resolve(strict=True)
        if not path.is_dir():
            raise ValueError(tr(Msg.FOLDER_DOES_NOT_EXIST))
        callback(str(path))
        # Callback may clear all menus (ROM root), or remove the prompt (folders).
        if self.menus and self.menus[-1].get("picker"):
            self.pop_menu()

    def confirm_platform_folders(self):
        self.menu(tr(Msg.CREATE_PLATFORM_FOLDERS_PROMPT), [(tr(Msg.CREATE), self.make_platform_folders, "", "folder-new"),
                  (tr(Msg.CANCEL), self.pop_menu, "", "go-previous")], self.library.root_path)

    def make_platform_folders(self):
        created = create_platform_directories(self.library.root_path, self.catalog)
        self.library.configure_root(self.library.root_path)
        self.clear_menus()
        self.notice = tr(Msg.CREATED_OR_KEPT_COUNT_PLATFORM_FOLDERS, count=len(created))
        self.settings()

    def core_status(self, core, platform=None):
        if core.status == "incompatible":
            return tr(Msg.CANNOT_LOAD_REASON, reason=core.reason)
        if core.status == "unverified":
            return tr(Msg.CHECKING)
        return tr(Msg.ENABLED_LOAD_CHECKED) if self.catalog.enabled(core, platform) else tr(Msg.DISABLED_LOAD_CHECKED)

    def core_management(self, quiet=False):
        options = [(tr(Msg.SEARCH_CORES), lambda: self.prompt(tr(Msg.SEARCH_CORES), self.core_search), "", "edit-find"),
                   (tr(Msg.REFRESH_CORE_LIST), self.refresh_catalog, "", "view-refresh")]
        for platform in sorted(self.catalog.platforms.values(), key=lambda p: p.title.casefold()):
            cores = self.catalog.platform_cores(platform.id)
            if not cores:
                continue
            enabled = sum(self.catalog.enabled(c, platform.id) and c.status != "incompatible" for c in cores)
            options.append((platform.title, lambda p=platform.id: self.platform_cores_menu(p),
                            tr(Msg.ENABLED_TOTAL_ENABLED_DIRECTORY, enabled=enabled,
                               total=len(cores), directory=platform.directory)))
        if not self.catalog.cores:
            options.append((tr(Msg.NO_INSTALLED_CORES_FOUND), None))
        self.menu(tr(Msg.CORE_MANAGEMENT), options,
                  tr(Msg.COUNT_INSTALLED_CORES_PENDING_CHECKING_LOADING_CHECKS_DO_NOT_VERIFY_GAMEPLAY,
                     count=len(self.catalog.cores), pending=self.cores_pending), quiet=quiet, icon="applications-system", settings=True)
        self.menus[-1].update(coreView="catalog")

    def core_search(self, text):
        self.pop_menu()
        self.core_search_results(text.strip().casefold())

    def core_search_results(self, query, quiet=False):
        cores = [c for c in self.catalog.cores.values() if query in
                 (c.id + " " + c.name + " " + " ".join(c.platforms)).casefold()]
        self.menu(tr(Msg.SEARCH_CORES), [(c.name, lambda c=c: self.core_details(c.id),
                  c.id + " · " + self.core_status(c)) for c in sorted(cores, key=lambda c: c.name.casefold())],
                  tr(Msg.COUNT_MATCHING_CORES, count=len(cores)), quiet=quiet, icon="applications-system")
        self.menus[-1].update(coreView="search", coreQuery=query)

    def platform_cores_menu(self, platform, quiet=False):
        value = self.catalog.platforms.get(platform)
        if not value:
            self.core_management(quiet=quiet)
            return
        default = self.store.data["preferences"].get("platformCores", {}).get(platform)
        if not default:
            recommended = self.catalog.recommended(platform)
            default = recommended.id if recommended else ""
        self.menu(value.title, [(c.name, lambda c=c: self.core_details(c.id, platform),
                  ("★ " if c.id == default else "") + c.id + " · " + self.core_status(c, platform))
                  for c in self.catalog.platform_cores(platform)],
                  str(Path(self.library.root_path) / value.directory), quiet=quiet, icon="applications-system")
        self.menus[-1].update(coreView="platform", platformId=platform)

    def core_details(self, identifier, platform=None, quiet=False):
        core = self.catalog.cores.get(identifier)
        if not core:
            raise ValueError(tr(Msg.SELECTED_CORE_IS_UNAVAILABLE_CORE, core=identifier))
        enable = not self.catalog.enabled(core, platform)
        options = [self.setting_option(tr(Msg.ENABLE_CORE),
                    (lambda: self.toggle_core(identifier, enable, platform))
                    if not enable or core.status == "available" else None,
                    "emblem-default" if enable else "process-stop", checked=not enable)]
        if self.catalog.enabled(core, platform) and core.status == "available":
            if platform:
                options.append((tr(Msg.USE_AS_PLATFORM_DEFAULT), lambda: self.set_default_core(platform, identifier), "", "emblem-default"))
            else:
                options.extend((tr(Msg.DEFAULT_FOR_PLATFORM, platform=self.catalog.platforms[p].title),
                                lambda p=p: self.set_default_core(p, identifier), "", "emblem-default") for p in core.platforms)
            if core.no_content:
                options.append((tr(Msg.RUN_CORE_WITHOUT_CONTENT), lambda: self.run_core(identifier, platform), "", "media-playback-start"))
        options.append((tr(Msg.BACK), self.pop_menu, "", "go-previous"))
        formats = " · ".join(core.extensions) or tr(Msg.NO_CONTENT_REQUIRED)
        self.menu(core.name, options, message_lines([
            core.id + (" · " + core.version if core.version else ""), self.core_status(core, platform),
            " / ".join(self.catalog.platforms[p].directory + "/" for p in core.platforms),
            tr(Msg.FORMATS_FORMATS, formats=formats),
            tr(Msg.SAVE_STATES_SUPPORTED) if core.savestate else tr(Msg.THIS_CORE_DOES_NOT_SUPPORT_SAVE_STATES)]), quiet=quiet, settings=True)
        self.menus[-1].update(coreView="detail", coreId=identifier, platformId=platform)

    def refresh_core_menu(self, identifier=None):
        if not any(menu.get("coreView") for menu in self.menus):
            return
        original = self.menus
        # Reconcile ancestors too: Back must never expose callbacks from an old
        # catalogue. Publish once so a search prompt keeps its draft and focus.
        with QSignalBlocker(self):
            self.menus = []
            for position, menu in enumerate(original):
                view = menu.get("coreView")
                platform, core_id = menu.get("platformId"), menu.get("coreId")
                if view and ((platform and platform not in self.catalog.platforms)
                             or (core_id and core_id not in self.catalog.cores)):
                    for discarded in original[position:]:
                        for row in discarded["options"]:
                            self._callbacks.pop(row["id"], None)
                    break
                if not view or (view == "detail" and identifier and core_id != identifier):
                    self.menus.append(menu)
                    continue
                selected = menu["options"][menu["index"]]["title"]
                for row in menu["options"]:
                    self._callbacks.pop(row["id"], None)
                if view == "catalog":
                    self.core_management(quiet=True)
                elif view == "platform":
                    self.platform_cores_menu(platform, quiet=True)
                elif view == "search":
                    self.core_search_results(menu["coreQuery"], quiet=True)
                else:
                    self.core_details(core_id, platform, quiet=True)
                refreshed = self.menus[-1]
                refreshed["index"] = next((i for i, row in enumerate(refreshed["options"])
                    if row["title"] == selected and not row["disabled"]), refreshed["index"])
            if not self.menus:
                self.core_management(quiet=True)
        self.publish()

    def toggle_core(self, identifier, enabled, platform=None):
        core = self.catalog.cores[identifier]
        if enabled and core.status != "available":
            raise ValueError(tr(Msg.SELECTED_CORE_IS_UNAVAILABLE_CORE, core=identifier))
        self.store.data["preferences"].setdefault("coreEnabled", {})[identifier] = enabled
        self.persist()
        self.library.refresh()
        self.pop_menu()
        self.core_details(identifier, platform)

    def set_default_core(self, platform, identifier):
        self.store.data["preferences"].setdefault("platformCores", {})[platform] = identifier
        self.persist()
        self.notice = tr(Msg.PLATFORM_DEFAULT_UPDATED)
        self.pop_menu()

    def choose_game_core(self):
        platform = self.catalog.canonical(self.current["platform"])
        cores = self.catalog.candidates(platform, Path(self.current["path"]).suffix)
        options = [(tr(Msg.USE_PLATFORM_DEFAULT), lambda: self.set_game_core(None))]
        options.extend((c.name, lambda c=c: self.set_game_core(c.id), c.id + " · " + self.core_status(c, platform))
                       for c in cores if c.status == "available")
        self.menu(tr(Msg.CHOOSE_CORE), options, tr(Msg.ONLY_ENABLED_CORES_SUPPORTING_THIS_FORMAT_ARE_LISTED))

    def set_game_core(self, identifier):
        choices = self.store.data["preferences"].setdefault("gameCores", {})
        if identifier:
            choices[self.current["id"]] = identifier
        else:
            choices.pop(self.current["id"], None)
        self.persist()
        self.update_checks()
        self.pop_menu()

    def engine_platform_menu(self):
        self.menu(tr(Msg.ADD_ENGINE_ENTRY), [(p.title, lambda p=p: self.engine_entry_picker(p.id), p.directory + "/")
                  for p in self.catalog.platforms.values() if p.mode in ("manual", "dos", "scummvm")
                  and self.catalog.candidates(p.id)],
                  tr(Msg.CHOOSE_THE_LAUNCH_FILE_NOT_THE_FOLDER_CONTAINING_GAME_ASSETS), icon="input-gaming")

    def engine_entry_picker(self, platform):
        root = Path(self.library.root_path)
        if not root.is_dir():
            raise ValueError(tr(Msg.CREATE_THE_PLATFORM_FOLDER_FIRST_DIRECTORY, directory=self.catalog.platforms[platform].directory))
        directories = [p for p in root.iterdir() if p.is_dir() and not p.is_symlink()
                       and self.catalog.platform_for_directory(p.name) is self.catalog.platforms[platform]]
        if not directories:
            raise ValueError(tr(Msg.CREATE_THE_PLATFORM_FOLDER_FIRST_DIRECTORY, directory=self.catalog.platforms[platform].directory))
        def chosen(path):
            entries = self.store.data["preferences"].setdefault("engineEntries", [])
            if path not in entries:
                entries.append(path)
            self.persist()
            self.library.refresh()
            self.clear_menus()
            self.page, self.tab = "library", 1
        self.path_picker(directories[0], chosen, boundary=directories[0], file_filter=lambda p:
                         any(c.supports(p.suffix) for c in self.catalog.candidates(platform)))

    def sources_menu(self):
        self.rom_picker()

    def show_rom_root(self):
        self.cancel_launch()
        self.page, self.tab = "library", 1
        self.clear_menus()
