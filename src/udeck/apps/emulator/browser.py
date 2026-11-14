"""Two-level platform browsing, with independent focus and searches per collection."""


from PySide6.QtCore import Slot

from udeck.apps.emulator.platform_icons import platform_icon
from udeck.i18n import Msg, tr
from udeck.sounds import interaction


def game_count(count):
    return tr(Msg.EMULATOR_ONE_GAME) if count == 1 else tr(Msg.EMULATOR_GAME_COUNT, count=count)


class EmulatorBrowser:
    def __init__(self, *args, **kwargs):
        self.platform = "All"
        self._searches = {}
        self._core_view_state = None
        self._platform_index = 0
        super().__init__(*args, **kwargs)

    def _scope(self):
        return f"1:{self.platform}" if self.tab == 1 and self.platform != "All" else str(self.tab)

    def _remember_browser(self):
        scope = self._scope()
        self.store.data["focus"][scope] = self.selected
        self._searches[scope] = self.filter

    def _restore_browser(self):
        scope = self._scope()
        self.selected = self.store.data["focus"].get(scope, "")
        self.filter = self._searches.get(scope, "")

    def persist(self):
        self._remember_browser()
        if self.library.suspended:
            return
        self.store.save()

    def _sync_core_browser(self):
        state = (id(self.catalog), tuple((c.id, c.status) for c in self.catalog.cores.values()),
                 tuple(sorted(self.catalog.preferences.get("coreEnabled", {}).items())),
                 tuple((p["id"], p["count"], str(p["error"])) for p in self.library.playlists))
        if state != self._core_view_state:
            self._core_view_state = state
            self._row_revision += 1
            self._availability = {}
        if (self.tab == 1 and self.platform != "All" and self.page == "library"
                and self.platform not in {p["id"] for p in self.library.playlists}):
            self._return_to_platforms()

    def _view_rows(self):
        self._sync_core_browser()
        return super()._view_rows()

    def rows(self):
        self._sync_core_browser()
        query = self.filter.casefold()
        if self.tab == 1 and self.platform == "All":
            rows = []
            for playlist in self.library.playlists:
                platform = self.catalog.platform_for_database(playlist["title"])
                names = " ".join((playlist["title"], platform.id, *platform.aliases)) if platform else playlist["title"]
                if query and query not in names.casefold():
                    continue
                rows.append({"id": playlist["id"], "kind": "playlist", "title": playlist["title"],
                             "subtitle": playlist["error"] or game_count(playlist["count"]),
                             "gameCount": playlist["count"], "cover": platform_icon(platform.id if platform else ""),
                             "playlistPath": playlist["path"]})
            return rows
        items = self.library.items
        if self.tab == 1:
            items = [i for i in items if i.get("playlistId") == self.platform]
        else:
            choices = self.store.data["preferences"].get("entryChoices", {})
            unique = {}
            for item in items:
                if item["id"] not in unique or item.get("entryId") == choices.get(item["id"]):
                    unique[item["id"]] = item
            order = self.store.data["recent" if self.tab == 0 else "favorites"]
            items = [unique[i] for i in order if i in unique]
        rows = []
        for item in items:
            if query and query not in (str(item["title"]) + " " + item.get("relative", "")).casefold():
                continue
            platform = self.catalog.platforms.get(self.catalog.canonical(item["platform"]))
            key = (item["platform"], item.get("format"), item.get("playlistCoreId"), item.get("playlistDefaultCoreId"))
            if key not in self._availability:
                try:
                    self.catalog.resolve(item)
                    self._availability[key] = ""
                except ValueError as error:
                    from udeck.i18n import error_text

                    self._availability[key] = error_text(error)
            rows.append({**item, "id": item.get("entryId", item["id"]), "gameId": item["id"],
                         "subtitle": item.get("contentError") or self._availability[key]
                         or (platform.title if platform else item.get("dbName", ""))})
        return rows

    def activate(self, row):
        if row.get("kind") != "playlist":
            return super().activate(row)
        platform = row["id"]
        self._platform_index = max(0, self.selectedIndex)
        self._remember_browser()
        self.feedback("open")
        self.platform = platform
        self._restore_browser()

    def _return_to_platforms(self):
        self._remember_browser()
        self.platform, self.page, self.folder = "All", "library", ""
        self.history.clear()
        self._restore_browser()
        rows = self.rows()
        if self.selected not in {row["id"] for row in rows}:
            # The previous card model contains games, so reconcile against the
            # platform position saved before entering the now-disabled platform.
            self.selected = rows[min(self._platform_index, len(rows) - 1)]["id"] if rows else ""

    def back(self):
        if self.page == "library" and self.tab == 1 and self.platform != "All":
            self._return_to_platforms()
        else:
            super().back()

    @Slot(int)
    @interaction
    def setTab(self, index):
        if not 0 <= index < len(self.tabs()):
            return
        self._remember_browser()
        if index != self.tab or self.page != "library" or self.platform != "All":
            self.feedback("open")
        self.tab, self.page, self.folder, self.platform = index, "library", "", "All"
        self.history.clear()
        self._restore_browser()
        self.publish()

    def browser_state(self):
        collections = self.tab == 1 and self.platform == "All"
        playlist = next((p for p in self.library.playlists if p["id"] == self.platform), None) if self.tab == 1 else None
        count = len(self._rows)
        hint = tr(Msg.EMULATOR_NO_SEARCH_MATCHES) if self.filter else tr(
            Msg.EMU_EMPTY_PLAYLIST if playlist else Msg.EMU_PLAYLIST_HINT)
        return {"platformsView": collections, "playlistsView": collections,
                "platformTitle": playlist["title"] if playlist else "",
                "playlistTitle": playlist["title"] if playlist else "",
                "countLabel": str(count) if collections else game_count(count), "emptyHint": hint}
