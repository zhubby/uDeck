"""[INPUT]: 依赖固定分发目录、私有目录及 ACP 握手。
[OUTPUT]: 提供版本查询、安装、升级、回退和命令解析。
[POS]: 在后台执行用户级安装事务。
[PROTOCOL]: Update this header on change, then check AGENTS.md
"""

import fcntl
import hashlib
import json
import os
import platform
import selectors
import shutil
import signal
import subprocess
import tarfile
import tempfile
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

from PySide6.QtCore import QObject, Signal

from udeck.apps.common.state import atomic_json

from . import catalog
from .acp import INITIALIZE

_GITHUB = {"github.com", "release-assets.githubusercontent.com", "objects.githubusercontent.com"}
_LIMIT = 512 * 1024 * 1024


class InstallError(RuntimeError):
    pass


def supported_platform():
    return platform.system() == "Linux" and platform.machine() in {"aarch64", "arm64"}


def state(root, identifier):
    try:
        data = json.loads((root / f"{identifier}.json").read_text())
        if isinstance(data, dict):
            return data
    except (FileNotFoundError, ValueError):
        pass
    return {}


def _entry(root, item):
    folder = item.get("folder", "")
    if not isinstance(folder, str) or len(folder) != 32 or not all(c in "0123456789abcdef" for c in folder):
        raise InstallError("missing")
    return root / "versions" / folder


def command(root, identifier, *, login=False, item=None):
    agent = catalog.AGENTS[identifier]
    item = item if item is not None else state(root, identifier).get("active")
    if not isinstance(item, dict):
        raise InstallError("missing")
    directory = _entry(root, item)
    name, *args = agent.login if login else (agent.binary, *agent.args)
    binary_path = item.get("bin", "bin")
    if not isinstance(binary_path, str):
        raise InstallError("missing")
    binary_dir = directory / ("node_modules/.bin" if agent.npm else binary_path)
    if not binary_dir.resolve().is_relative_to(directory.resolve()) and not agent.npm:
        raise InstallError("missing")
    executable = binary_dir / name
    if not executable.is_file():
        raise InstallError("missing")
    path = [str(binary_dir)]
    if agent.npm:
        node = root / "node" / catalog.NODE_VERSION / "bin"
        if not (node / "node").is_file():
            raise InstallError("missing")
        path.insert(0, str(node))
    env = {"PATH": os.pathsep.join([*path, os.environ.get("PATH", os.defpath)])}
    if identifier == "codex":
        # 明确使用本次安装的 Codex，而非用户 PATH 里的其他版本。
        codex = binary_dir / "codex"
        if not codex.is_file():
            raise InstallError("missing")
        env["CODEX_PATH"] = str(codex)
    return [str(executable), *args], env


def installed(root, identifier):
    item = state(root, identifier).get("active")
    try:
        command(root, identifier, item=item)
    except InstallError:
        return ""
    try:
        item_version = item.get("version")
        catalog.version(item_version)
    except ValueError:
        return ""
    return item_version


class Installer(QObject):
    completed = Signal(str, str, object, str)
    progress = Signal(str, str)

    def __init__(self, root, parent=None):
        super().__init__(parent)
        self.root = root
        self.pool = ThreadPoolExecutor(max_workers=1)
        self.cancelled = threading.Event()
        self.job = None

    def start(self, action, agent):
        if self.job is not None:
            return False
        self.cancelled.clear()
        self.job = self.pool.submit(self._worker, action, agent)
        self.job.add_done_callback(lambda result: self._done(action, agent, result))
        return True

    def cancel(self):
        self.cancelled.set()

    def close(self):
        self.cancel()
        self.pool.shutdown(wait=False, cancel_futures=True)

    def _done(self, action, agent, future):
        if future.cancelled():
            return
        try:
            data, error = future.result(), ""
        except InstallError as exc:
            data, error = None, str(exc)
        except (OSError, ValueError, TypeError, KeyError, AttributeError, StopIteration,
                tarfile.TarError, subprocess.SubprocessError):
            data, error = None, "install"
        try:
            self.completed.emit(action, agent, data, error)
        except RuntimeError:
            pass  # 应用已退出。

    def _check_cancelled(self):
        if self.cancelled.is_set():
            raise InstallError("cancelled")

    def _worker(self, action, identifier):
        self._check_cancelled()
        if action == "check":
            return catalog.available(identifier)
        if action == "probe":
            argv, env = command(self.root, identifier)
            self._probe(argv, env, self.root)
            return None
        if not supported_platform():
            raise InstallError("platform")
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        with (self.root / "install.lock").open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise InstallError("busy") from exc
            for path in self.root.glob(".agent-stage-*"):
                if path.is_dir() and not path.is_symlink():
                    shutil.rmtree(path)
            self._prune()
            if action == "rollback":
                data = state(self.root, identifier)
                previous = data.get("previous")
                if not isinstance(previous, dict):
                    raise InstallError("missing")
                argv, env = command(self.root, identifier, item=previous)
                self._probe(argv, env, self.root)
                self._check_cancelled()
                atomic_json(self.root / f"{identifier}.json",
                            {"active": previous, "previous": data.get("active")})
                return previous
            return self._install(identifier)

    def _install(self, identifier):
        self.progress.emit(identifier, "download")
        distribution = catalog.available(identifier)
        existing = state(self.root, identifier)
        active_version = installed(self.root, identifier)
        if active_version and catalog.version(active_version) > catalog.version(distribution["version"]):
            return existing["active"]
        if active_version == distribution["version"]:
            if existing["active"].get("packages") == distribution.get("packages"):
                return existing["active"]
        agent = catalog.AGENTS[identifier]
        versions = self.root / "versions"
        versions.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".agent-stage-", dir=self.root) as work:
            work = self.root / os.path.basename(work)
            folder = uuid.uuid4().hex
            item = {"folder": folder, "version": distribution["version"]}
            tree = work / "agent"
            tree.mkdir()
            if agent.npm:
                self._npm(work, tree, distribution["packages"])
                item["packages"] = distribution["packages"]
            else:
                archive = work / "package.tar.gz"
                self._download(distribution["url"], distribution["sha256"], archive, _GITHUB)
                self._unpack(archive, tree)
                source = [path for path in tree.rglob(agent.binary)
                          if path.is_file() and not path.is_symlink()]
                if len(source) != 1:
                    raise InstallError("archive")
                # 保留归档内适配器和其辅助程序的相对布局。
                item["bin"] = str(source[0].parent.relative_to(tree))
            target = versions / folder
            tree.rename(target)
            try:
                self.progress.emit(identifier, "verify")
                argv, env = command(self.root, identifier, item=item)
                self._probe(argv, env, work)
                self._check_cancelled()
                atomic_json(self.root / f"{identifier}.json",
                            {"active": item, "previous": existing.get("active")})
            except Exception:
                shutil.rmtree(target)
                raise
            self._prune()
            return item

    def _prune(self):
        references = set()
        for identifier in catalog.AGENTS:
            for item in state(self.root, identifier).values():
                if isinstance(item, dict):
                    references.add(item.get("folder"))
        for path in (self.root / "versions").glob("*"):
            if path.is_dir() and not path.is_symlink() and path.name not in references:
                shutil.rmtree(path, ignore_errors=True)

    def _download(self, url, checksum, path, hosts):
        if shutil.disk_usage(path.parent).free < 64 * 1024 * 1024:
            raise InstallError("space")
        digest = hashlib.sha256()
        with catalog.open_url(url, hosts) as response, path.open("wb") as destination:
            total = 0
            while block := response.read(256 * 1024):
                self._check_cancelled()
                total += len(block)
                if total > _LIMIT:
                    raise InstallError("archive")
                digest.update(block)
                destination.write(block)
        if digest.hexdigest() != checksum:
            raise InstallError("checksum")

    def _unpack(self, archive, destination):
        with tarfile.open(archive, "r:*") as compressed:
            total = 0
            for member in compressed:
                self._check_cancelled()
                total += member.size
                if total > 3 * _LIMIT:
                    raise InstallError("archive")
                if member.isdev():
                    raise InstallError("archive")
                compressed.extract(member, destination, filter="data")

    def _npm(self, work, tree, packages):
        node = self.root / "node" / catalog.NODE_VERSION
        if not (node / "bin/node").is_file():
            archive = work / catalog.NODE_ARCHIVE
            url = f"https://nodejs.org/dist/v{catalog.NODE_VERSION}/{catalog.NODE_ARCHIVE}"
            self._download(url, catalog.NODE_SHA256, archive, {"nodejs.org"})
            self._unpack(archive, work)
            node.parent.mkdir(exist_ok=True)
            (work / catalog.NODE_ARCHIVE.removesuffix(".tar.xz")).rename(node)
        node_bin = node / "bin/node"
        npm = node / "lib/node_modules/npm/bin/npm-cli.js"
        atomic_json(tree / "package.json", {"private": True, "dependencies": packages})
        env = {**os.environ, "PATH": f"{node_bin.parent}{os.pathsep}{os.defpath}",
               "NPM_CONFIG_USERCONFIG": str(work / "npm-user.conf"),
               "NPM_CONFIG_GLOBALCONFIG": str(work / "npm-global.conf"),
               "NPM_CONFIG_CACHE": str(self.root / "npm-cache")}
        env.pop("NODE_OPTIONS", None)
        with subprocess.Popen([str(node_bin), str(npm), "install", "--ignore-scripts", "--no-audit",
                               "--no-fund", "--registry", catalog.NPM],
                              cwd=tree, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL, start_new_session=True) as process:
            try:
                self._wait(process)
            finally:
                self._terminate(process)

    def _wait(self, process):
        deadline = time.monotonic() + 900
        while process.poll() is None:
            if self.cancelled.wait(0.15):
                self._check_cancelled()
            if time.monotonic() >= deadline:
                raise InstallError("timeout")
        if process.returncode:
            raise InstallError("package")

    @staticmethod
    def _terminate(process):
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass

    def _probe(self, argv, override, workspace):
        with tempfile.TemporaryDirectory(prefix="probe-", dir=workspace) as private:
            env = {name: value for name, value in os.environ.items()
                   if name in {"PATH", "LANG", "LC_ALL", "TZ"}}
            env.update(override, HOME=private, XDG_CONFIG_HOME=private,
                       XDG_DATA_HOME=private, XDG_CACHE_HOME=private, XDG_STATE_HOME=private)
            with subprocess.Popen(argv, cwd=private, env=env, stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                  start_new_session=True) as process, selectors.DefaultSelector() as selector:
                try:
                    request = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": INITIALIZE}
                    process.stdin.write(json.dumps(request).encode() + b"\n")
                    process.stdin.flush()
                    selector.register(process.stdout, selectors.EVENT_READ)
                    deadline = time.monotonic() + 25
                    buffer = bytearray()
                    while time.monotonic() < deadline:
                        self._check_cancelled()
                        if not selector.select(timeout=0.15):
                            continue
                        chunk = os.read(process.stdout.fileno(), 65536)
                        buffer.extend(chunk)
                        while b"\n" in buffer:
                            frame, _, buffer = buffer.partition(b"\n")
                            message = json.loads(frame)
                            if message.get("id") == 1:
                                result = message.get("result")
                                if isinstance(result, dict) and result.get("protocolVersion") == 1:
                                    return
                                raise InstallError("protocol")
                        if not chunk or len(buffer) > 8 * 1024 * 1024:
                            break
                    raise InstallError("protocol")
                finally:
                    self._terminate(process)
