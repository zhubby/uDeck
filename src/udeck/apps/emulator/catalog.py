"""Installed libretro catalogue and the single shared platform/selection policy."""

import hashlib
import json
import platform as host_platform
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from udeck.i18n import tr

LEGACY_PLATFORMS = {"GB": "gb", "GBA": "gba", "NES": "nes", "SNES": "snes", "PS1": "psx"}
ARCHIVES = {".zip", ".7z"}
DISCS = {".cue", ".gdi", ".chd", ".iso", ".ccd", ".toc", ".pbp", ".m3u"}


def message_lines(values, separator="\n"):
    result = ""
    for value in values:
        result = result + separator + value if result else value
    return result


def normal_id(value):
    return re.sub(r"[^a-z0-9]+", "-", str(value or "").lower()).strip("-")[:100]


def core_directories(preferences):
    if preferences.get("coreDirectory"):
        return [Path(preferences["coreDirectory"]).expanduser()]
    return [Path(p) for p in ("/usr/lib/aarch64-linux-gnu/libretro", "/usr/lib/x86_64-linux-gnu/libretro",
                             "/usr/lib/arm-linux-gnueabihf/libretro", "/usr/lib/libretro",
                             "/usr/local/lib/libretro", str(Path.home() / ".config/retroarch/cores"))]


def read_info(path):
    values = {}
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            match = re.match(r'^\s*([\w]+)\s*=\s*(?:"(.*)"|([^#]*))\s*$', line)
            if match:
                values[match[1]] = (match[2] if match[2] is not None else match[3]).strip()
    except OSError:
        pass
    return values


def probe_key(path):
    stat = Path(path).stat()
    return hashlib.sha256(f"4:{Path(path).resolve()}:{stat.st_size}:{stat.st_mtime_ns}:"
                          f"{host_platform.machine()}:{host_platform.release()}".encode()).hexdigest()


def probe_core(path, timeout=45):
    try:
        with tempfile.TemporaryDirectory(prefix="udeck-core-probe-") as temporary:
            result = subprocess.run([sys.executable, str(Path(__file__).with_name("probe.py")), str(path)],
                                    cwd=temporary, capture_output=True, timeout=timeout, text=True)
        if result.returncode:
            return {"status": "incompatible", "reason": f"Core probe exited {result.returncode}: "
                    + (result.stderr or result.stdout)[-900:]}
        value = json.loads(result.stdout.strip().splitlines()[-1])
        if not isinstance(value, dict) or value.get("status") not in ("available", "incompatible"):
            raise ValueError("Invalid core probe response")
        return value
    except (OSError, ValueError, IndexError, subprocess.TimeoutExpired) as error:
        return {"status": "incompatible", "reason": str(error)[:1200]}


@dataclass
class Platform:
    id: str
    title: str
    directory: str = ""
    aliases: tuple = ()
    cores: tuple = ()
    mode: str = "files"
    firmware_groups: dict = field(default_factory=dict)

    def __post_init__(self):
        self.directory = self.directory or self.id


@dataclass
class Core:
    id: str
    path: str
    name: str
    extensions: tuple
    platforms: tuple = ()
    version: str = ""
    savestate: bool = True
    no_content: bool = False
    firmware: tuple = ()
    status: str = "unverified"
    reason: str = ""
    signature: str = ""
    core_hash: str = ""
    block_extract: bool = False
    library_name: str = ""

    def supports(self, suffix):
        suffix = "." + suffix.lower().lstrip(".")
        return (suffix in self.extensions
                or (suffix in ARCHIVES and bool(self.extensions) and not self.block_extract)
                or (suffix == ".m3u" and bool(set(self.extensions) & DISCS)))


class CoreCatalog:
    def __init__(self, preferences):
        self.preferences = preferences
        self.cores = {}
        data = json.loads((Path(__file__).parent / "resources/platforms.json").read_text())
        self.system_ids = data.get("systemIds", {})
        self.firmware_groups = data.get("firmwareGroups", {})
        self.platforms = {p["id"]: Platform(p["id"], p["title"], aliases=tuple(p.get("aliases", [])),
                                          cores=tuple(p["cores"]), mode=p.get("mode", "files"),
                                          firmware_groups=p.get("firmwareGroups", {})) for p in data["platforms"]}
        self.errors = []

    @classmethod
    def discover(cls, preferences, info_directories=None):
        catalog = cls(preferences)
        directories = core_directories(preferences)
        info_directories = ([Path(p) for p in info_directories] if info_directories is not None else
                            [*(p for d in directories for p in (d, d / "info", d.parent / "info")),
                             Path("/usr/share/libretro/info"), Path("/usr/share/retroarch/info"),
                             Path.home() / ".config/retroarch/info"])
        for directory in directories:
            if not directory.is_dir():
                continue
            try:
                paths = sorted(directory.glob("*_libretro.so"))
                for path in paths:
                    identifier = path.name.removesuffix("_libretro.so")
                    if identifier in catalog.cores or not path.is_file():
                        continue
                    info_path = next((d / (identifier + "_libretro.info") for d in info_directories
                                      if (d / (identifier + "_libretro.info")).is_file()), Path("/nonexistent"))
                    values = read_info(info_path)
                    platforms = tuple(p.id for p in catalog.platforms.values() if identifier in p.cores)
                    if not platforms:
                        system_id = normal_id(values.get("systemid"))
                        platform_id = catalog.system_ids.get(system_id, system_id) or normal_id(identifier)
                        if platform_id in ("multi", "multisystem", "multi-system", "various"):
                            platform_id = normal_id(identifier)
                        if platform_id not in catalog.platforms:
                            category = values.get("categories", "").lower()
                            mode = "manual" if "engine" in category or category == "game" else "files"
                            catalog.platforms[platform_id] = Platform(platform_id,
                                values.get("systemname") or values.get("display_name") or identifier,
                                cores=(identifier,), mode=mode)
                        platforms = (platform_id,)
                    firmware = []
                    try:
                        count = min(512, max(0, int(values.get("firmware_count", 0))))
                    except ValueError:
                        count = 0
                    for index in range(count):
                        name = values.get(f"firmware{index}_path", "")
                        if name:
                            firmware.append({"path": name, "description": values.get(f"firmware{index}_desc", name),
                                             "optional": values.get(f"firmware{index}_opt", "false") == "true"})
                    catalog.cores[identifier] = Core(identifier, str(path.resolve()),
                        values.get("display_name") or values.get("corename") or identifier,
                        tuple("." + x.lower().lstrip(".") for x in values.get("supported_extensions", "").split("|") if x),
                        platforms=platforms, version=values.get("display_version", ""),
                        savestate=values.get("savestate", "true").lower() != "false",
                        no_content=values.get("supports_no_game", "false").lower() == "true",
                        firmware=tuple(firmware), signature=probe_key(path))
            except OSError as error:
                catalog.errors.append(str(error))
        return catalog

    def apply_probe(self, identifier, result):
        core = self.cores.get(identifier)
        if not core:
            return
        core.status = result["status"]
        core.reason = result.get("reason", "")
        core.version = result.get("version") or core.version
        core.library_name = result.get("name", "")
        core.core_hash = result.get("coreHash", "")
        core.block_extract = result.get("blockExtract", False)
        if not core.extensions and result.get("extensions"):
            core.extensions = tuple("." + x.lower().lstrip(".") for x in result["extensions"].split("|") if x)

    def canonical(self, platform):
        return LEGACY_PLATFORMS.get(platform, platform)

    def platform_for_directory(self, name):
        name = name.casefold()
        return next((p for p in self.platforms.values() if name in (p.directory, *p.aliases)), None)

    def platform_cores(self, platform):
        platform = self.canonical(platform)
        value = self.platforms.get(platform)
        order = value.cores if value else ()
        return sorted((c for c in self.cores.values() if platform in c.platforms),
                      key=lambda c: (order.index(c.id) if c.id in order else len(order), c.id))

    def recommended(self, platform):
        return next((c for c in self.platform_cores(platform) if c.status != "incompatible"), None)

    def enabled(self, core, platform=None):
        chosen = self.preferences.get("coreEnabled", {}).get(core.id)
        return chosen if isinstance(chosen, bool) else (self.recommended(self.canonical(platform)) is core
            if platform else any(self.recommended(p) is core for p in core.platforms))

    def candidates(self, platform, suffix=None, enabled_only=True):
        return [c for c in self.platform_cores(platform) if c.status != "incompatible"
                and (not enabled_only or self.enabled(c, platform)) and (not suffix or c.supports(suffix))]

    def resolve(self, item, require_available=True):
        platform = self.canonical(item["platform"])
        suffix = Path(item.get("path", "")).suffix or item.get("format", "")
        explicit = item.get("coreId") or self.preferences.get("gameCores", {}).get(item.get("id"))
        if explicit:
            core = self.cores.get(explicit)
            if (not core or platform not in core.platforms or not self.enabled(core, platform)
                    or core.status == "incompatible" or (require_available and core.status != "available")
                    or (not item.get("noContent") and not core.supports(suffix))):
                raise ValueError(tr("Selected core is unavailable: {core}", core=explicit))
            return core
        candidates = self.candidates(platform, suffix)
        default = self.preferences.get("platformCores", {}).get(platform)
        core = next((c for c in candidates if c.id == default), next(iter(candidates), None))
        if not core:
            raise ValueError(tr("No enabled core supports this game: {platform}", platform=platform))
        if require_available and core.status != "available":
            raise ValueError(tr("Core validation is still running: {core}", core=core.id))
        return core

    def firmware_check(self, core, platform, system):
        system = Path(system)
        value = self.platforms.get(self.canonical(platform))
        groups = self.firmware_groups.get(core.id, value.firmware_groups.get(core.id, []) if value else [])
        alternatives = [group["alternatives"] if isinstance(group, dict) else [[n] for n in group] for group in groups]
        grouped = {name for group in alternatives for option in group for name in option}
        def present(name):
            path = system / name
            return path.is_file() or (not path.suffix and path.is_dir() and any(path.iterdir()))
        required = [" / ".join(" + ".join(option) for option in group) for group in alternatives
                    if not any(all(present(n) for n in option) for option in group)]
        optional = []
        for firmware in core.firmware:
            name = firmware["path"]
            # Metadata is data, not a path capability outside the firmware folder.
            path = Path(name)
            if path.is_absolute() or ".." in path.parts:
                required.append(name)
            elif name not in grouped and not present(name):
                (optional if firmware["optional"] else required).append(name)
        return {"required": required, "optional": optional}
