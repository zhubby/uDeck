"""Preflight and recoverable relocation; saves never move with ROM files."""

import base64
import copy
import errno
import hashlib
import json
import os
import shutil
import tempfile
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

from PySide6.QtCore import QBuffer, QIODevice
from PySide6.QtGui import QImage

from udeck.apps.common.library import Source, fingerprint
from udeck.apps.common.state import atomic_json
from udeck.i18n import Msg, error_text, tr

from .library import confined_path, content_dependencies, scan_games
from .playlists import ContentIdentities, PlaylistDocument, content_reference, signature
from .thumbnails import thumbnail_names


@dataclass
class MigrationPlan:
    old_root: str
    base: str
    moves: list = field(default_factory=list)
    games: list = field(default_factory=list)
    covers: list = field(default_factory=list)
    issues: list = field(default_factory=list)
    choices: dict = field(default_factory=dict)
    playlist_signatures: dict = field(default_factory=dict)
    mappings: dict = field(default_factory=dict)


def plan_migration(old_root, base, catalog, old_items, mappings=None, cancelled=lambda: False):
    old_root, base = Path(old_root).absolute(), Path(base).absolute()
    plan = MigrationPlan(str(old_root), str(base))
    confined_path(old_root, old_root)
    mappings = mappings or {}
    plan.mappings = dict(mappings)
    scan = scan_games(Source.create(old_root), catalog, cancelled, enabled_only=False)
    old = {(i["path"], i.get("archiveMember", "")): i for i in old_items}
    by_path = {}
    for key, value in old.items():
        by_path.setdefault(key[0], []).append((key, value))
    games = {}
    for item in scan.items:
        previous = by_path.get(item["path"], [])
        if previous:
            for key, value in previous:
                games[key] = {**item, **{k: value[k] for k in ("id", "title", "archiveMember", "basename") if k in value}}
        else:
            games[(item["path"], "")] = item
    for key, item in old.items():
        if Path(key[0]).is_relative_to(old_root):
            games.setdefault(key, item)
    assignments, directories = {}, {}
    for directory in sorted(old_root.iterdir()):
        if directory.name.startswith(".") or directory == base / "roms":
            continue
        platform = catalog.platform_for_directory(directory.name)
        if not platform or not directory.is_dir():
            continue
        if directory.is_symlink():
            plan.issues.append(tr(Msg.CONTENT_REFERENCE_USES_A_SYMBOLIC_LINK_PATH, path=directory))
            continue
        directories[directory] = platform
        group = [g for (path, _), g in games.items() if Path(path).is_relative_to(directory)]
        for item in group:
            path = Path(item["path"])
            try:
                item = {**item, "dependencies": [str(p) for p in content_dependencies(path, directory, cancelled)],
                        "contentError": ""}
            except (OSError, ValueError) as error:
                plan.issues.append(error_text(error))
                continue
            database = mappings.get(str(path)) or mappings.get(str(directory)) or catalog.database_for_path(
                platform.id, Path(item.get("archiveMember") or path), directory.name, strict=True)
            if not database or database not in (platform.databases or (platform.directory,)):
                plan.choices[str(directory)] = list(platform.databases or (platform.directory,))
                continue
            if item.get("contentError") or not path.is_file():
                plan.issues.append(item.get("contentError") or tr(Msg.EMU_CONTENT_MISSING, path=path))
                continue
            missing = [p for p in item.get("dependencies", []) if not Path(p).is_file()]
            if missing:
                plan.issues.extend(tr(Msg.EMU_CONTENT_MISSING, path=p) for p in missing)
                continue
            for dependency in [str(path), *item.get("dependencies", [])]:
                if dependency in assignments and assignments[dependency] != database:
                    plan.issues.append(tr(Msg.EMU_MIGRATION_MAPPING, path=dependency))
                assignments[dependency] = database
            target = base / "roms" / database / path.relative_to(directory)
            plan.games.append({**item, "target": str(target), "dbName": database})
            cover = next((p for p in (path.with_suffix(".png"), path.with_suffix(".jpg"),
                                      path.parent / "cover.jpg") if p.is_file() and not p.is_symlink()), None)
            if cover:
                name = thumbnail_names({"path": str(target), "archiveMember": item.get("archiveMember", ""),
                                        "title": item["title"]})[0]
                plan.covers.append({"source": str(cover), "target": str(
                    base / "thumbnails" / database / "Named_Boxarts" / (name + ".png"))})
    for directory, platform in directories.items():
        for folder, folders, names in os.walk(directory, followlinks=False):
            for name in list(folders):
                if (Path(folder) / name).is_symlink():
                    plan.issues.append(tr(Msg.CONTENT_REFERENCE_USES_A_SYMBOLIC_LINK_PATH, path=Path(folder) / name))
                    folders.remove(name)
            for name in sorted(names):
                if cancelled():
                    raise OSError(tr(Msg.EMU_SCAN_CANCELLED))
                source = Path(folder) / name
                if source.is_symlink() or not source.is_file():
                    plan.issues.append(tr(Msg.CONTENT_REFERENCE_USES_A_SYMBOLIC_LINK_PATH, path=source))
                    continue
                database = assignments.get(str(source))
                if not database:
                    siblings = {db for p, db in assignments.items() if Path(p).parent == source.parent
                                and Path(p).stem == source.stem}
                    database = next(iter(siblings)) if len(siblings) == 1 else (
                        mappings.get(str(directory)) or catalog.database_for_path(
                            platform.id, source, directory.name, strict=not bool(assignments)))
                if not database:
                    plan.choices[str(directory)] = list(platform.databases or (platform.directory,))
                    continue
                target = base / "roms" / database / source.relative_to(directory)
                confined_path(target, base)
                if target == source:
                    continue
                if target.exists() or target.is_symlink():
                    plan.issues.append(tr(Msg.EMU_MIGRATION_CONFLICT, path=target))
                stat = source.stat()
                plan.moves.append({"source": str(source), "target": str(target), "size": stat.st_size,
                                   "stamp": [stat.st_size, stat.st_mtime_ns], "sha256": fingerprint(source, cancelled)})
    targets = [m["target"] for m in plan.moves]
    if len(targets) != len(set(targets)):
        plan.issues.append(tr(Msg.EMU_MIGRATION_CONFLICT, path=base / "roms"))
    for database in {g["dbName"] for g in plan.games}:
        path = base / "playlists" / (database + ".lpl")
        try:
            plan.playlist_signatures[str(path)] = PlaylistDocument.load(path).original if path.exists() else None
        except (OSError, ValueError) as error:
            plan.issues.append(str(error))
    existing = base
    while not existing.exists():
        existing = existing.parent
    required = sum(m["size"] for m in plan.moves if Path(m["source"]).stat().st_dev != existing.stat().st_dev)
    if shutil.disk_usage(existing).free < required + 1024 * 1024:
        plan.issues.append(tr(Msg.EMU_MIGRATION_SPACE))
    return plan


def _atomic_bytes(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".migration-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


class MigrationTransaction:
    def __init__(self, journal, cancelled=lambda: False, progress=lambda done, total: None):
        self.path = Path(journal)
        self.cancelled, self.progress = cancelled, progress
        self.log = None

    def _save(self):
        atomic_json(self.path, self.log)

    def _load(self):
        self.log = json.loads(self.path.read_text(encoding="utf-8"))
        if (not isinstance(self.log, dict) or self.log.get("version") != 1
                or self.log.get("status") not in {"moving", "publishing", "committed", "rolled-back"}
                or not isinstance(self.log.get("publications"), list) or not isinstance(self.log.get("moves"), list)
                or not isinstance(self.log.get("plan"), dict)):
            raise ValueError(tr(Msg.EMU_PLAYLIST_INVALID, path=self.path))
        return self.log

    def _check_cancel(self):
        if self.cancelled():
            raise OSError(tr(Msg.EMU_SCAN_CANCELLED))

    def execute(self, plan, state):
        if plan.issues or plan.choices:
            raise ValueError("\n".join(map(str, plan.issues)) or tr(Msg.EMU_MIGRATION_MAPPING, path=plan.old_root))
        if self.path.exists() and self._load()["status"] not in {"committed", "rolled-back"}:
            raise ValueError(tr(Msg.EMU_MIGRATION_RECOVERY))
        state.flush()
        original = copy.deepcopy(state.data)
        self.log = {"version": 1, "status": "moving", "plan": asdict(plan),
                    "moves": [dict(m, method="pending") for m in plan.moves], "publications": []}
        self._save()
        try:
            for index, move in enumerate(self.log["moves"]):
                self._check_cancel()
                source = Path(move["source"])
                stat = source.stat()
                if source.is_symlink() or [stat.st_size, stat.st_mtime_ns] != move["stamp"]:
                    raise OSError(tr(Msg.THE_FILE_HAS_CHANGED_REFRESH_THE_LIBRARY_BEFORE_OPENING_IT))
                move["method"] = self._transfer(move)
                self._save()
                if move.get("staging"):
                    Path(move["staging"]).unlink(missing_ok=True)
                self.progress(index + 1, len(plan.moves))
            self._check_cancel()
            self.log["status"] = "publishing"
            self._save()
            self._publish_library(plan, state)
            self._check_cancel()
            self.log["status"] = "committed"
            self._save()
        except Exception:
            self.rollback()
            state.data.clear()
            state.data.update(original)
            raise
        # Cross-device sources remain intact until the new configuration commits.
        for move in self.log["moves"]:
            source = Path(move["source"])
            if move["method"] == "copy" and source.is_file() and fingerprint(source) == move["sha256"]:
                source.unlink()
        for parent in sorted({Path(m["source"]).parent for m in plan.moves}, key=lambda p: len(p.parts), reverse=True):
            while parent != Path(plan.old_root) and parent.is_relative_to(plan.old_root):
                try:
                    parent.rmdir()
                except OSError:
                    break
                parent = parent.parent
        return state.data

    def _transfer(self, move):
        source, target = Path(move["source"]), Path(move["target"])
        confined_path(source, Path(self.log["plan"]["old_root"]))
        confined_path(target, Path(self.log["plan"]["base"]))
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            # Link/unlink has rename semantics without ever replacing a racing file.
            os.link(source, target)
        except OSError as error:
            if error.errno != errno.EXDEV:
                raise
            staging = target.parent / (".udeck-migration-" + uuid.uuid4().hex)
            move["staging"] = str(staging)
            self._save()
            try:
                with source.open("rb") as stream, staging.open("xb") as output:
                    while data := stream.read(1024 * 1024):
                        self._check_cancel()
                        output.write(data)
                    output.flush()
                    os.fsync(output.fileno())
                if fingerprint(staging, self.cancelled) != move["sha256"]:
                    raise OSError("Migration checksum mismatch")
                os.link(staging, target)
            except Exception:
                staging.unlink(missing_ok=True)
                raise
            return "copy"
        if fingerprint(target, self.cancelled) != move["sha256"]:
            target.unlink()
            raise OSError("Migration source changed")
        source.unlink()
        return "move"

    def _publish(self, path, data):
        path = Path(path)
        raw = (json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode() if isinstance(data, dict) else data
        original = path.read_bytes() if path.exists() else None
        self.log["publications"].append({"path": str(path), "original":
            base64.b64encode(original).decode() if original is not None else None,
            "sha256": hashlib.sha256(raw).hexdigest()})
        self._save()
        _atomic_bytes(path, raw)

    def _publish_library(self, plan, state):
        base = Path(plan.base)
        identities = ContentIdentities(state.path.parent / "emulator-identities.json")
        documents = {}
        for game in plan.games:
            path = base / "playlists" / (game["dbName"] + ".lpl")
            if path not in documents:
                document = PlaylistDocument.load(path) if path.exists() else PlaylistDocument(path, {
                    "version": "1.5", "base_content_directory": str(base / "roms"), "items": []})
                if document.original != plan.playlist_signatures[str(path)]:
                    raise ValueError(tr(Msg.EMU_PLAYLIST_CHANGED, path=path))
                documents[path] = document
            document = documents[path]
            matching = None
            for entry in document.data["items"]:
                if not isinstance(entry, dict):
                    continue
                try:
                    ref = content_reference(entry.get("path"), document.data.get("base_content_directory"), base / "roms")
                    if str(ref.path) in {game["path"], game["target"]} and ref.member == game.get("archiveMember", ""):
                        matching = entry
                        break
                except ValueError:
                    continue
            if matching is None:
                core_id = state.data["preferences"].get("gameCores", {}).get(game["id"])
                core = state.data["preferences"].get("coreDirectory", "/usr/lib/aarch64-linux-gnu/libretro")
                matching = {"label": game["title"], "db_name": game["dbName"] + ".lpl", "crc32": "DETECT",
                            "core_path": str(Path(core) / (core_id + "_libretro.so")) if core_id else "DETECT",
                            "core_name": core_id or "DETECT"}
                document.data["items"].append(matching)
            member = game.get("archiveMember", "")
            matching["path"] = game["target"] + ("#" + member if member else "")
            identities.register(game["target"], game.get("archiveMember", ""), game["id"])
        for path, document in documents.items():
            document.check()
            self._publish(path, document.data)
        for cover in plan.covers:
            target = Path(cover["target"])
            if target.exists():
                continue
            moved = next((m["target"] for m in plan.moves if m["source"] == cover["source"]), cover["source"])
            image = QImage(str(moved))
            if not image.isNull():
                buffer = QBuffer()
                buffer.open(QIODevice.OpenModeFlag.WriteOnly)
                image.save(buffer, "PNG")
                self._publish(target, bytes(buffer.data()))
        self._publish(identities.path, {"version": 1, "identities": identities.values})
        root = base / "roms"
        root.mkdir(parents=True, exist_ok=True)
        source = Source.create(root)
        prefs = state.data["preferences"]
        prefs.update(romRoot=str(root), romSourceId=source.id, playlistDirectory=str(base / "playlists"),
                     thumbnailDirectory=str(base / "thumbnails"), emulatorSchema=3)
        moved = {m["source"]: m["target"] for m in plan.moves}
        prefs["engineEntries"] = [moved.get(p, p) for p in prefs.get("engineEntries", [])]
        state.data["sources"] = [source.to_dict()]
        state.set_index([])
        self._publish(state.index_path, {"version": 1, "items": []})
        runtime = copy.deepcopy({k: v for k, v in state.data.items() if k != "index"})
        runtime["indexFile"] = state.index_path.name
        self._publish(state.path, runtime)

    def rollback(self):
        self._load()
        for publication in reversed(self.log["publications"]):
            path = Path(publication["path"])
            if path.exists():
                if signature(path) != publication["sha256"]:
                    original = publication["original"]
                    if original is not None and path.read_bytes() == base64.b64decode(original):
                        continue
                    raise ValueError(tr(Msg.EMU_MIGRATION_CONFLICT, path=path))
                if publication["original"] is None:
                    path.unlink()
                else:
                    _atomic_bytes(path, base64.b64decode(publication["original"]))
        for move in reversed(self.log["moves"]):
            source, target = Path(move["source"]), Path(move["target"])
            staging = Path(move["staging"]) if move.get("staging") else None
            if not target.exists():
                if not source.is_file():
                    raise ValueError(tr(Msg.EMU_CONTENT_MISSING, path=source))
                if staging:
                    staging.unlink(missing_ok=True)
                continue
            if move["method"] == "pending" and source.exists():
                owned = os.path.samefile(source, target) or (staging and staging.exists() and os.path.samefile(staging, target))
                if not owned:
                    if staging:
                        staging.unlink(missing_ok=True)
                    continue
            if target.is_symlink() or fingerprint(target) != move["sha256"]:
                raise ValueError(tr(Msg.EMU_MIGRATION_CONFLICT, path=target))
            if source.exists():
                if fingerprint(source) != move["sha256"]:
                    raise ValueError(tr(Msg.EMU_MIGRATION_CONFLICT, path=source))
                target.unlink()
            else:
                source.parent.mkdir(parents=True, exist_ok=True)
                try:
                    os.link(target, source)
                except OSError as error:
                    if error.errno != errno.EXDEV:
                        raise
                    with target.open("rb") as stream, source.open("xb") as output:
                        shutil.copyfileobj(stream, output)
                    if fingerprint(source) != move["sha256"]:
                        raise OSError("Migration recovery checksum mismatch") from None
                target.unlink()
            if staging:
                staging.unlink(missing_ok=True)
        self.log["status"] = "rolled-back"
        self._save()
