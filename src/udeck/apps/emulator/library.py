"""Platform-directory scanning with bounded disc references."""

import copy
import hashlib
import os
import re
import shlex
import threading
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import QRunnable, QThreadPool

from udeck.apps.common.library import Library, ScanSignals, Source, fingerprint
from udeck.i18n import error_text, tr

DESCRIPTORS = {".cue", ".gdi", ".m3u"}


def confined_path(path, root):
    """Check every component, including symlinks pointing back inside the root."""
    root = Path(root).absolute()
    path = Path(path)
    path = path if path.is_absolute() else Path.cwd() / path
    try:
        relative = path.relative_to(root)
    except ValueError:
        raise ValueError(tr("Content reference leaves its platform folder: {path}", path=path)) from None
    current = root
    for part in relative.parts:
        if part == "..":
            current = current.parent
            if current != root and root not in current.parents:
                raise ValueError(tr("Content reference leaves its platform folder: {path}", path=path))
            continue
        current = current / part
        if current.is_symlink():
            raise ValueError(tr("Content reference uses a symbolic link: {path}", path=current))
    if root.is_symlink():
        raise ValueError(tr("Content reference uses a symbolic link: {path}", path=root))
    return current


def content_dependencies(path, root, cancelled=lambda: False):
    references, referenced, visiting, visited = [], set(), set(), set()
    edges, descriptor_bytes = 0, 0

    def visit(entry, depth=0):
        nonlocal edges, descriptor_bytes
        if cancelled():
            raise OSError(tr("Scan cancelled"))
        entry = confined_path(entry, root)
        if entry in visiting or depth > 8:
            raise ValueError(tr("Circular or deeply nested disc playlist"))
        if entry in visited:
            return
        if entry.suffix.lower() not in DESCRIPTORS or not entry.is_file():
            visited.add(entry)
            return
        size = entry.stat().st_size
        descriptor_bytes += size
        if size > 2 * 1024 * 1024 or descriptor_bytes > 8 * 1024 * 1024:
            raise ValueError(tr("Disc descriptor is too large"))
        text = entry.read_text(encoding="utf-8-sig", errors="replace")
        suffix = entry.suffix.lower()
        if suffix == ".cue":
            names = [a or b for a, b in re.findall(r'^\s*FILE\s+(?:"([^"\n]+)"|(\S+))\s+', text, re.M | re.I)]
        elif suffix == ".m3u":
            names = [line.strip().strip('"') for line in text.splitlines()
                     if line.strip() and not line.lstrip().startswith("#")]
        else:
            lines = [line for line in text.splitlines() if line.strip()]
            try:
                count = int(lines[0].strip())
                names = [shlex.split(line)[4] for line in lines[1:]]
                if len(names) != count:
                    raise ValueError("Track count mismatch")
            except (IndexError, ValueError):
                raise ValueError(tr("Invalid GDI descriptor")) from None
        if not names:
            raise ValueError(tr("Disc descriptor contains no entries"))
        visiting.add(entry)
        for name in names:
            if cancelled():
                raise OSError(tr("Scan cancelled"))
            edges += 1
            if edges > 8192:
                raise ValueError(tr("Too many disc references"))
            name = name.replace("\\", "/")
            if Path(name).is_absolute() or re.match(r"^[A-Za-z]:", name):
                raise ValueError(tr("Content reference leaves its platform folder: {path}", path=name))
            target = confined_path(entry.parent / name, root)
            if target not in referenced:
                if len(references) >= 512:
                    raise ValueError(tr("Too many disc references"))
                referenced.add(target)
                references.append(target)
            visit(target, depth + 1)
        visiting.remove(entry)
        visited.add(entry)

    visit(Path(path))
    return references


@dataclass
class GameScan:
    items: list = field(default_factory=list)
    hints: list = field(default_factory=list)


def scan_games(source, catalog, cancelled=lambda: False, cache=None):
    result = GameScan()
    cache = cache or {}
    root = Path(source.path)
    if not source.available():
        raise OSError(tr("Source disconnected"))
    confined_path(root, root)
    manual = set(catalog.preferences.get("engineEntries", []))
    for directory in sorted(root.iterdir()):
        if cancelled():
            return GameScan()
        if directory.name.startswith("."):
            continue
        platform = catalog.platform_for_directory(directory.name)
        if directory.is_symlink() or not directory.is_dir() or not platform:
            if len(result.hints) < 20:
                result.hints.append(tr("Not scanned: {name}. Use a platform folder.", name=directory.name))
            continue
        candidates = catalog.candidates(platform.id)
        if not candidates:
            if len(result.hints) < 20:
                result.hints.append(tr("Enable a core for {platform}", platform=platform.title))
            continue
        files = []
        for folder, folders, names in os.walk(directory, followlinks=False):
            folders[:] = sorted(n for n in folders if not n.startswith(".") and not (Path(folder) / n).is_symlink())
            for name in sorted(names):
                if cancelled():
                    return GameScan()
                path = Path(folder) / name
                if name.startswith(".") or path.is_symlink() or not path.is_file():
                    continue
                suffix = path.suffix.lower()
                if not any(c.supports(suffix) for c in candidates):
                    continue
                if platform.mode == "scummvm" and suffix != ".scummvm":
                    continue
                if platform.mode == "dos" and suffix not in {".dosz", ".zip", ".7z", ".conf", ".dosbox"} and str(path) not in manual:
                    continue
                if platform.mode == "manual" and str(path) not in manual:
                    continue
                files.append(path)
                if len(files) >= 30000:
                    break
            if len(files) >= 30000:
                break
        referenced, dependencies, errors = set(), {}, {}
        for path in files:
            if cancelled():
                return GameScan()
            if path.suffix.lower() in DESCRIPTORS:
                try:
                    dependencies[path] = content_dependencies(path, directory, cancelled)
                    referenced.update(dependencies[path])
                except (OSError, ValueError) as error:
                    errors[path] = error_text(error)
        for path in files:
            if cancelled():
                return GameScan()
            if path in referenced:
                continue
            try:
                relative = str(path.relative_to(root))
                stat = path.stat()
                stamp = [stat.st_size, stat.st_mtime_ns]
                old = cache.get(str(path), {})
                digest = old["fingerprint"] if old.get("stamp") == stamp else fingerprint(path, cancelled)
                identifier = hashlib.sha256(f"{source.id}/{relative}/{digest}".encode()).hexdigest()
                cover = next((p for p in (path.with_suffix(".jpg"), path.with_suffix(".png"),
                             path.parent / "cover.jpg") if p.is_file() and not p.is_symlink()), None)
                result.items.append({"id": identifier, "sourceId": source.id, "path": str(path),
                    "relative": relative, "fingerprint": digest, "stamp": stamp, "metadata": {},
                    "title": path.stem, "artist": "", "album": path.parent.name, "folder": str(path.parent),
                    "format": path.suffix[1:].upper(), "platform": platform.id,
                    "platformRoot": str(directory), "dependencies": [str(p) for p in dependencies.get(path, [])],
                    "contentError": errors.get(path, ""), "cover": cover.as_uri() if cover else "", "duration": 0})
            except (OSError, ValueError):
                continue
            if len(result.items) >= 20000:
                result.hints.append(tr("Library limit reached. Use a smaller ROM root."))
                return result
    if cancelled():
        return GameScan()
    if not source.available():
        raise OSError(tr("Source disconnected"))
    result.items.sort(key=lambda i: (i["platform"], i["relative"].casefold()))
    return result


class GameScanTask(QRunnable):
    def __init__(self, generation, source, catalog, cancel, cache):
        super().__init__()
        self.generation, self.source, self.catalog = generation, source, catalog
        self.cancel, self.cache = cancel, cache
        self.signals = ScanSignals()

    def run(self):
        report = {"error": "", "hints": []}
        try:
            result = scan_games(self.source, self.catalog, self.cancel.is_set, self.cache)
            items, report["hints"] = result.items, result.hints
        except (OSError, ValueError) as error:
            items, report["error"] = [], error_text(error)
        self.signals.done.emit(self.generation, self.source.id, items, report)


class EmulatorLibrary(Library):
    def __init__(self, state, catalog, parent=None):
        super().__init__("emulator", state, parent)
        self.catalog = catalog
        self.reports = {}
        self.root_id = state.data["preferences"].get("romSourceId", "")
        self.root_path = str(Path(state.data["preferences"].get("romRoot", str(Path.home() / "Games"))).expanduser())
        if Path(self.root_path).is_dir():
            self._attach_root(self.root_path, reconnect=False)

    def _attach_root(self, path, reconnect=True):
        path = str(Path(path).expanduser().resolve(strict=True))
        existing = next((s for s in self.sources if s.path == path), None)
        source = Source.create(path, existing.id if existing else None) if reconnect or not existing else existing
        if existing:
            self.sources.remove(existing)
        self.sources.append(source)
        self.root_id, self.root_path = source.id, source.path
        prefs = self.state.data["preferences"]
        prefs.update(romRoot=source.path, romSourceId=source.id, emulatorSchema=2)
        self.state.data["sources"] = [s.to_dict() for s in self.sources]

    def configure_root(self, path):
        # Validation happens before touching preferences, source identity or scans.
        source = Source.create(path)
        with os.scandir(source.path) as entries:
            next(entries, None)
        previous = (self.root_path, self.root_id, list(self.sources),
                    copy.deepcopy(self.state.data["preferences"]), self.state.data["sources"])
        try:
            self._attach_root(source.path)
            self.state.save()
        except OSError:
            self.root_path, self.root_id, self.sources, preferences, sources = previous
            self.state.data["preferences"].clear()
            self.state.data["preferences"].update(preferences)
            self.state.data["sources"] = sources
            raise
        self.refresh()

    def refresh(self):
        self.cancel.set()
        self.cancel = threading.Event()
        self.generation += 1
        self.pending.clear()
        self.check_sources()
        self.errors.pop("rom-root", None)
        root = Path(self.root_path)
        if not root.is_dir():
            self.errors["rom-root"] = tr("ROM root does not exist: {path}", path=self.root_path)
        else:
            try:
                if not any(s.id == self.root_id and s.path == str(root.resolve()) for s in self.sources):
                    self._attach_root(root, reconnect=False)
            except OSError as error:
                self.errors["rom-root"] = error_text(error)
        cache = {i["path"]: i for i in self.items}
        catalog = copy.deepcopy(self.catalog)
        for source in self.sources:
            if not source.available():
                continue
            self.pending.add(source.id)
            task = GameScanTask(self.generation, source, catalog, self.cancel, cache)
            task.signals.done.connect(self._done)
            self.tasks.append(task)
            QThreadPool.globalInstance().start(task)
        self.changed.emit()

    def _done(self, generation, source_id, items, report):
        if generation == self.generation and source_id not in self.unavailable:
            self.reports[source_id] = report["hints"]
        super()._done(generation, source_id, items, report["error"])

    def require(self, identifier):
        item = super().require(identifier)
        source = next(s for s in self.sources if s.id == item["sourceId"])
        confined_path(item["path"], source.path)
        confined_path(item["path"], item.get("platformRoot", Path(item["path"]).parent))
        return item


def create_platform_directories(root, catalog):
    root = Path(root).expanduser()
    if root.is_symlink():
        raise ValueError(tr("Choose a folder without symbolic links"))
    root.mkdir(parents=True, exist_ok=True)
    created = []
    for platform in catalog.platforms.values():
        if not catalog.candidates(platform.id):
            continue
        path = root / platform.directory
        if path.is_symlink():
            raise ValueError(tr("Content reference uses a symbolic link: {path}", path=path))
        path.mkdir(exist_ok=True)
        created.append(str(path))
    return created
