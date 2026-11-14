"""rclone owns filesystem synchronization; uDeck owns verified progress adoption."""

import asyncio
import hashlib
import json
import os
import re
import shutil
import signal
import time
import uuid
from collections import defaultdict, deque

from udeck.apps.common.state import atomic_json

from . import data_directory
from .files import copy_file, lock
from .history import History
from .native import SaveManager

MARKER = "RCLONE_TEST"
MARKER_BYTES = b"uDeck RetroArch save history v1\n"


class RcloneError(OSError):
    def __init__(self, message, code=1):
        super().__init__(message)
        self.code = code


def clean_error(text):
    text = re.sub(r"https?://\S+", "[remote URL]", text)
    text = re.sub(r"(?i)(token|password|secret|authorization|access_key)[=: ]+\S+", r"\1=[redacted]", text)
    return text[-2000:]


class Rclone:
    def __init__(self, *, config=None, executable=None, progress=None):
        self.config = str(config) if config else None
        self.executable = executable or shutil.which("rclone")
        self.progress = progress
        self.process = None
        self.checked = False

    async def run(self, *arguments, environment=None):
        if not self.executable:
            raise RcloneError("rclone is not installed")
        command = [self.executable, "--ask-password=false", "--contimeout=10s", "--timeout=60s",
                   "--retries=2", "--low-level-retries=3", "--use-json-log", "--stats=1s"]
        if self.config:
            command.extend(("--config", self.config))
        self.process = await asyncio.create_subprocess_exec(
            *command, *map(str, arguments), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            env={**os.environ, **(environment or {})})
        process = self.process
        messages = []

        async def stderr():
            while line := await process.stderr.readline():
                try:
                    entry = json.loads(line)
                    if self.progress and isinstance(entry.get("stats"), dict):
                        self.progress(entry["stats"])
                    if entry.get("level") in ("error", "critical", "fatal"):
                        messages.append(clean_error(entry.get("msg", "rclone failed")))
                except (ValueError, TypeError):
                    messages.append(clean_error(line.decode(errors="replace")))
                del messages[:-8]

        async def stdout():
            chunks, size = [], 0
            while chunk := await process.stdout.read(65536):
                size += len(chunk)
                if size > 4 * 1024 * 1024:
                    raise RcloneError("The rclone response is too large")
                chunks.append(chunk)
            return b"".join(chunks).decode(errors="replace")

        reader = asyncio.create_task(stderr())
        output = asyncio.create_task(stdout())
        try:
            result = await output
            await reader
            code = await process.wait()
            if code:
                raise RcloneError("\n".join(messages) or f"rclone exited with code {code}", code)
            return result
        except BaseException:
            if process.returncode is None:
                try:
                    process.send_signal(signal.SIGINT)
                    try:
                        await asyncio.wait_for(process.wait(), 3)
                    except TimeoutError:
                        process.terminate()
                        try:
                            await asyncio.wait_for(process.wait(), 2)
                        except TimeoutError:
                            process.kill()
                            await process.wait()
                except ProcessLookupError:
                    pass
            for task in (reader, output):
                if not task.done():
                    task.cancel()
            await asyncio.gather(reader, output, return_exceptions=True)
            raise
        finally:
            self.process = None

    async def capabilities(self):
        if not self.checked:
            help_text = await self.run("bisync", "--help")
            if any(flag not in help_text for flag in ("--recover", "--resilient", "--backup-dir1", "--backup-dir2")):
                raise RcloneError("Upgrade rclone: recoverable bisync support is required")
            self.checked = True

    async def remotes(self):
        output = await self.run("listremotes")
        return [name[:-1] for name in output.splitlines() if name.endswith(":")]


class SyncManager:
    def __init__(self, directory=None, *, rclone_config=None):
        self.root = data_directory(directory)
        self.saves = SaveManager(self.root)
        self.config_path = self.root / "emulator-cloud.json"
        self.config = {"enabled": False, "remote": "", "directory": ""}
        try:
            saved = json.loads(self.config_path.read_text())
            if not isinstance(saved, dict):
                raise ValueError("The cloud configuration is damaged")
            self.config.update(saved)
        except FileNotFoundError:
            pass
        self.transport = Rclone(config=rclone_config, progress=self.progress)
        self.phase = "idle" if self.config["enabled"] else "disabled"
        self.error = ""
        self.last_sync = self.config.get("lastSync", 0)
        self.stats = {}
        self.conflicts = []
        self.incompatible = []
        self.job_id = 0
        self.completed_job = 0
        self.task = None
        self.pending = False
        self.lock = asyncio.Lock()
        self.configuration_lock = asyncio.Lock()
        self.generation = 0
        self.next_run = 0
        self.failures = 0

    def progress(self, value):
        self.stats = {k: value.get(k, 0) for k in ("bytes", "totalBytes", "speed", "transfers", "totalTransfers")}

    def status(self):
        return {**self.config, "phase": self.phase, "error": self.error, "lastSync": self.last_sync,
                "jobId": self.job_id, "completedJob": self.completed_job, "progress": self.stats,
                "conflicts": self.conflicts, "incompatible": self.incompatible,
                "available": bool(self.transport.executable)}

    async def remotes(self):
        return await self.transport.remotes()

    def destination(self):
        directory = self.config["directory"].rstrip("/")
        suffix = (directory + "/" if directory else "") + "uDeck/Emulator/v1"
        return self.config["remote"] + ":" + suffix

    async def configure(self, value):
        async with self.configuration_lock:
            return await self._configure(value)

    async def _configure(self, value):
        if not isinstance(value, dict):
            raise ValueError("Invalid cloud configuration")
        enabled = value.get("enabled", self.config["enabled"])
        remote = value.get("remote", self.config["remote"])
        directory = value.get("directory", self.config["directory"])
        if type(enabled) is not bool or not isinstance(remote, str) or not isinstance(directory, str):
            raise ValueError("Invalid cloud configuration")
        if (len(directory) > 2048 or any(c in directory for c in ("\x00", "\n", "\r", "\\"))
                or ".." in directory.split("/")):
            raise ValueError("Invalid remote directory")
        if enabled:
            if remote not in await self.remotes():
                raise ValueError("Choose an existing rclone remote")
            await self.transport.capabilities()
        self.generation += 1
        if self.task and not self.task.done():
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
        updated = {"enabled": enabled, "remote": remote, "directory": directory}
        atomic_json(self.config_path, updated)
        self.config = updated
        self.pending = False
        self.last_sync = 0
        self.conflicts, self.incompatible = [], []
        self.phase, self.error = ("idle" if enabled else "disabled"), ""
        self.next_run = 0
        return self.status()

    async def test_connection(self, remote, directory):
        if remote not in await self.remotes():
            raise ValueError("Choose an existing rclone remote")
        await self.transport.run("lsf", remote + ":" + directory, "--max-depth=1")
        return {"connected": True}

    async def initialize(self, destination, workdir, snapshots, *, established=False):
        marker = snapshots / MARKER
        try:
            listing = await self.transport.run("lsf", destination, "--max-depth=1")
        except RcloneError as error:
            if error.code not in (3, 4):
                raise
            listing = ""
        if MARKER not in listing.splitlines():
            if established:
                raise ValueError("The remote access marker is missing; check the remote before retrying")
            if listing.strip():
                raise ValueError("The remote directory does not contain a recognized save history")
            marker.write_bytes(MARKER_BYTES)
            os.utime(marker, ns=(1700000000000000000, 1700000000000000000))
            await self.transport.run("copyto", marker, destination + "/" + MARKER)
        else:
            probe = workdir / ("marker-" + uuid.uuid4().hex)
            try:
                await self.transport.run("copyto", destination + "/" + MARKER, probe)
                if probe.read_bytes() != MARKER_BYTES:
                    raise ValueError("The remote history has an unsupported format")
                shutil.copy2(probe, marker)
            finally:
                probe.unlink(missing_ok=True)

    def schedule(self):
        if self.config["enabled"]:
            if self.task and not self.task.done():
                self.pending = True
            else:
                self.job_id += 1
                self.phase = "syncing"
                self.task = asyncio.create_task(self.run_scheduled())
        return self.status()

    async def run_scheduled(self):
        while self.config["enabled"]:
            self.pending = False
            await self.sync(scheduled=True)
            if not self.pending or self.phase == "error":
                return
            self.job_id += 1

    async def sync(self, *, scheduled=False):
        async with self.lock:
            if not self.config["enabled"]:
                return self.status()
            if not scheduled:
                self.job_id += 1
            job, generation = self.job_id, self.generation
            self.phase, self.error, self.stats = "syncing", "", {}
            destination = self.destination()
            profile = hashlib.sha256(destination.encode()).hexdigest()[:24]
            workdir = self.root / "emulator-sync-work" / profile
            workdir.mkdir(parents=True, exist_ok=True, mode=0o700)
            snapshots = workdir / "snapshots"
            snapshots.mkdir(mode=0o700, exist_ok=True)
            baseline = workdir / "initialized.json"
            guard = lock(workdir / ".service.lock", blocking=False)
            acquired = False
            try:
                await self.transport.capabilities()
                guard.__enter__()
                acquired = True
                await asyncio.to_thread(self.stage_history, snapshots)
                await self.initialize(destination, workdir, snapshots, established=baseline.exists())
                # Only this user's service touches this workdir; never remove a
                # live rclone lock or a listing belonging to a different pair.
                for path in workdir.glob("*.lck"):
                    try:
                        data = json.loads(path.read_text())
                        pid = int(data["PID"] if "PID" in data else data["pid"])
                        os.kill(pid, 0)
                    except ProcessLookupError:
                        path.unlink()
                    except (OSError, ValueError, KeyError, TypeError):
                        raise ValueError("The rclone sync lock needs inspection") from None
                run = uuid.uuid4().hex
                recovery = self.root / "emulator-sync-recovery" / profile
                recovery.mkdir(parents=True, exist_ok=True, mode=0o700)
                remote_recovery = destination.rsplit("/", 1)[0] + "/recovery/" + self.saves.history.device_id
                # Alias backends are resolved to their long underlying names.
                # Combine keeps a short virtual root and separate recovery mount.
                def mounts(data, backup):
                    return " ".join(json.dumps(v, ensure_ascii=False) for v in ("data=" + str(data), "recovery=" + str(backup)))
                aliases = {"RCLONE_CONFIG_UDECKSAVELOCAL_TYPE": "combine",
                           "RCLONE_CONFIG_UDECKSAVELOCAL_UPSTREAMS": mounts(snapshots, recovery),
                           "RCLONE_CONFIG_UDECKSAVECLOUD_TYPE": "combine",
                           "RCLONE_CONFIG_UDECKSAVECLOUD_UPSTREAMS": mounts(destination, remote_recovery)}
                arguments = ["bisync", "udecksavelocal:", "udecksavecloud:",
                             "--workdir", workdir, "--check-access", "--resilient", "--recover",
                             "--conflict-resolve=none", "--conflict-loser=num", "--max-delete=10",
                             "--transfers=2", "--checkers=2", "--exclude=/recovery/**",
                             "--backup-dir1", "udecksavelocal:recovery/" + run,
                             "--backup-dir2", "udecksavecloud:recovery/" + run]
                if not baseline.exists():
                    arguments.append("--resync")
                await self.transport.run(*arguments, environment=aliases)
                # Validate complete generations before publishing a new baseline
                # or touching any game's working save files.
                await asyncio.to_thread(self.accept_history, snapshots)
                atomic_json(baseline, {"version": 1, "destination": destination})
                guard.__exit__(None, None, None)
                acquired = False
                if generation != self.generation:
                    return self.status()
                results = await asyncio.to_thread(self.saves.reconcile_all)
                self.conflicts = [c for result in results for c in result["conflicts"]]
                self.incompatible = [c for result in results for c in result["incompatible"]]
                self.last_sync = time.time()
                self.config["lastSync"] = self.last_sync
                atomic_json(self.config_path, self.config)
                self.phase = "conflict" if self.conflicts else "idle"
                self.failures = 0
                self.next_run = time.monotonic() + 60
            except asyncio.CancelledError:
                self.phase = "idle" if self.config["enabled"] else "disabled"
                raise
            except (OSError, ValueError, KeyError, TypeError, RuntimeError) as error:
                self.phase, self.error = "error", clean_error(str(error))
                self.failures += 1
                self.next_run = time.monotonic() + min(300, 5 * 3 ** min(self.failures - 1, 4))
            finally:
                if acquired:
                    guard.__exit__(None, None, None)
                self.completed_job = job
            return self.status()

    @staticmethod
    def copy_snapshot(source, target):
        if target.is_symlink() or target.parent.is_symlink():
            raise ValueError("Symbolic links are not supported for saves")
        if target.exists():
            if (target / "manifest.json").read_bytes() != (source / "manifest.json").read_bytes():
                raise ValueError("Two different backups have the same identity")
            return
        staging = target.with_name("." + target.name)
        if staging.exists():
            shutil.rmtree(staging)
        staging.mkdir(parents=True, mode=0o700)
        try:
            manifest = json.loads((source / "manifest.json").read_text())
            for name in manifest["files"]:
                copy_file(source / name, staging / name)
            copy_file(source / "manifest.json", staging / "manifest.json")
            os.replace(staging, target)
        finally:
            if staging.exists():
                shutil.rmtree(staging)

    def stage_history(self, snapshots):
        history = self.saves.history
        for entry in history.entries():
            target = snapshots / entry["deviceId"] / entry["id"]
            history.read(entry["id"])
            self.copy_snapshot(history.directory(entry["id"]), target)

    def accept_history(self, snapshots):
        # Use the same manifest validation for downloaded data, with all working
        # files and local application state outside this transport cache.
        entries, directories = {}, {}
        for directory in snapshots.glob("*/*"):
            if not directory.is_dir() or directory.name.startswith("."):
                continue
            entry = History.read_directory(directory)
            if entry["id"] in entries:
                raise ValueError("Two different backups have the same identity")
            entries[entry["id"]], directories[entry["id"]] = entry, directory
        # A complete history includes every causal parent and has no cycles.
        children, counts = defaultdict(list), {}
        for identifier, entry in entries.items():
            counts[identifier] = len(entry["parents"])
            for parent in entry["parents"]:
                if parent not in entries or entries[parent]["resource"] != entry["resource"]:
                    raise ValueError("The backup history is incomplete or damaged")
                children[parent].append(identifier)
        ready = deque(key for key, count in counts.items() if count == 0)
        visited = 0
        while ready:
            visited += 1
            for child in children[ready.popleft()]:
                counts[child] -= 1
                if counts[child] == 0:
                    ready.append(child)
        if visited != len(entries):
            raise ValueError("The backup history is damaged")
        for identifier, entry in entries.items():
            target = self.saves.history.snapshots / entry["deviceId"] / entry["id"]
            with lock(self.saves.history.lock_path):
                self.copy_snapshot(directories[identifier], target)

    async def close(self):
        if self.task and not self.task.done():
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
