"""Handheld Emulator settings, using the suite's existing focus and menu stack."""

from pathlib import Path

from PySide6.QtCore import QSignalBlocker

from udeck.apps.emulator.catalog import message_lines
from udeck.apps.emulator.library import confined_path, create_platform_directories
from udeck.i18n import tr


class EmulatorSettings:
    def settings(self):
        self.cancel_launch()
        self.menu(tr("Settings"), [
            (tr("ROM root"), self.rom_picker, self.library.root_path, "folder"),
            (tr("Create platform folders"), self.confirm_platform_folders,
             tr("Create folders for enabled platforms; existing files are kept."), "folder-new"),
            (tr("Core management"), self.core_management,
             tr("{count} installed cores", count=len(self.catalog.cores)), "applications-system"),
            (tr("Add engine entry"), self.engine_platform_menu, "", "list-add"),
            (tr("Core folder"), lambda: self.folder_picker("coreDirectory", "/usr/lib/aarch64-linux-gnu/libretro"), "", "folder"),
            (tr("Firmware folder"), lambda: self.folder_picker("firmwareDirectory", str(Path.home() / ".config/retroarch/system")), "", "folder"),
            (tr("Refresh library"), self.refresh, "", "view-refresh"),
            (tr("Close application"), self.requestClose, "", "window-close")], self.scan_description(), icon="preferences-system")

    def scan_description(self):
        return tr("Scanning…") if self.library.pending else (
            message_lines(e for e in self.library.errors.values() if e) or
            tr("Platform folders only: gba/ · psp/ · psx/ · dreamcast/"))

    def rom_picker(self):
        self.path_picker(self.library.root_path, self.set_rom_root)

    def set_rom_root(self, path):
        self.library.configure_root(path)
        self.cancel_launch()
        self.tab, self.page = 1, "library"
        self.clear_menus()
        self.notice = tr("ROM root updated")

    def folder_picker(self, key, default):
        def chosen(path):
            value = str(Path(path).expanduser().resolve(strict=True))
            if not Path(value).is_dir():
                raise ValueError(tr("Folder does not exist"))
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
            options.append((tr("Use this folder"), lambda: callback(str(path)), "", "emblem-default"))
        if path != path.parent and (boundary is None or path != Path(boundary)):
            options.append((tr("Parent folder"), lambda: navigate(path.parent), "", "go-up"))
        if boundary is None:
            options.append((tr("Enter path"), lambda: self.prompt(tr("Folder path"),
                           lambda text: self.picker_path(text, callback), str(path)), "", "document-edit"))
        for entry in entries:
            if entry.is_symlink() or entry.name.startswith("."):
                continue
            if entry.is_dir():
                options.append(("▸ " + entry.name, lambda p=entry: navigate(p), "", "folder"))
            elif file_filter and file_filter(entry):
                options.append((entry.name, lambda p=entry: callback(str(p)), "", "application-x-executable"))
        options.append((tr("Cancel"), self.pop_menu, "", "go-previous"))
        self.menu(tr("Choose a file") if file_filter else tr("Choose a folder"), options, str(path), owner="picker", icon="folder")
        self.menus[-1].update(picker=True, pickerParent=(lambda: navigate(path.parent))
                             if path != path.parent and (boundary is None or path != Path(boundary)) else None)

    def picker_path(self, text, callback):
        path = Path(text).expanduser().resolve(strict=True)
        if not path.is_dir():
            raise ValueError(tr("Folder does not exist"))
        callback(str(path))
        # Callback may clear all menus (ROM root), or remove the prompt (folders).
        if self.menus and self.menus[-1].get("picker"):
            self.pop_menu()

    def confirm_platform_folders(self):
        self.menu(tr("Create platform folders?"), [(tr("Create"), self.make_platform_folders, "", "folder-new"),
                  (tr("Cancel"), self.pop_menu, "", "go-previous")], self.library.root_path)

    def make_platform_folders(self):
        created = create_platform_directories(self.library.root_path, self.catalog)
        self.library.configure_root(self.library.root_path)
        self.clear_menus()
        self.notice = tr("Created or kept {count} platform folders", count=len(created))
        self.settings()

    def core_status(self, core, platform=None):
        if core.status == "incompatible":
            return tr("Cannot load: {reason}", reason=core.reason)
        if core.status == "unverified":
            return tr("Checking…")
        return tr("Enabled · load checked") if self.catalog.enabled(core, platform) else tr("Disabled · load checked")

    def core_management(self, quiet=False):
        options = [(tr("Search cores"), lambda: self.prompt(tr("Search cores"), self.core_search), "", "edit-find"),
                   (tr("Refresh core list"), self.refresh_catalog, "", "view-refresh")]
        for platform in sorted(self.catalog.platforms.values(), key=lambda p: p.title.casefold()):
            cores = self.catalog.platform_cores(platform.id)
            if not cores:
                continue
            enabled = sum(self.catalog.enabled(c, platform.id) and c.status != "incompatible" for c in cores)
            options.append((platform.title, lambda p=platform.id: self.platform_cores_menu(p),
                            tr("{enabled}/{total} enabled · {directory}/", enabled=enabled,
                               total=len(cores), directory=platform.directory)))
        if not self.catalog.cores:
            options.append((tr("No installed cores found"), None))
        self.menu(tr("Core management"), options,
                  tr("{count} installed cores · {pending} checking. Loading checks do not verify gameplay.",
                     count=len(self.catalog.cores), pending=self.cores_pending), quiet=quiet, icon="applications-system")
        self.menus[-1].update(coreView="catalog")

    def core_search(self, text):
        self.pop_menu()
        self.core_search_results(text.strip().casefold())

    def core_search_results(self, query, quiet=False):
        cores = [c for c in self.catalog.cores.values() if query in
                 (c.id + " " + c.name + " " + " ".join(c.platforms)).casefold()]
        self.menu(tr("Search cores"), [(c.name, lambda c=c: self.core_details(c.id),
                  c.id + " · " + self.core_status(c)) for c in sorted(cores, key=lambda c: c.name.casefold())],
                  tr("{count} matching cores", count=len(cores)), quiet=quiet, icon="applications-system")
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
            raise ValueError(tr("Selected core is unavailable: {core}", core=identifier))
        enable = not self.catalog.enabled(core, platform)
        options = [(tr("Enable core") if enable else tr("Disable core"),
                    (lambda: self.toggle_core(identifier, enable, platform))
                    if not enable or core.status == "available" else None, "", "emblem-default" if enable else "process-stop")]
        if self.catalog.enabled(core, platform) and core.status == "available":
            if platform:
                options.append((tr("Use as platform default"), lambda: self.set_default_core(platform, identifier), "", "emblem-default"))
            else:
                options.extend((tr("Default for {platform}", platform=self.catalog.platforms[p].title),
                                lambda p=p: self.set_default_core(p, identifier), "", "emblem-default") for p in core.platforms)
            if core.no_content:
                options.append((tr("Run core without content"), lambda: self.run_core(identifier, platform), "", "media-playback-start"))
        options.append((tr("Back"), self.pop_menu, "", "go-previous"))
        formats = " · ".join(core.extensions) or tr("No content required")
        self.menu(core.name, options, message_lines([
            core.id + (" · " + core.version if core.version else ""), self.core_status(core, platform),
            " / ".join(self.catalog.platforms[p].directory + "/" for p in core.platforms),
            tr("Formats: {formats}", formats=formats),
            tr("Save states supported") if core.savestate else tr("This core does not support save states")]), quiet=quiet)
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
            raise ValueError(tr("Selected core is unavailable: {core}", core=identifier))
        self.store.data["preferences"].setdefault("coreEnabled", {})[identifier] = enabled
        self.persist()
        self.library.refresh()
        self.pop_menu()
        self.core_details(identifier, platform)

    def set_default_core(self, platform, identifier):
        self.store.data["preferences"].setdefault("platformCores", {})[platform] = identifier
        self.persist()
        self.notice = tr("Platform default updated")
        self.pop_menu()

    def choose_game_core(self):
        platform = self.catalog.canonical(self.current["platform"])
        cores = self.catalog.candidates(platform, Path(self.current["path"]).suffix)
        options = [(tr("Use platform default"), lambda: self.set_game_core(None))]
        options.extend((c.name, lambda c=c: self.set_game_core(c.id), c.id + " · " + self.core_status(c, platform))
                       for c in cores if c.status == "available")
        self.menu(tr("Choose core"), options, tr("Only enabled cores supporting this format are listed."))

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
        self.menu(tr("Add engine entry"), [(p.title, lambda p=p: self.engine_entry_picker(p.id), p.directory + "/")
                  for p in self.catalog.platforms.values() if p.mode in ("manual", "dos", "scummvm")
                  and self.catalog.candidates(p.id)],
                  tr("Choose the launch file, not the folder containing game assets."), icon="input-gaming")

    def engine_entry_picker(self, platform):
        root = Path(self.library.root_path)
        if not root.is_dir():
            raise ValueError(tr("Create the platform folder first: {directory}", directory=self.catalog.platforms[platform].directory))
        directories = [p for p in root.iterdir() if p.is_dir() and not p.is_symlink()
                       and self.catalog.platform_for_directory(p.name) is self.catalog.platforms[platform]]
        if not directories:
            raise ValueError(tr("Create the platform folder first: {directory}", directory=self.catalog.platforms[platform].directory))
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
