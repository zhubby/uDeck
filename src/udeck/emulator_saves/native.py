"""Native import/export and history restoration without a running frontend."""

import hashlib
import json
import re
import uuid
from pathlib import Path

from udeck.apps.common.state import atomic_json

from . import data_directory
from .files import copy_file, lock, native_tree, regular_file, replace_tree
from .history import History, validate_context
from .store import CoreSaveStore


def state_name(basename, slot):
    if str(slot) not in ("1", "2", "3", "auto"):
        raise ValueError("Invalid save slot")
    return basename + (".state.auto" if str(slot) == "auto" else ".state" + str(slot))


class SaveManager:
    def __init__(self, directory=None):
        self.root = data_directory(directory)
        self.history = History(self.root / "emulator-backups")
        self.registry_path = self.root / "emulator-save-registry.json"

    def store(self, context):
        context = validate_context(context)
        return CoreSaveStore(self.root / "emulator-saves" / context["gameId"], context["coreId"], context["coreHash"])

    def session(self, context):
        return lock(self.root / "emulator-save-locks" / (context["gameId"] + ".lock"), blocking=False)

    def registered(self):
        try:
            value = json.loads(self.registry_path.read_text())
            if not isinstance(value, dict):
                raise ValueError("The save registry is damaged")
            return [validate_context(c) for c in value.values()]
        except FileNotFoundError:
            return []

    def register(self, context):
        context = validate_context(context)
        with lock(self.registry_path.with_suffix(".lock")):
            entries = self.registered()
            def key(c):
                return c["gameId"], c["coreId"], c["coreHash"]
            entries = [c for c in entries if key(c) != key(context)] + [context]
            atomic_json(self.registry_path, {hashlib.sha256(repr(key(c)).encode()).hexdigest(): c for c in entries})
        return context

    def _record_state(self, context, slot, *, parents=None, generation=None, force=False):
        store = self.store(context)
        source, metadata = store.load(slot, context["contentHash"], context["coreHash"], generation=generation)
        name = state_name(context["basename"], slot)
        files = {name: source}
        thumbnail = source.parent / "thumbnail.png"
        if metadata.get("thumbnail") and thumbnail.is_file():
            files[name + ".png"] = thumbnail
        return self.history.record(context, "state", slot, files, parents=parents, force=force)

    def record_state(self, context, slot, *, generation=None):
        self.register(context)
        return self._record_state(context, str(slot), generation=generation, force=True)

    def _backup(self, context, *, force=False):
        store, entries = self.store(context), []
        for slot in store.manifest():
            if slot in ("1", "2", "3", "auto"):
                entries.append(self._record_state(context, slot, force=force))
        store.recover_sram()
        files = native_tree(store.sram_root)
        if files:
            entries.append(self.history.record(context, "sram", "", files, force=force))
        return [e for e in entries if e]

    def backup(self, context):
        self.register(context)
        with self.session(context):
            return self._backup(context, force=True)

    def backup_sram(self, context):
        self.register(context)
        with self.session(context):
            store = self.store(context)
            store.recover_sram()
            return self.history.record(context, "sram", "", native_tree(store.sram_root), force=True)

    def backup_all(self):
        result = {"backedUp": 0, "deferred": [], "errors": []}
        for context in self.registered():
            try:
                result["backedUp"] += len(self.backup(context))
            except RuntimeError:
                result["deferred"].append(context["title"])
            except (OSError, ValueError) as error:
                result["errors"].append(str(error))
        return result

    def import_native(self, context, source, *, slot="1", confirmed=False):
        if not confirmed:
            raise ValueError("Please confirm the target game, core and slot")
        context, source = self.register(context), Path(source)
        regular_file(source)
        state = re.search(r"\.state(?:\d+|\.auto)?$", source.name, re.I)
        if not state and source.suffix.lower() not in (".srm", ".rtc"):
            raise ValueError("Choose a RetroArch .state, .stateN, .state.auto, .srm or .rtc file")
        if state:
            state_name(context["basename"], slot)
        with self.session(context):
            self._backup(context)
            if state:
                metadata = {"contentHash": context["contentHash"], "coreHash": context["coreHash"],
                            "coreId": context["coreId"], "game": context["gameId"], "imported": True}
                thumbnail = Path(str(source) + ".png")
                if thumbnail.exists():
                    regular_file(thumbnail)
                self.store(context).publish(str(slot), source, metadata, thumbnail if thumbnail.exists() else None)
                return self._record_state(context, str(slot), force=True)
            sram = source.with_suffix(".srm") if source.suffix.lower() == ".rtc" else source
            regular_file(sram)
            files = {context["basename"] + ".srm": sram}
            rtc = sram.with_suffix(".rtc")
            if rtc.exists():
                regular_file(rtc)
                files[context["basename"] + ".rtc"] = rtc
            existing = native_tree(self.store(context).sram_root)
            existing.pop(context["basename"] + ".rtc", None)
            self._replace_sram(context, {**existing, **files})
            return self.history.record(context, "sram", "", native_tree(self.store(context).sram_root), force=True)

    def export_native(self, context, destination, *, slot="1", kind="state", overwrite=False):
        with self.session(context):
            store = self.store(context)
            if kind == "state":
                source, metadata = store.load(str(slot), context["contentHash"], context["coreHash"])
                files = {state_name(context["basename"], slot): source}
                if metadata.get("thumbnail"):
                    files[state_name(context["basename"], slot) + ".png"] = source.parent / "thumbnail.png"
            elif kind == "sram":
                store.recover_sram()
                files = native_tree(store.sram_root)
            else:
                raise ValueError("Invalid save type")
            if not files:
                raise ValueError("There are no saves to export")
            destination = Path(destination)
            if any(destination.resolve().is_relative_to((self.root / name).resolve()) for name in (
                    "emulator-saves", "emulator-backups", "emulator-sync-work", "emulator-sync-recovery")):
                raise ValueError("Choose an export folder outside the managed save storage")
            if not overwrite and any((destination / name).exists() for name in files):
                raise FileExistsError("A native save already exists at the destination")
            # Preserve unknown external saves as native files, without assigning
            # them a game/core identity in our history.
            if overwrite:
                backup = destination / ".retroarch-save-backups" / uuid.uuid4().hex
                for name in files:
                    target = destination / name
                    if target.exists() and target.resolve() != files[name].resolve():
                        copy_file(target, backup / name, overwrite=False)
            result = []
            for name, source in files.items():
                target = destination / name
                copy_file(source, target, overwrite=overwrite)
                result.append(target)
            return result

    def _replace_sram(self, context, files):
        replace_tree(self.store(context).sram_root, files)

    def _apply(self, context, entry):
        source_context = entry["context"]
        if any(context[k] != source_context[k] for k in ("platform", "contentHash", "coreId")):
            raise ValueError("This backup belongs to another game or core")
        directory = self.history.directory(entry["id"])
        if entry["kind"] == "state":
            if source_context["coreHash"] != context["coreHash"]:
                raise ValueError("This state requires its original core version")
            original_name = state_name(source_context["basename"], entry["slot"])
            source = directory / original_name
            regular_file(source)
            metadata = {"game": context["gameId"], "contentHash": context["contentHash"],
                        "coreId": context["coreId"], "coreHash": context["coreHash"], "coreVersion": context["coreHash"][:16]}
            thumbnail = directory / (original_name + ".png")
            self.store(context).publish(entry["slot"], source, metadata, thumbnail if thumbnail.exists() else None)
        else:
            old, new = source_context["basename"], context["basename"]
            files = {(new + name[len(old):] if name.startswith(old + ".") else name): directory / name
                     for name in entry["files"]}
            self._replace_sram(context, files)

    def restore(self, context, identifier):
        entry = self.history.read(identifier)
        with self.session(context):
            self._backup(context)
            parents = [e["id"] for e in self.history.heads(entry["resource"])]
            self._apply(context, entry)
            if entry["kind"] == "state":
                store = self.store(context)
                source, _ = store.load(entry["slot"], context["contentHash"], context["coreHash"])
                name = state_name(context["basename"], entry["slot"])
                files = {name: source}
                thumbnail = source.parent / "thumbnail.png"
                if thumbnail.exists():
                    files[name + ".png"] = thumbnail
            else:
                files = native_tree(self.store(context).sram_root)
            return self.history.record(context, entry["kind"], entry["slot"], files, parents=parents)

    def reconcile(self, context):
        result = {"applied": 0, "conflicts": [], "incompatible": [], "deferred": False}
        self.register(context)
        try:
            with self.session(context):
                # A confirmed emulator save can precede its queued history job.
                # Preserve those bytes before adopting any downloaded head.
                self._backup(context)
                entries = self.history.entries(context)
                for key in sorted({e["resource"] for e in entries}):
                    heads = self.history.heads(key)
                    if any(e["kind"] == "state" and e["context"]["coreHash"] != context["coreHash"] for e in heads):
                        result["incompatible"].extend(e["id"] for e in heads)
                        continue
                    if len({self.history.payload_signature(e) for e in heads}) > 1:
                        result["conflicts"].append({"resource": key, "versions": heads})
                        continue
                    if not heads:
                        continue
                    entry = heads[0]
                    if len(heads) == 1 and self.history.applied(key, context) == entry["id"]:
                        # A shared SRAM head can already be applied for another
                        # local path containing the same ROM; ensure this store exists.
                        if entry["kind"] != "sram" or self.store(context).sram_root.exists():
                            if entry["kind"] != "state" or entry["slot"] in self.store(context).manifest():
                                continue
                    verified = self.history.read(entry["id"])
                    self._apply(context, verified)
                    if len(heads) > 1:
                        parents = [head["id"] for head in heads]
                        if entry["kind"] == "state":
                            self._record_state(context, entry["slot"], parents=parents)
                        else:
                            self.history.record(context, "sram", "", native_tree(self.store(context).sram_root), parents=parents)
                    else:
                        self.history.mark(key, entry["id"], context)
                    result["applied"] += 1
        except RuntimeError:
            result["deferred"] = True
        return result

    def reconcile_all(self):
        return [self.reconcile(context) for context in self.registered()]
