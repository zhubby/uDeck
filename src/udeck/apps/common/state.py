"""Atomic local state and the music queue, independent of engine lifetimes."""

import json
import logging
import os
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path


def atomic_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(prefix="." + path.name, suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


class AppState:
    def __init__(self, app, directory=None, *, background=False):
        root = Path(directory) if directory else Path(os.environ.get(
            "XDG_DATA_HOME", str(Path.home() / ".local/share"))) / "udeck/apps"
        self.path = root / (app + ".json")
        self.index_path = root / (app + '.index.json')
        self.background = background
        self.on_error = None
        self._lock = threading.Lock()
        self._executor = None
        self._future = None
        self._pending = None
        self._writing = False
        self._last_error = None
        self._closed = False
        self._saved_index = None
        self._index_source = None
        self._index_size = -1
        self._index_revision = 0
        self._index_snapshot = None
        self._index_error = ''
        self.error = ""
        self.data = {"version": 1, "sources": [], "positions": {}, "favorites": [],
                     "recent": [], "bookmarks": {}, "preferences": {}, "focus": {},
                     "history": [], "tabs": [], "queue": [], "index": []}
        try:
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(loaded, dict) or loaded.get("version") != 1:
                raise ValueError("Unsupported state version")
            for key, default in self.data.items():
                if key in loaded and type(loaded[key]) is type(default):
                    self.data[key] = loaded[key]
            if loaded.get('indexFile') == self.index_path.name:
                try:
                    index = json.loads(self.index_path.read_text(encoding='utf-8'))
                    if not isinstance(index, dict) or index.get('version') != 1 or not isinstance(index.get('items'), list):
                        raise ValueError('Unsupported library index')
                    self.data['index'] = index['items']
                    self._index_source = self.data['index']
                    self._index_size = len(self._index_source)
                    self._index_snapshot = deepcopy(self._index_source)
                    self._saved_index = self._index_revision
                except (OSError, ValueError) as error:
                    self._index_error = str(error)
        except FileNotFoundError:
            pass
        except (ValueError, OSError) as error:
            self.error = str(error)

    def set_index(self, items):
        """Publish a scan result, including edits to existing entries, before saving."""
        self.data['index'] = items
        self._index_source = None

    def _snapshot(self, *, check_index=False):
        runtime = deepcopy({key: value for key, value in self.data.items() if key != 'index'})
        runtime['indexFile'] = self.index_path.name
        index = self.data['index']
        if check_index or index is not self._index_source or len(index) != self._index_size:
            snapshot = deepcopy(index)
            if snapshot != self._index_snapshot:
                self._index_revision += 1
                self._index_snapshot = snapshot
            # Retain the source object; object IDs can be reused after a scan.
            self._index_source, self._index_size = index, len(index)
        return runtime, self._index_revision, self._index_snapshot

    def _write(self, snapshot):
        runtime, index_key, index = snapshot
        # Preserve corrupt input for recovery before the first successful write.
        if self.error and self.path.exists():
            recovery = self.path.with_suffix(".recovery.json")
            if not recovery.exists():
                recovery.write_bytes(self.path.read_bytes())
        if self._index_error and self.index_path.exists():
            recovery = self.index_path.with_suffix('.recovery.json')
            if not recovery.exists():
                recovery.write_bytes(self.index_path.read_bytes())
        if index_key != self._saved_index:
            atomic_json(self.index_path, {'version': 1, 'items': index})
        atomic_json(self.path, runtime)
        self._saved_index = index_key
        self.error = ""
        self._index_error = ''

    def save(self):
        if self._closed:
            raise RuntimeError('Application state is already closed')
        if self.background:
            return self.save_async()
        self.flush()
        self._write(self._snapshot(check_index=True))

    def save_async(self):
        if self._closed:
            raise RuntimeError('Application state is already closed')
        snapshot = self._snapshot(check_index=not self.background)
        with self._lock:
            self._pending = snapshot
            if self._executor is None:
                self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='udeck-state')
            if not self._writing:
                self._writing = True
                self._future = self._executor.submit(self._drain)
            return self._future

    def _drain(self):
        while True:
            with self._lock:
                snapshot, self._pending = self._pending, None
                if snapshot is None:
                    self._writing = False
                    return
            try:
                self._write(snapshot)
                self._last_error = None
            except Exception as error:
                self._last_error = error
                if self.on_error:
                    try:
                        self.on_error(error)
                    except Exception:
                        logging.getLogger(__name__).exception('Could not report application state save failure')

    def flush(self):
        while self._future is not None:
            future = self._future
            future.result()
            with self._lock:
                if future is self._future and not self._writing:
                    break
        if self._last_error:
            raise self._last_error

    def close(self):
        if self._closed:
            return
        try:
            self.flush()
        finally:
            self._closed = True
            if self._executor:
                self._executor.shutdown(wait=True)

    def remember(self, identifier):
        self.data["recent"] = [identifier] + [x for x in self.data["recent"] if x != identifier][:99]


class PlayQueue:
    def __init__(self):
        self.items = []
        self.current = None
        self.cursor = -1
        self.repeat = "off"
        self.shuffle = False

    def replace(self, items, current):
        self.items = list(items)
        self.current = current
        self.cursor = self.items.index(current) if current in self.items else -1

    def append(self, items):
        self.items.extend(items)

    def remove(self, identifier):
        if identifier not in self.items:
            return
        index = self.items.index(identifier)
        self.items.pop(index)
        if index <= self.cursor:
            self.cursor -= 1

    def move(self, identifier, delta):
        if identifier not in self.items:
            return
        index = self.items.index(identifier)
        target = max(0, min(len(self.items) - 1, index + delta))
        self.items.insert(target, self.items.pop(index))
        if self.current in self.items:
            self.cursor = self.items.index(self.current)

    def advance(self, delta=1):
        if self.repeat == "one" and delta == 1 and self.current in self.items:
            return self.current
        if self.shuffle and len(self.items) > 1:
            import random

            choices = [i for i, item in enumerate(self.items) if item != self.current]
            self.cursor = random.choice(choices) if choices else 0
        else:
            self.cursor += delta
            if self.repeat == "all" and self.items:
                self.cursor %= len(self.items)
        if 0 <= self.cursor < len(self.items):
            self.current = self.items[self.cursor]
        else:
            self.current = None
        return self.current
