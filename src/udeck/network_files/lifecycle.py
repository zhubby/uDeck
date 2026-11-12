"""Listener reconciliation and persistent-versus-session share lifetime."""

import asyncio
import json
import os
import time
import uuid
from pathlib import Path

from aiohttp import web

from . import DURATIONS, PORT
from .networks import discover
from .server import STATE, create_app


class ShareSettings:
    def __init__(self, path=None):
        self.path = Path(path) if path else Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "udeck/network-files.json"

    def load(self):
        defaults = {"enabled": False, "duration": 0, "root": str(Path.home()), "networks": []}
        try:
            value = json.loads(self.path.read_text())
            if not isinstance(value, dict):
                return defaults
            root, networks, duration = value.get("root"), value.get("networks"), value.get("duration", 0)
            if (not isinstance(root, str) or not root.startswith("/") or "\x00" in root
                    or type(duration) is not int or duration not in DURATIONS
                    or not isinstance(networks, list) or len(networks) > 32
                    or not all(isinstance(key, str) and 0 < len(key) < 512 for key in networks)):
                return defaults
            defaults.update(root=root, networks=list(dict.fromkeys(networks)), duration=duration,
                            enabled=value.get("enabled") is True and duration == 0 and bool(networks))
        except (OSError, ValueError):
            pass
        return defaults

    def save(self, value):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(".network-files-" + uuid.uuid4().hex)
        try:
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w") as stream:
                json.dump({key: value[key] for key in ("enabled", "duration", "root", "networks")}, stream)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        finally:
            temporary.unlink(missing_ok=True)


class ShareManager:
    def __init__(self, path=None, *, port=PORT):
        self.settings = ShareSettings(path)
        self.value = self.settings.load()
        self.port = port
        self.runner = None
        self.listeners = {}
        self.errors = []
        self.candidates = []
        self.owner = ""
        self.deadline = None
        self.lock = asyncio.Lock()

    def status(self):
        enabled = self.value["enabled"]
        return {**self.value, "state": "running" if self.listeners else "waiting" if enabled else "stopped",
                "urls": [row["url"] for row in self.listeners.values()], "errors": self.errors,
                "remaining": max(0, int(self.deadline - time.monotonic())) if self.deadline is not None else None,
                "candidates": self.candidates}

    async def configure(self, value, *, candidates=None):
        if not isinstance(value, dict):
            raise ValueError("Expected a configuration object")
        root = Path(value.get("root", "")).expanduser()
        duration, networks = value.get("duration", 0), value.get("networks", [])
        if not root.is_absolute() or not root.is_dir() or type(duration) is not int or duration not in DURATIONS:
            raise ValueError("Choose an existing shared folder and a supported duration")
        if not isinstance(networks, list) or not 0 < len(networks) <= 32 or not all(isinstance(key, str) and len(key) < 512 for key in networks):
            raise ValueError("Select at least one connected network")
        if duration and (not isinstance(value.get("owner"), str) or not value["owner"]):
            raise ValueError("Temporary access needs an active uDeck session")
        candidates = candidates if candidates is not None else await discover()
        if not set(networks).issubset({row["key"] for row in candidates} | set(self.value["networks"])):
            raise ValueError("A selected network is no longer connected")
        async with self.lock:
            configured = {"enabled": True, "root": str(root.resolve()), "duration": duration, "networks": list(dict.fromkeys(networks))}
            self.settings.save(configured)
            await self._close()
            self.value = configured
            self.owner = value.get("owner", "")
            self.deadline = time.monotonic() + duration if duration else None
            await self._reconcile(candidates)
        return self.status()

    async def reconcile(self, candidates):
        async with self.lock:
            await self._reconcile(candidates)

    async def _reconcile(self, candidates):
        self.candidates = candidates
        if not self.value["enabled"]:
            return
        self.errors = []
        if self.runner:
            try:
                self.runner.app[STATE].fs.check_root()
            except OSError:
                self.value["enabled"] = False
                self.deadline = None
                try:
                    self.settings.save(self.value)
                finally:
                    await self._close()
                self.errors = ["Shared folder is no longer available. Choose the folder again to resume access."]
                return
        wanted = {address for row in candidates if row["key"] in self.value["networks"] for address in row["addresses"]}
        if set(self.listeners) - wanted:
            # Stop accepted keep-alive connections too; stopping accept() alone is insufficient.
            await self._close()
        if self.runner is None:
            try:
                self.runner = web.AppRunner(create_app(self.value["root"]), shutdown_timeout=3, handler_cancellation=False)
                await self.runner.setup()
            except (OSError, ValueError) as error:
                self.errors = [str(error)]
                self.runner = None
                return
        for address in wanted - set(self.listeners):
            try:
                site = web.TCPSite(self.runner, address, self.port, reuse_address=True)
                await site.start()
                port = site._server.sockets[0].getsockname()[1]
                host = f"[{address}]" if ":" in address else address
                self.listeners[address] = {"site": site, "url": f"http://{host}:{port}"}
            except OSError as error:
                self.errors.append(f"{address}: {error}")

    async def tick(self, *, candidates, owner_alive=True):
        if self.value["enabled"] and self.deadline is not None and (time.monotonic() >= self.deadline or not owner_alive):
            await self.stop()
        else:
            await self.reconcile(candidates)

    async def stop(self):
        async with self.lock:
            self.value["enabled"] = False
            self.deadline = None
            self.errors = []
            try:
                self.settings.save(self.value)
            finally:
                await self._close()
        return self.status()

    async def _close(self):
        self.listeners.clear()
        if self.runner:
            await self.runner.cleanup()
            self.runner = None

    async def close(self):
        async with self.lock:
            await self._close()
