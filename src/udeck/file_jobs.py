import os
import time
from pathlib import Path

from .files import CollisionError, available_name
from .i18n import error_text, tr


def distinct_sources(paths):
    sources = list(dict.fromkeys(str(Path(path).absolute()) for path in paths))
    result = []
    for source in sources:
        path = Path(source)
        if not any(path != Path(parent) and path.is_relative_to(Path(parent)) and not Path(parent).is_symlink()
                   for parent in sources):
            result.append(source)
    return result


class FileJob:
    def __init__(self, operations, action, sources, directory, cancelled, progress, *, policy="error", trash=None):
        self.operations, self.action = operations, action
        self.sources, self.directory = sources, directory
        self.cancelled, self.progress, self.policy, self.trash = cancelled, progress, policy, trash
        self.state = {"state": "running", "phase": "preparing", "doneBytes": 0, "totalBytes": 0,
                      "doneFiles": 0, "totalFiles": 0, "completedItems": 0, "skippedItems": 0,
                      "current": "", "speed": 0, "eta": -1}
        self.started = time.monotonic()
        self.last_update = 0

    def publish(self, force=False):
        now = time.monotonic()
        if force or now - self.last_update >= 0.1:
            elapsed = max(0.01, now - self.started)
            self.state["speed"] = self.state["doneBytes"] / elapsed
            self.state["eta"] = max(0, (self.state["totalBytes"] - self.state["doneBytes"]) / self.state["speed"]) if self.state["speed"] else -1
            self.progress(dict(self.state))
            self.last_update = now

    def update(self, update):
        self.state["doneBytes"] += update.get("bytes", 0)
        self.state["doneFiles"] += update.get("files", 0)
        self.state["current"] = update.get("path", self.state["current"])
        self.publish()

    def run(self):
        completed, skipped, errors = [], [], []
        plans = []
        try:
            self.publish(True)
            for source in self.sources:
                if self.cancelled.is_set():
                    raise InterruptedError(tr("操作已取消"))
                path = source["path"] if isinstance(source, dict) else source
                self.state["current"] = str(path)
                try:
                    measured = self.operations.measure([path], self.cancelled) if self.action in ("copy", "move") else {"bytes": 0, "files": 1}
                except InterruptedError:
                    raise
                except Exception as error:
                    errors.append({"path": str(path), "reason": error_text(error)})
                    continue
                plans.append((source, measured))
                self.state["totalBytes"] += measured["bytes"]
                self.state["totalFiles"] += measured["files"]
                self.publish()
            self.state["phase"] = "working"
            self.started = time.monotonic()
            self.publish(True)
            for source, measured in plans:
                if self.cancelled.is_set():
                    raise InterruptedError(tr("操作已取消"))
                path = Path(source["path"] if isinstance(source, dict) else source)
                self.state["current"] = str(path)
                before_bytes, before_files = self.state["doneBytes"], self.state["doneFiles"]
                try:
                    if self.action == "trash":
                        self.operations.trash(path)
                        target = str(path)
                    elif self.action == "restore":
                        target = str(self.trash.restore(source, self.directory or None))
                    else:
                        if self.policy == "skip" and os.path.lexists(Path(self.directory) / path.name):
                            skipped.append(str(path))
                            self.state["skippedItems"] += 1
                            self.state["totalBytes"] -= measured["bytes"]
                            self.state["totalFiles"] -= measured["files"]
                            continue
                        while True:
                            name = available_name(self.directory, path.name) if self.policy == "keep" else path.name
                            try:
                                target = str(self.operations.transfer(path, self.directory, move=self.action == "move",
                                             replace=self.policy == "replace", cancelled=self.cancelled,
                                             target_name=name, progress=self.update))
                                break
                            except CollisionError:
                                self.state["doneBytes"], self.state["doneFiles"] = before_bytes, before_files
                                if self.policy == "keep":
                                    continue
                                if self.policy == "skip":
                                    target = None
                                    break
                                raise
                        if target is None:
                            skipped.append(str(path))
                            self.state["skippedItems"] += 1
                            self.state["totalBytes"] -= measured["bytes"]
                            self.state["totalFiles"] -= measured["files"]
                            continue
                    self.state["doneBytes"] = before_bytes + measured["bytes"]
                    self.state["doneFiles"] = before_files + measured["files"]
                    self.state["completedItems"] += 1
                    completed.append({"source": str(path), "target": target})
                except InterruptedError:
                    raise
                except Exception as error:
                    errors.append({"path": str(path), "reason": error_text(error)})
                self.publish(True)
            self.state["state"] = "failed" if errors else "completed"
        except InterruptedError:
            self.state["state"] = "cancelled"
        except Exception as error:
            errors.append({"path": self.state["current"], "reason": error_text(error)})
            self.state["state"] = "failed"
        self.state["phase"] = "finished"
        return {**self.state, "completed": completed, "skipped": skipped, "errors": errors}
