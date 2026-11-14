"""JSON .lpl documents, portable content references and persistent game identities."""

import copy
import hashlib
import json
import os
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from udeck.apps.common.library import Source, fingerprint
from udeck.apps.common.state import atomic_json
from udeck.i18n import Msg, error_text, tr


def signature(path):
    path = Path(path)
    if path.is_symlink():
        raise ValueError(tr(Msg.CHOOSE_A_FOLDER_WITHOUT_SYMBOLIC_LINKS))
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


@dataclass
class PlaylistDocument:
    path: Path
    data: dict
    original: str | None = None

    @classmethod
    def load(cls, path):
        path = Path(path)
        if path.is_symlink() or path.stat().st_size > 16 * 1024 * 1024:
            raise ValueError(tr(Msg.EMU_PLAYLIST_INVALID, path=path))
        raw = path.read_bytes()
        data = json.loads(raw.decode("utf-8-sig"))
        if (not isinstance(data, dict) or not isinstance(data.get("items"), list)
                or len(data["items"]) > 20000 or not str(data.get("version", "1.0")).startswith("1.")):
            raise ValueError(tr(Msg.EMU_PLAYLIST_INVALID, path=path))
        return cls(path, data, hashlib.sha256(raw).hexdigest())

    def check(self):
        if signature(self.path) != self.original:
            raise ValueError(tr(Msg.EMU_PLAYLIST_CHANGED, path=self.path))

    def save(self):
        self.check()
        atomic_json(self.path, self.data)
        self.original = signature(self.path)


@dataclass(frozen=True)
class ContentReference:
    path: Path
    member: str = ""

    @property
    def launch_path(self):
        return str(self.path) + ("#" + self.member if self.member else "")

    @property
    def basename(self):
        return PurePosixPath(self.member).stem if self.member else self.path.stem

    @property
    def suffix(self):
        return (PurePosixPath(self.member).suffix if self.member else self.path.suffix).lower()


def content_reference(value, base_directory, rom_root):
    if not isinstance(value, str) or not value or "\x00" in value:
        raise ValueError(tr(Msg.EMU_CONTENT_PATH_INVALID, path=value))
    physical, marker, member = value.partition("#")
    if not marker or Path(physical).suffix.lower() not in {".zip", ".7z"}:
        physical, member = value, ""
    member = member.replace("\\", "/")
    if member and (member.startswith("/") or ".." in PurePosixPath(member).parts
                   or re.match(r"^[A-Za-z]:", member)):
        raise ValueError(tr(Msg.EMU_CONTENT_PATH_INVALID, path=value))
    physical = physical.replace("\\", "/")
    base = str(base_directory or "").replace("\\", "/").rstrip("/")
    windows = bool(re.match(r"^[A-Za-z]:", physical))
    prefix = physical.casefold() if windows else physical
    compared_base = base.casefold() if windows else base
    if base and (prefix == compared_base or prefix.startswith(compared_base + "/")):
        physical = str(Path(rom_root) / physical[len(base):].lstrip("/"))
    elif windows:
        # A drive letter without a matching portable base cannot name a local file.
        raise ValueError(tr(Msg.EMU_CONTENT_PATH_INVALID, path=value))
    path = Path(physical).expanduser()
    if not path.is_absolute():
        path = Path(rom_root) / path
    return ContentReference(Path(os.path.abspath(path)), member)


def core_identifier(value):
    if not value or not isinstance(value, str) or value.upper() == "DETECT":
        return ""
    name = value.replace("\\", "/").rsplit("/", 1)[-1]
    return re.sub(r"_libretro\.(so|dll|dylib)$", "", name, flags=re.I)


def database_name(value):
    if not isinstance(value, str):
        return ""
    value = re.sub(r"\.lpl$", "", value, flags=re.I)
    return value if value and value not in {".", ".."} and not any(c in value for c in "/\\\x00") else ""


class ContentIdentities:
    def __init__(self, path):
        self.path = Path(path)
        self.values = {}
        if self.path.exists():
            try:
                value = json.loads(self.path.read_text(encoding="utf-8"))
                if (not isinstance(value, dict) or not isinstance(value.get("identities"), dict)
                        or any(not isinstance(k, str) or not isinstance(v, str) or not v
                               for k, v in value["identities"].items())):
                    raise ValueError()
            except (OSError, ValueError):
                raise ValueError(tr(Msg.EMU_PLAYLIST_INVALID, path=self.path)) from None
            self.values = value["identities"]

    @staticmethod
    def key(path, member=""):
        return json.dumps([os.path.abspath(path), member], ensure_ascii=False)

    def register(self, path, member, identifier):
        self.values[self.key(path, member)] = identifier

    def identifier(self, path, member=""):
        key = self.key(path, member)
        return self.values.setdefault(key, hashlib.sha256(key.encode()).hexdigest())

    def save(self):
        atomic_json(self.path, {"version": 1, "identities": self.values})


@dataclass
class PlaylistScan:
    items: list = field(default_factory=list)
    playlists: list = field(default_factory=list)
    errors: dict = field(default_factory=dict)
    sources: list = field(default_factory=list)


def _platform(catalog, database, reference, core):
    platform = catalog.platform_for_database(database)
    if not platform:
        platform = next((p for parent in reference.path.parents
                         if (p := catalog.platform_for_directory(parent.name))), None)
    if not platform and core in catalog.cores and len(catalog.cores[core].platforms) == 1:
        platform = catalog.platforms[catalog.cores[core].platforms[0]]
    return platform.id if platform else ""


def _content_item(reference, root, cache, cancelled):
    from .library import confined_path, content_dependencies

    path = reference.path
    result = {"path": str(path), "contentPath": reference.launch_path, "archiveMember": reference.member,
              "basename": reference.basename, "stamp": None, "fingerprint": "", "dependencies": [],
              "contentError": "", "platformRoot": str(root)}
    try:
        confined_path(path, root)
        if not path.is_file():
            raise OSError(tr(Msg.EMU_CONTENT_MISSING, path=path))
        stat = path.stat()
        result["stamp"] = [stat.st_size, stat.st_mtime_ns]
        old = cache.get(str(path), {})
        digest = old.get("fingerprint") if old.get("stamp") == result["stamp"] else None
        result["fingerprint"] = digest or fingerprint(path, cancelled)
        cache[str(path)] = result
        dependencies = content_dependencies(path, root, cancelled)
        result["dependencies"] = [str(p) for p in dependencies]
        missing = [p.name for p in dependencies if not p.is_file()]
        if missing:
            result["contentError"] = tr(Msg.MISSING_DISC_TRACK_NAME, name=", ".join(missing))
    except (OSError, ValueError) as error:
        if cancelled():
            raise OSError(tr(Msg.SCAN_CANCELLED)) from None
        result["contentError"] = error_text(error)
    return result


def read_library(directory, rom_root, catalog, identities, cancelled=lambda: False, cache=None):
    result = PlaylistScan()
    directory, rom_root = Path(directory), Path(rom_root)
    cache, sources = dict(cache or {}), {}
    if not directory.exists():
        return result
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError(tr(Msg.CHOOSE_A_FOLDER_WITHOUT_SYMBOLIC_LINKS))
    for path in sorted(directory.iterdir(), key=lambda p: p.name.casefold()):
        if cancelled():
            raise OSError(tr(Msg.SCAN_CANCELLED))
        if path.suffix.lower() != ".lpl" or path.name.startswith("."):
            continue
        playlist_id = "playlist:" + hashlib.sha256(str(path).encode()).hexdigest()[:24]
        playlist = {"id": playlist_id, "path": str(path), "title": path.stem, "count": 0, "error": ""}
        result.playlists.append(playlist)
        try:
            document = PlaylistDocument.load(path)
        except (OSError, ValueError) as error:
            playlist["error"] = error_text(error)
            result.errors[str(path)] = error_text(error)
            continue
        playlist["signature"] = document.original
        seen = defaultdict(int)
        for index, raw in enumerate(document.data["items"]):
            if cancelled():
                raise OSError(tr(Msg.SCAN_CANCELLED))
            try:
                if not isinstance(raw, dict):
                    raise ValueError(tr(Msg.EMU_PLAYLIST_ENTRY_INVALID, path=path, index=index + 1))
                if not isinstance(raw.get("label", ""), str):
                    raise ValueError(tr(Msg.EMU_PLAYLIST_ENTRY_INVALID, path=path, index=index + 1))
                reference = content_reference(raw.get("path"), document.data.get("base_content_directory"), rom_root)
                db = database_name(raw.get("db_name"))
                core = core_identifier(raw.get("core_path"))
                default = core_identifier(document.data.get("default_core_path"))
                platform = _platform(catalog, db or path.stem, reference, core or default)
                if not db and platform:
                    hint = path.stem if catalog.platform_for_database(path.stem) else next(
                        (p.name for p in reference.path.parents if catalog.platform_for_directory(p.name)), "")
                    db = catalog.database_for_path(platform, Path(reference.member or reference.path), hint)
                root = rom_root if reference.path.is_relative_to(rom_root) else reference.path.parent
                if reference.path.is_relative_to(rom_root):
                    relative = reference.path.relative_to(rom_root)
                    if len(relative.parts) > 1 and catalog.platform_for_directory(relative.parts[0]):
                        root = rom_root / relative.parts[0]
                source_path = rom_root if reference.path.is_relative_to(rom_root) else root
                if str(source_path) not in sources:
                    try:
                        sources[str(source_path)] = Source.create(source_path)
                    except (OSError, ValueError):
                        sources[str(source_path)] = None
                source = sources[str(source_path)]
                identifier = identities.identifier(reference.path, reference.member)
                occurrence = seen[identifier]
                seen[identifier] += 1
                entry_id = "entry:" + hashlib.sha256(f"{playlist_id}/{identifier}/{occurrence}".encode()).hexdigest()[:32]
                item = _content_item(reference, root, cache, cancelled)
                item.update(id=identifier, entryId=entry_id, playlistId=playlist_id, playlistPath=str(path),
                            entryIndex=index, playlistSignature=document.original, romRoot=str(rom_root),
                            title=raw.get("label") or reference.basename,
                            dbName=db, platform=platform, playlistCoreId=core, playlistDefaultCoreId=default,
                            sourceId=source.id if source else "missing:" + str(source_path),
                            relative=str(reference.path.relative_to(rom_root)) if reference.path.is_relative_to(rom_root)
                            else str(reference.path), format=reference.suffix[1:].upper(),
                            artist="", album=path.stem, folder=str(reference.path.parent),
                            metadata={}, duration=0, cover="")
                result.items.append(item)
                playlist["count"] += 1
            except (OSError, ValueError, TypeError) as error:
                if cancelled():
                    raise OSError(tr(Msg.SCAN_CANCELLED)) from None
                result.errors[f"{path}:{index + 1}"] = error_text(error)
        if len(result.items) > 20000:
            raise ValueError(tr(Msg.LIBRARY_LIMIT_REACHED_USE_A_SMALLER_ROM_ROOT))
    result.sources = [s for s in sources.values() if s]
    return result


@dataclass
class PlaylistProposal:
    documents: list = field(default_factory=list)
    additions: list = field(default_factory=list)
    hints: list = field(default_factory=list)

    def commit(self):
        for document in self.documents:
            document.check()
        for document in self.documents:
            document.save()


def generate_playlists(root, directory, catalog, cancelled=lambda: False, *, selected=None):
    from .library import scan_games

    root, directory = Path(root), Path(directory)
    scan = scan_games(Source.create(root), catalog, cancelled, enabled_only=False)
    proposal = PlaylistProposal(hints=scan.hints)
    documents, known = {}, {}
    for item in scan.items:
        if cancelled():
            raise OSError(tr(Msg.SCAN_CANCELLED))
        if selected is not None and item["path"] not in selected:
            continue
        relative = Path(item["relative"])
        database = catalog.database_for_path(item["platform"], Path(item["path"]), relative.parts[0])
        path = directory / (database + ".lpl")
        if path not in documents:
            document = PlaylistDocument.load(path) if path.exists() else PlaylistDocument(path, {
                "version": "1.5", "base_content_directory": str(root), "items": []})
            documents[path] = document
            known[path] = set()
            for entry in document.data["items"]:
                if isinstance(entry, dict):
                    try:
                        ref = content_reference(entry.get("path"), document.data.get("base_content_directory"), root)
                        known[path].add(ref.launch_path)
                    except ValueError:
                        pass
        if item["path"] in known[path]:
            continue
        entry = {"path": item["path"], "label": item["title"], "core_path": "DETECT",
                 "core_name": "DETECT", "crc32": "DETECT", "db_name": database + ".lpl"}
        documents[path].data["items"].append(entry)
        known[path].add(item["path"])
        proposal.additions.append({**item, "dbName": database})
    proposal.documents = [d for d in documents.values() if any(
        item["dbName"] + ".lpl" == d.path.name for item in proposal.additions)]
    return proposal


def update_entry(item, changes):
    document = PlaylistDocument.load(item["playlistPath"])
    if document.original != item.get("playlistSignature"):
        raise ValueError(tr(Msg.EMU_PLAYLIST_CHANGED, path=document.path))
    index = item["entryIndex"]
    if index >= len(document.data["items"]):
        raise ValueError(tr(Msg.EMU_PLAYLIST_CHANGED, path=document.path))
    raw = document.data["items"][index]
    reference = content_reference(raw.get("path"), document.data.get("base_content_directory"), item["romRoot"])
    if reference.launch_path != item.get("contentPath", item["path"]):
        raise ValueError(tr(Msg.EMU_PLAYLIST_CHANGED, path=document.path))
    document.data["items"][index] = {**raw, **copy.deepcopy(changes)}
    document.save()
    item["playlistSignature"] = document.original
