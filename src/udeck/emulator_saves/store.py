"""On-disk save groups, shared by the emulator and the headless save service."""

import hashlib
import json
import os
import re
import shutil
import time
import uuid
from pathlib import Path

from udeck.apps.common.state import atomic_json
from udeck.i18n import Msg, tr

from .files import recover_tree


def file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class SaveStore:
    def __init__(self, root):
        self.root = Path(root)
        self.sram_root = self.root / "sram"

    def prepare_sram(self):
        self.recover_sram()
        self.sram_root.mkdir(parents=True, exist_ok=True, mode=0o700)

    def recover_sram(self):
        recover_tree(self.sram_root)

    def inspect(self, slot):
        name = self.manifest().get(str(slot))
        if not isinstance(name, str) or not re.fullmatch(r"[0-9a-f]{32}", name):
            raise ValueError(tr(Msg.THIS_SAVE_SLOT_IS_EMPTY))
        value = json.loads((self.root / name / "metadata.json").read_text())
        if not isinstance(value, dict):
            raise ValueError(tr(Msg.THE_SAVE_STATE_IS_DAMAGED))
        return value

    def manifest(self):
        try:
            slots = json.loads((self.root / "slots.json").read_text())
            if not isinstance(slots, dict):
                raise ValueError(tr(Msg.THE_SAVE_INDEX_IS_DAMAGED))
            return slots
        except FileNotFoundError:
            return {}

    def publish(self, slot, state_file, metadata, thumbnail=None):
        if not Path(state_file).is_file() or Path(state_file).stat().st_size == 0:
            raise OSError(tr(Msg.THE_CORE_DID_NOT_WRITE_A_SAVE_STATE))
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        name = uuid.uuid4().hex
        staging = self.root / ("." + name)
        staging.mkdir(mode=0o700)
        try:
            target = staging / "state"
            with Path(state_file).open("rb") as source, target.open("wb") as output:
                shutil.copyfileobj(source, output)
                output.flush()
                os.fsync(output.fileno())
            data = {**metadata, "version": 1, "sha256": file_hash(target), "created": time.time(),
                    "thumbnail": bool(thumbnail and Path(thumbnail).is_file())}
            if data["thumbnail"]:
                shutil.copyfile(thumbnail, staging / "thumbnail.png")
            atomic_json(staging / "metadata.json", data)
            os.replace(staging, self.root / name)
            slots = SaveStore.manifest(self)
            slots[str(slot)] = name
            atomic_json(self.root / "slots.json", slots)
            return data
        finally:
            if staging.exists():
                shutil.rmtree(staging)

    def load(self, slot, content_hash, core_hash, *, generation=None):
        name = generation if generation is not None else self.manifest().get(str(slot))
        if not isinstance(name, str) or len(name) != 32 or any(c not in "0123456789abcdef" for c in name):
            raise ValueError(tr(Msg.THIS_SAVE_SLOT_IS_EMPTY))
        directory = self.root / name
        metadata = json.loads((directory / "metadata.json").read_text())
        if not isinstance(metadata, dict):
            raise ValueError(tr(Msg.THE_SAVE_STATE_IS_DAMAGED))
        if metadata.get("version") != 1 or metadata.get("contentHash") != content_hash or metadata.get("coreHash") != core_hash:
            raise ValueError(tr(Msg.THIS_STATE_BELONGS_TO_ANOTHER_GAME_OR_CORE_VERSION))
        path = directory / "state"
        if file_hash(path) != metadata.get("sha256"):
            raise ValueError(tr(Msg.THE_SAVE_STATE_IS_DAMAGED))
        return path, metadata


class CoreSaveStore(SaveStore):
    def __init__(self, game_root, core_id, core_hash):
        if not re.fullmatch(r"[A-Za-z0-9_-]+", core_id) or not re.fullmatch(r"[0-9a-f]{64}", core_hash):
            raise ValueError(tr(Msg.INVALID_CORE_SAVE_IDENTITY))
        self.game_root, self.core_id, self.core_hash = Path(game_root), core_id, core_hash
        super().__init__(self.game_root / "cores" / core_id / core_hash)
        self.sram_root = self.root.parent / "sram"


def latest_save(game_root, slot="auto"):
    root = Path(game_root)
    candidates = []
    for directory in root.glob("cores/*/*"):
        if directory.name == "sram":
            continue
        try:
            store = SaveStore(directory)
            metadata = store.inspect(slot)
            candidates.append((float(metadata.get("created", 0)), store, metadata))
        except (OSError, ValueError, TypeError):
            continue
    return max(candidates, key=lambda x: x[0])[1:] if candidates else (None, None)


