"""Background core validation and launch preparation; all UI writes stay on Qt."""

from concurrent.futures import ThreadPoolExecutor, as_completed

from PySide6.QtCore import QObject, QRunnable, Signal

from ..i18n import error_text
from .game_catalog import CoreCatalog, probe_core


class InventorySignals(QObject):
    discovered = Signal(int, object)
    progress = Signal(int, str, object)
    done = Signal(int, object)


class CoreInventoryTask(QRunnable):
    def __init__(self, generation, preferences, cache, cancel):
        super().__init__()
        self.generation, self.preferences, self.cache, self.cancel = generation, preferences, cache, cancel
        self.signals = InventorySignals()

    def run(self):
        if self.cancel.is_set():
            return
        catalog = CoreCatalog.discover(self.preferences)
        pending, cache = [], {}
        for core in catalog.cores.values():
            previous = self.cache.get(core.signature)
            if isinstance(previous, dict) and previous.get("status") in ("available", "incompatible"):
                catalog.apply_probe(core.id, previous)
                cache[core.signature] = previous
            else:
                pending.append(core)
        if self.cancel.is_set():
            return
        self.signals.discovered.emit(self.generation, catalog)
        with ThreadPoolExecutor(max_workers=2, thread_name_prefix="udeck-core-probe") as pool:
            futures = {pool.submit(probe_core, core.path): core for core in pending}
            for future in as_completed(futures):
                if self.cancel.is_set():
                    for remaining in futures:
                        remaining.cancel()
                    return
                core = futures[future]
                result = future.result()
                cache[core.signature] = result
                self.signals.progress.emit(self.generation, core.id, result)
        if not self.cancel.is_set():
            self.signals.done.emit(self.generation, cache)


class LaunchSignals(QObject):
    done = Signal(int, object)


class LaunchTask(QRunnable):
    def __init__(self, generation, item, preferences, catalog, cancel):
        super().__init__()
        self.generation, self.item, self.preferences, self.catalog = generation, item, preferences, catalog
        self.signals = LaunchSignals()
        self.cancel = cancel

    def run(self):
        from .games import preflight

        try:
            checks = preflight(self.item, self.preferences, catalog=self.catalog, cancelled=self.cancel.is_set)
        except (OSError, ValueError, RuntimeError) as error:
            checks = {"ready": False, "errors": [error_text(error)]}
        self.signals.done.emit(self.generation, checks)
