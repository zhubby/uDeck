"""Immutable native snapshots; parent links describe progress, never wall clocks."""

import hashlib
import json
import math
import os
import re
import shutil
import socket
import time
import uuid
from pathlib import Path

from udeck.apps.common.state import atomic_json

from .files import MAX_TOTAL, copy_file, lock, regular_file, safe_relative
from .store import file_hash


def validate_context(context):
    if not isinstance(context, dict):
        raise ValueError("Invalid save identity")
    value = dict(context)
    for key in ("contentHash", "coreHash"):
        if not isinstance(value.get(key), str) or not re.fullmatch(r"[0-9a-f]{64}", value[key]):
            raise ValueError("Invalid save identity")
    for key in ("gameId", "platform", "coreId"):
        pattern = r"[A-Za-z0-9_-]+" if key == "coreId" else r"[A-Za-z0-9:_-]+"
        if not isinstance(value.get(key), str) or not re.fullmatch(pattern, value[key]):
            raise ValueError("Invalid save identity")
    name = value.get("basename", "")
    if (not isinstance(name, str) or not name or name in (".", "..")
            or any(c in name for c in ("/", "\\", "\x00", "\n", "\r"))):
        raise ValueError("Invalid native save name")
    if not isinstance(value.get("title"), str) or len(value["title"]) > 4096:
        raise ValueError("Invalid save title")
    return value


def resource(context, kind, slot=""):
    value = [context["platform"], context["contentHash"], context["coreId"], kind]
    if kind == "state":
        if str(slot) not in ("1", "2", "3", "auto"):
            raise ValueError("Invalid save slot")
        value.extend((context["coreHash"], str(slot)))
    elif kind != "sram":
        raise ValueError("Invalid save type")
    return "/".join(value)


class History:
    def __init__(self, root):
        self.root = Path(root)
        self.snapshots = self.root / "snapshots"
        self.state_path = self.root / "local.json"
        self.lock_path = self.root / ".history.lock"
        self.snapshots.mkdir(parents=True, exist_ok=True, mode=0o700)
        state = self.local()
        if not state.get("deviceId"):
            with lock(self.lock_path):
                state = self.local()
                if not state.get("deviceId"):
                    state.update(deviceId=uuid.uuid4().hex, deviceName=socket.gethostname(), applied={})
                    atomic_json(self.state_path, state)
        self.device_id = state["deviceId"]
        self.device_name = state["deviceName"]

    def local(self):
        try:
            value = json.loads(self.state_path.read_text())
            if not isinstance(value, dict) or not isinstance(value.get("applied", {}), dict):
                raise ValueError("The backup index is damaged")
            return value
        except FileNotFoundError:
            return {"applied": {}}

    def directory(self, identifier):
        if not isinstance(identifier, str) or not re.fullmatch(r"[0-9a-f]{32}", identifier):
            raise ValueError("Invalid snapshot identity")
        paths = list(self.snapshots.glob("*/" + identifier))
        if len(paths) != 1 or paths[0].is_symlink() or paths[0].parent.is_symlink():
            raise ValueError("The backup is missing or damaged")
        return paths[0]

    def read(self, identifier, *, verify=True):
        return self.read_directory(self.directory(identifier), verify=verify)

    @staticmethod
    def read_directory(directory, *, verify=True):
        try:
            return History._read_directory(Path(directory), verify=verify)
        except (OSError, ValueError, TypeError, KeyError, OverflowError) as error:
            raise ValueError("The backup is missing or damaged") from error

    @staticmethod
    def _read_directory(directory, *, verify):
        identifier = directory.name
        if (directory.is_symlink() or directory.parent.is_symlink()
                or not re.fullmatch(r"[0-9a-f]{32}", identifier)):
            raise ValueError("The backup is damaged")
        manifest = directory / "manifest.json"
        if regular_file(manifest).st_size > 1024 * 1024:
            raise ValueError("The backup is damaged")
        value = json.loads(manifest.read_text())
        if not isinstance(value, dict) or value.get("version") != 1 or value.get("id") != identifier:
            raise ValueError("The backup is damaged")
        context = validate_context(value["context"])
        if value.get("deviceId") != directory.parent.name or not re.fullmatch(r"[0-9a-f]{32}", value["deviceId"]):
            raise ValueError("The backup is damaged")
        if value.get("resource") != resource(context, value["kind"], value.get("slot", "")):
            raise ValueError("The backup is damaged")
        created = value.get("created")
        if (type(created) not in (int, float) or not math.isfinite(created) or not 0 < created < 253402214400
                or not isinstance(value.get("deviceName"), str) or not 0 < len(value["deviceName"]) <= 255
                or value.get("slot") not in (("1", "2", "3", "auto") if value["kind"] == "state" else ("",))):
            raise ValueError("The backup is damaged")
        parents = value.get("parents")
        files = value.get("files")
        if (not isinstance(parents, list) or len(parents) > 256
                or any(not isinstance(p, str) or not re.fullmatch(r"[0-9a-f]{32}", p) or p == identifier for p in parents)
                or not isinstance(files, dict) or not 0 < len(files) <= 4096):
            raise ValueError("The backup is damaged")
        if len(set(parents)) != len(parents):
            raise ValueError("The backup is damaged")
        total = 0
        for name, info in files.items():
            safe_relative(name)
            if (name == "manifest.json" or not isinstance(info, dict) or type(info.get("size")) is not int
                    or info["size"] < 0 or not re.fullmatch(r"[0-9a-f]{64}", info.get("sha256", ""))):
                raise ValueError("The backup is damaged")
            total += info["size"]
            if total > MAX_TOTAL:
                raise ValueError("The backup is too large")
            if verify:
                path = directory / name
                if regular_file(path, empty=True).st_size != info["size"] or file_hash(path) != info["sha256"]:
                    raise ValueError("The backup is damaged")
        if value["kind"] == "state":
            name = context["basename"] + (".state.auto" if value["slot"] == "auto" else ".state" + value["slot"])
            if name not in files or set(files) - {name, name + ".png"} or not files[name]["size"]:
                raise ValueError("The backup is damaged")
        return value

    def entries(self, context=None):
        result = []
        for manifest in sorted(self.snapshots.glob("*/*/manifest.json")):
            if not re.fullmatch(r"[0-9a-f]{32}", manifest.parent.name):
                continue
            try:
                value = self.read_directory(manifest.parent, verify=False)
            except (OSError, ValueError, KeyError, TypeError):
                continue
            if context and any(value["context"][k] != context[k] for k in ("platform", "contentHash", "coreId")):
                continue
            result.append(value)
        return sorted(result, key=lambda e: e["created"], reverse=True)

    def heads(self, key):
        entries = [e for e in self.entries() if e["resource"] == key]
        parents = {p for e in entries for p in e["parents"]}
        return [e for e in entries if e["id"] not in parents]

    @staticmethod
    def local_key(key, context):
        return key + "#" + context["gameId"]

    def applied(self, key, context):
        return self.local()["applied"].get(self.local_key(key, context))

    def mark(self, key, identifier, context):
        with lock(self.lock_path):
            local = self.local()
            local["applied"][self.local_key(key, context)] = identifier
            atomic_json(self.state_path, local)

    def record(self, context, kind, slot, files, *, parents=None, force=False):
        context = validate_context(context)
        key = resource(context, kind, slot)
        if not files:
            return None
        with lock(self.lock_path):
            local = self.local()
            info = {}
            for name, path in files.items():
                safe_relative(name)
                info[name] = {"size": regular_file(path, empty=True).st_size, "sha256": file_hash(path)}
            local_key = self.local_key(key, context)
            previous = local["applied"].get(local_key)
            if parents is None and previous and not force:
                try:
                    old = self.read(previous)
                    if self.payload_signature(old) == self.payload_signature({"context": context, "files": info}):
                        return old
                except (OSError, ValueError, KeyError):
                    pass
            identifier = uuid.uuid4().hex
            directory = self.snapshots / self.device_id / identifier
            staging = directory.with_name("." + identifier)
            staging.mkdir(parents=True, mode=0o700)
            try:
                for name, path in files.items():
                    copy_file(path, staging / name)
                    if file_hash(staging / name) != info[name]["sha256"]:
                        raise OSError("The save changed while it was being backed up")
                value = {"version": 1, "id": identifier, "context": context, "resource": key,
                         "kind": kind, "slot": str(slot), "parents": parents if parents is not None else ([previous] if previous else []),
                         "deviceId": self.device_id, "deviceName": self.device_name,
                         "created": time.time(), "files": info}
                atomic_json(staging / "manifest.json", value)
                os.replace(staging, directory)
                local["applied"][local_key] = identifier
                atomic_json(self.state_path, local)
                return value
            finally:
                if staging.exists():
                    shutil.rmtree(staging)

    @staticmethod
    def payload_signature(entry):
        # Filenames depend on each device's ROM name. Compare the native role
        # and bytes so a renamed ROM does not produce a false progress conflict.
        basename = entry["context"]["basename"]
        roles = [(name[len(basename):] if name.startswith(basename + ".") else name, value["size"], value["sha256"])
                 for name, value in entry["files"].items()]
        return hashlib.sha256(json.dumps(sorted(roles)).encode()).hexdigest()
