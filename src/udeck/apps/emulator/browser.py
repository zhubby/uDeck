"""Two-level platform browsing, with independent focus and searches per collection."""

from collections import Counter
from pathlib import Path

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
        self.store.save()

    def _sync_core_browser(self):
        # Core switches and probe results mutate the catalogue in place. They
        # must invalidate cards even before the asynchronous ROM scan finishes.
        state = (id(self.catalog), tuple((c.id, c.status) for c in self.catalog.cores.values()),
                 tuple(sorted(self.catalog.preferences.get("coreEnabled", {}).items())))
        if state != self._core_view_state:
            self._core_view_state = state
            self._row_revision += 1
            if (self.tab == 1 and self.platform != "All" and self.page == "library"
                    and not self.catalog.candidates(self.platform)):
                self._return_to_platforms()

    def _view_rows(self):
        self._sync_core_browser()
        return super()._view_rows()

    def rows(self):
        self._sync_core_browser()
        if self.tab == 1 and self.platform == "All":
            counts = Counter(self.catalog.canonical(item["platform"]) for item in self.library.items
                             if item["sourceId"] == self.library.root_id
                             and item["sourceId"] not in self.library.unavailable)
            query = self.filter.casefold()
            return [{"id": "platform:" + p.id, "kind": "platform", "platformId": p.id,
                     "title": p.title, "subtitle": game_count(counts[p.id]),
                     "gameCount": counts[p.id], "cover": platform_icon(p.id)}
                    for p in sorted(self.catalog.platforms.values(), key=lambda p: p.title.casefold())
                    if self.catalog.candidates(p.id) and (not query or query in
                        " ".join((p.id, p.title, p.directory, *p.aliases)).casefold())]
        rows = [r for r in super().rows() if r["sourceId"] == self.library.root_id]
        if self.tab == 0:
            order = self.store.data["recent"]
            rows = [r for r in rows if r["id"] in order]
            rows.sort(key=lambda r: order.index(r["id"]))
        elif self.tab == 2:
            rows = [r for r in rows if r["id"] in self.store.data["favorites"]]
        if self.tab == 1 and self.platform != "All":
            rows = [r for r in rows if self.catalog.canonical(r["platform"]) == self.platform]
        return [{**r, "subtitle": self.catalog.platforms[self.catalog.canonical(r["platform"])].title
                 if self.catalog.canonical(r["platform"]) in self.catalog.platforms else r["platform"]}
                for r in rows]

    def activate(self, row):
        if row.get("kind") != "platform":
            return super().activate(row)
        platform = row["platformId"]
        if not self.catalog.candidates(platform):
            return
        self._remember_browser()
        self.feedback("open")
        self.platform = platform
        self._restore_browser()

    def _return_to_platforms(self):
        self._remember_browser()
        self.platform, self.page, self.folder = "All", "library", ""
        self.history.clear()
        self._restore_browser()

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
        platforms = self.tab == 1 and self.platform == "All"
        platform = self.catalog.platforms.get(self.platform) if self.tab == 1 else None
        count = len(self._rows)
        if self.filter:
            hint = tr(Msg.EMULATOR_NO_SEARCH_MATCHES)
        elif platforms:
            hint = tr(Msg.EMULATOR_ENABLE_CORES_HINT)
        else:
            hint = tr(Msg.EMULATOR_PLATFORM_GAMES_HINT,
                      path=str(Path(self.library.root_path) / platform.directory)) if platform else tr(
                          Msg.ROM_ROOT_PATH_USE_PLATFORM_FOLDERS_GBA_PSP_PSX_DREAMCAST,
                          path=self.library.root_path)
        return {"platformsView": platforms, "platformTitle": platform.title if platform else "",
                "countLabel": (tr(Msg.EMULATOR_ONE_PLATFORM) if count == 1 else
                               tr(Msg.EMULATOR_PLATFORM_COUNT, count=count)) if platforms else game_count(count),
                "emptyHint": hint}
