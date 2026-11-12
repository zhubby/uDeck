"""Transactional Samba configuration and independent sharing lifetime."""

import asyncio
import ipaddress
import json
import os
import re
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from ..network_files import DURATIONS
from ..share_settings import configuration_transaction


@dataclass(frozen=True)
class Actor:
    uid: int
    gid: int
    name: str
    pid: int
    session: str = ""
    start_time: str = ""


def atomic_write(path, content, mode=0o600):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name("." + path.name + "-" + uuid.uuid4().hex)
    try:
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
        with os.fdopen(fd, "w") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


class SmbSettings:
    def __init__(self, path=None):
        self.path = Path(path or "/var/lib/udeck-smb/settings.json")

    def load(self):
        defaults = {"enabled": False, "root": "", "duration": 0, "networks": [],
                    "uid": None, "gid": None, "username": "", "identity": []}
        try:
            value = json.loads(self.path.read_text())
            if (not isinstance(value, dict) or type(value.get("duration")) is not int or value["duration"] not in DURATIONS
                    or not isinstance(value.get("root"), str) or not value["root"].startswith("/")
                    or any(char in value["root"] for char in "\x00\r\n:")
                    or not isinstance(value.get("networks"), list) or not 0 < len(value["networks"]) <= 32
                    or not all(isinstance(key, str) and 0 < len(key) < 512 for key in value["networks"])
                    or type(value.get("uid")) is not int or value["uid"] <= 0
                    or type(value.get("gid")) is not int or value["gid"] < 0
                    or not re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_.-]{0,63}\$?", value.get("username", ""))
                    or value.get("username") == "root" or not isinstance(value.get("identity"), list)
                    or len(value["identity"]) != 2 or any(type(number) is not int for number in value["identity"])):
                return defaults
            return {**{key: value[key] for key in defaults}, "enabled": value.get("enabled") is True and value["duration"] == 0}
        except (OSError, ValueError, TypeError):
            return defaults

    def save(self, value):
        atomic_write(self.path, json.dumps(value, sort_keys=True))


class SmbManager:
    def __init__(self, path=None, *, runtime=None, access=None):
        from .runtime import SambaRuntime, check_access
        self.settings = SmbSettings(path)
        self.value = self.settings.load()
        self.runtime = runtime or SambaRuntime()
        self.access = access or check_access
        self.addresses = set()
        self.candidates = []
        self.errors = []
        self.deadline = None
        self.owner = None
        self.lock = asyncio.Lock()

    def status(self):
        return {**{key: self.value[key] for key in ("enabled", "root", "duration", "networks")},
                "state": "running" if self.addresses else "waiting" if self.value["enabled"] else "stopped",
                "urls": [f"smb://{'[' + address + ']' if ':' in address else address}/udeck" for address in sorted(self.addresses)],
                "errors": list(self.errors), "candidates": self.candidates,
                "remaining": max(0, int(self.deadline - time.monotonic())) if self.deadline is not None else None,
                "ownerUid": self.value["uid"]}

    def _authorize_owner(self, actor):
        if actor is not None and actor.uid != 0 and self.value["uid"] not in (None, actor.uid):
            raise PermissionError("This SMB share belongs to another local user")

    @staticmethod
    def _addresses(value, candidates):
        addresses = set()
        for row in candidates:
            if row["key"] in value["networks"]:
                for raw in row["addresses"]:
                    address = ipaddress.ip_address(raw)
                    if address.is_unspecified or address.is_multicast or address.is_loopback or address.is_link_local:
                        continue
                    addresses.add(str(address))
        return addresses

    def _root_valid(self):
        try:
            stat = Path(self.value["root"]).stat()
            return Path(self.value["root"]).is_dir() and [stat.st_dev, stat.st_ino] == self.value["identity"]
        except OSError:
            return False

    async def configure(self, value, *, actor, candidates):
        async with self.lock:
            self._authorize_owner(actor)
            if actor.uid <= 0:
                raise PermissionError("Choose a non-root local user for guest file access")
            if not isinstance(value, dict):
                raise ValueError("Expected a configuration object")
            root, duration, networks = value.get("root"), value.get("duration", 0), value.get("networks")
            if (not isinstance(root, str) or not root.startswith("/") or any(char in root for char in "\x00\n\r:")
                    or type(duration) is not int or duration not in DURATIONS):
                raise ValueError("Choose an existing shared folder and a supported duration")
            if (not isinstance(networks, list) or not 0 < len(networks) <= 32
                    or not all(isinstance(key, str) and 0 < len(key) < 512 for key in networks)):
                raise ValueError("Select at least one connected network")
            if not set(networks) <= {row["key"] for row in candidates} | set(self.value["networks"]):
                raise ValueError("A selected network is no longer connected")
            root = Path(root).resolve(strict=True)
            if any(char in str(root) for char in "\x00\n\r:"):
                raise ValueError("The shared folder path contains unsupported characters")
            await self.access(root, actor)
            stat = root.stat()
            configured = {"enabled": True, "root": str(root), "duration": duration, "networks": list(dict.fromkeys(networks)),
                          "uid": actor.uid, "gid": actor.gid, "username": actor.name, "identity": [stat.st_dev, stat.st_ino]}
            wanted = self._addresses(configured, candidates)
            await self.runtime.validate(configured, wanted)
            old, deadline, owner = self.value, self.deadline, self.owner
            try:
                with configuration_transaction(self.settings, configured):
                    await self.runtime.stop()
                    self.addresses = set()
                    self.value = configured
                    self.deadline = time.monotonic() + duration if duration else None
                    self.owner = actor if duration else None
                    self.candidates = candidates
                    self.errors = []
                    if not self._root_valid():
                        raise OSError("Shared folder changed while enabling access")
                    if wanted:
                        await self.runtime.start(configured, wanted)
                        self.addresses = wanted
            except Exception as error:
                if self.value is old:
                    raise
                await self.runtime.stop()
                self.addresses = set()
                self.value, self.deadline, self.owner = old, deadline, owner
                self.errors = [str(error)]
                try:
                    await self._reconcile(candidates)
                except Exception as rollback_error:
                    await self.runtime.stop()
                    self.addresses = set()
                    self.value = {**old, "enabled": False}
                    self.errors.append("Could not restore previous SMB access: " + str(rollback_error))
                raise
            return self.status()

    async def _reconcile(self, candidates):
        self.candidates = candidates
        if not self.value["enabled"]:
            return
        if not self._root_valid():
            await self._stop("Shared folder is no longer available. Choose the folder again.")
            return
        wanted = self._addresses(self.value, candidates)
        if self.addresses and not await self.runtime.alive():
            await self._stop("Samba service exited unexpectedly. Enable sharing again to retry.")
            return
        if wanted != self.addresses:
            # Stop the entire service cgroup, including already connected clients.
            await self.runtime.stop()
            self.addresses = set()
            if wanted:
                try:
                    await self.runtime.start(self.value, wanted)
                    self.addresses = wanted
                    self.errors = []
                except (OSError, RuntimeError) as error:
                    await self._stop(str(error))

    async def tick(self, *, candidates, owner_alive=True):
        async with self.lock:
            if self.value["enabled"] and self.deadline is not None and (time.monotonic() >= self.deadline or not owner_alive):
                await self._stop()
            else:
                await self._reconcile(candidates)

    async def _stop(self, error="", *, persist=True):
        try:
            await self.runtime.stop()
        except Exception as failure:
            self.errors = [str(failure)]
            raise
        self.value = {**self.value, "enabled": False}
        self.deadline = None
        self.owner = None
        self.errors = [error] if error else []
        self.addresses = set()
        if persist:
            try:
                self.settings.save(self.value)
            except OSError as failure:
                self.errors.append(str(failure))
                raise

    async def stop(self, *, actor=None):
        async with self.lock:
            self._authorize_owner(actor)
            try:
                with configuration_transaction(self.settings, {**self.value, "enabled": False}):
                    await self._stop(persist=False)
            except Exception as failure:
                self.errors = [str(failure)]
                raise
            return self.status()

    async def close(self):
        async with self.lock:
            await self.runtime.stop()
            self.addresses = set()
