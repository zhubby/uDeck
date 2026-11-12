"""Descriptor-relative file access; never follow a client-selected symlink."""

import contextlib
import ctypes
import errno
import os
import shutil
import stat
import sys
import threading
import uuid
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from ..file_icons import file_icon
from ..files import CollisionError, natural_key, validate_name

DIRECTORY = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
PREFIX = ".udeck-web-"


def components(path, *, root=False):
    if not isinstance(path, str) or len(path) > 4096 or "\\" in path or "\x00" in path or path.startswith("/"):
        raise ValueError("Choose a path inside the shared folder")
    if path == "" and root:
        return []
    parts = path.split("/")
    if len(parts) > 128 or any(not part or part in (".", "..") or part.startswith(PREFIX) for part in parts):
        raise ValueError("Choose a path inside the shared folder")
    return parts


def no_replace(source, target, source_fd, target_fd):
    """Use native atomic no-replace rename while keeping directory handles open."""
    library = ctypes.CDLL(None, use_errno=True)
    symbol, flag = ("renameatx_np", 4) if sys.platform == "darwin" else ("renameat2", 1)
    function = getattr(library, symbol, None)
    if function is None:
        raise OSError(errno.ENOTSUP, "Atomic no-replace rename is not available")
    function.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    if function(source_fd, os.fsencode(source), target_fd, os.fsencode(target), flag):
        error = ctypes.get_errno()
        if error in (errno.EEXIST, errno.ENOTEMPTY):
            raise CollisionError("A file with this name already exists")
        raise OSError(error, os.strerror(error))


class Upload:
    def __init__(self, directory, name, size, policy, verify):
        self.directory, self.name, self.size, self.policy = directory, name, size, policy
        self.verify = verify
        self.temporary = PREFIX + uuid.uuid4().hex
        self.fd = os.open(self.temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC,
                          0o600, dir_fd=directory)
        self.written = 0
        self.closed = False

    def write(self, data):
        if self.closed or self.written + len(data) > self.size:
            raise ValueError("Upload size does not match")
        view = memoryview(data)
        while view:
            count = os.write(self.fd, view)
            view = view[count:]
            self.written += count

    def commit(self, cancelled=None):
        if self.closed or self.written != self.size:
            raise ValueError("Upload is incomplete")
        os.fsync(self.fd)
        os.close(self.fd)
        self.fd = -1
        try:
            self.verify()
            if cancelled is not None and cancelled.is_set():
                raise ValueError("Upload cancelled")
            if self.policy == "replace":
                existing = SharedRoot.information(self.directory, self.name)
                if existing and not stat.S_ISREG(existing.st_mode):
                    raise ValueError("Only regular files can be replaced")
                os.replace(self.temporary, self.name, src_dir_fd=self.directory, dst_dir_fd=self.directory)
            else:
                while True:
                    try:
                        no_replace(self.temporary, self.name, self.directory, self.directory)
                        break
                    except CollisionError:
                        if self.policy != "keep":
                            raise
                        self.name = SharedRoot.available(self.directory, self.name)
            return self.name
        finally:
            self.abort()

    def abort(self):
        if self.closed:
            return
        self.closed = True
        if self.fd >= 0:
            os.close(self.fd)
        with contextlib.suppress(FileNotFoundError):
            os.unlink(self.temporary, dir_fd=self.directory)
        os.close(self.directory)


class SharedRoot:
    def __init__(self, root, *, trash_directory=None):
        self.path = Path(root).expanduser().resolve(strict=True)
        self.fd = os.open(self.path, DIRECTORY)
        self.trash_directory = Path(trash_directory) if trash_directory else Path(
            os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share"))) / "Trash"

    def close(self):
        if self.fd >= 0:
            os.close(self.fd)
            self.fd = -1

    def check_root(self):
        current, held = self.path.stat(), os.fstat(self.fd)
        if (current.st_dev, current.st_ino) != (held.st_dev, held.st_ino):
            raise OSError("Shared folder is no longer available")

    def check_directory(self, path, held_fd):
        with self.directory(path) as fd:
            current, held = os.fstat(fd), os.fstat(held_fd)
            if (current.st_dev, current.st_ino) != (held.st_dev, held.st_ino):
                raise OSError("Destination changed during the operation")

    @contextlib.contextmanager
    def directory(self, path="", *, parents=False):
        # A fresh open gives each reader an independent directory stream and snapshot.
        fd = os.open(".", DIRECTORY, dir_fd=self.fd)
        try:
            # Detect removal/replacement of the configured root rather than serving stale storage.
            self.check_root()
            for part in components(path, root=True):
                if parents:
                    with contextlib.suppress(FileExistsError):
                        os.mkdir(part, 0o755, dir_fd=fd)
                child = os.open(part, DIRECTORY, dir_fd=fd)
                os.close(fd)
                fd = child
            yield fd
        finally:
            os.close(fd)

    @contextlib.contextmanager
    def parent(self, path, *, parents=False):
        parts = components(path)
        with self.directory("/".join(parts[:-1]), parents=parents) as fd:
            yield fd, parts[-1]

    @staticmethod
    def information(fd, name):
        try:
            return os.stat(name, dir_fd=fd, follow_symlinks=False)
        except FileNotFoundError:
            return None

    @staticmethod
    def available(fd, name):
        suffix = Path(name).suffix
        stem = name[:-len(suffix)] if suffix else name
        candidate, number = name, 2
        while SharedRoot.information(fd, candidate):
            ending = f" ({number}){suffix}"
            shortened = os.fsencode(stem)[:max(1, 255 - len(os.fsencode(ending)))].decode("utf-8", "ignore")
            candidate, number = shortened + ending, number + 1
        return candidate

    def listing(self, path="", *, hidden=False, query="", sort="name", descending=False, offset=0, limit=200):
        with self.directory(path) as fd:
            entries = []
            for entry in os.scandir(fd):
                if entry.name.startswith(PREFIX) or not hidden and entry.name.startswith("."):
                    continue
                if query.casefold() not in entry.name.casefold():
                    continue
                try:
                    info = entry.stat(follow_symlinks=False)
                except FileNotFoundError:
                    continue
                directory = stat.S_ISDIR(info.st_mode)
                link = stat.S_ISLNK(info.st_mode)
                entries.append({"name": entry.name, "path": "/".join(filter(None, [path, entry.name])),
                                "directory": directory, "symlink": link,
                                "usable": directory or stat.S_ISREG(info.st_mode),
                                "size": info.st_size, "modified": info.st_mtime,
                                "icon": file_icon(entry.name, directory=directory) if not link else "udeck-file-link"})
            key = (lambda row: (row[sort], natural_key(row["name"]))) if sort in ("size", "modified") else lambda row: natural_key(row["name"])
            entries = sorted([row for row in entries if row["directory"]], key=key, reverse=descending) + sorted(
                [row for row in entries if not row["directory"]], key=key, reverse=descending)
            disk = os.fstatvfs(fd)
            return {"path": path, "entries": entries[offset:offset + limit], "total": len(entries),
                    "freeBytes": disk.f_bavail * disk.f_frsize, "readonly": not os.access(self.path, os.W_OK)}

    def open_file(self, path):
        with self.parent(path) as (fd, name):
            stream = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=fd)
        if not stat.S_ISREG(os.fstat(stream).st_mode):
            os.close(stream)
            raise ValueError("Choose a regular file")
        return os.fdopen(stream, "rb")

    def mkdir(self, path, *, parents=False, policy="error"):
        if policy not in ("error", "keep", "skip"):
            raise ValueError("Folders are never merged or replaced")
        with self.parent(path, parents=parents) as (fd, name):
            while True:
                try:
                    os.mkdir(name, 0o755, dir_fd=fd)
                    return "/".join([*components(path)[:-1], name])
                except FileExistsError:
                    if policy == "skip":
                        return None
                    if policy != "keep":
                        raise
                    name = self.available(fd, name)

    def rename(self, path, name):
        validate_name(name)
        components(name)
        with self.parent(path) as (fd, old):
            self.require_usable(fd, old)
            no_replace(old, name, fd, fd)

    @staticmethod
    def require_usable(fd, name):
        info = os.stat(name, dir_fd=fd, follow_symlinks=False)
        if not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)):
            raise ValueError("Links and special files are not shared")
        return info

    def begin_upload(self, path, size, policy="error", *, parents=False):
        if type(size) is not int or size < 0 or policy not in ("error", "keep", "replace", "skip"):
            raise ValueError("Invalid upload")
        with self.parent(path, parents=parents) as (fd, name):
            info = self.information(fd, name)
            if info:
                if policy in ("error", "skip"):
                    raise CollisionError("A file with this name already exists")
                if policy == "keep":
                    name = self.available(fd, name)
                elif not stat.S_ISREG(info.st_mode):
                    raise ValueError("Only regular files can be replaced")
            disk = os.fstatvfs(fd)
            if size > disk.f_bavail * disk.f_frsize:
                raise OSError("Not enough free space")
            owned = os.dup(fd)
            try:
                return Upload(owned, name, size, policy,
                              lambda: self.check_directory("/".join(components(path)[:-1]), owned))
            except BaseException:
                os.close(owned)
                raise

    def walk(self, paths, cancelled=None):
        cancelled = cancelled or threading.Event()
        for path in self.distinct(paths):
            with self.parent(path) as (fd, name):
                info = self.require_usable(fd, name)
            if cancelled.is_set():
                raise InterruptedError("Cancelled")
            yield path, info
            if stat.S_ISDIR(info.st_mode):
                with self.directory(path) as fd:
                    names = sorted(name for name in os.listdir(fd) if not name.startswith(PREFIX))
                for name in names:
                    yield from self.walk([path + "/" + name], cancelled)

    @staticmethod
    def distinct(paths):
        if not isinstance(paths, list) or not 0 < len(paths) <= 2000:
            raise ValueError("Choose between 1 and 2000 items")
        values = list(dict.fromkeys("/".join(components(path)) for path in paths))
        return [path for path in values if not any(path.startswith(other + "/") for other in values if other != path)]

    def transfer(self, path, destination, *, move=False, policy="error", cancelled=None, progress=None):
        components(destination, root=True)
        if destination == path or destination.startswith(path + "/"):
            raise ValueError("Cannot copy a folder into itself")
        cancelled = cancelled or threading.Event()
        progress = progress or (lambda _: None)
        with self.parent(path) as (source_fd, name), self.directory(destination) as target_fd:
            info = self.require_usable(source_fd, name)
            if self.information(target_fd, name):
                if policy == "skip":
                    return None
                if policy == "keep":
                    name = self.available(target_fd, name)
                elif policy != "replace" or not stat.S_ISREG(info.st_mode) or not stat.S_ISREG(self.information(target_fd, name).st_mode):
                    raise CollisionError("A file with this name already exists")
            target = "/".join(filter(None, [destination, name]))
            if target == path:
                raise ValueError("Choose another destination")
            if move:
                try:
                    if policy == "replace" and stat.S_ISREG(info.st_mode):
                        os.replace(Path(path).name, name, src_dir_fd=source_fd, dst_dir_fd=target_fd)
                    else:
                        no_replace(Path(path).name, name, source_fd, target_fd)
                    return target
                except OSError as error:
                    import errno
                    if error.errno != errno.EXDEV:
                        raise
            temporary = PREFIX + uuid.uuid4().hex
            try:
                self._copy(source_fd, Path(path).name, target_fd, temporary, cancelled, progress)
                if cancelled.is_set():
                    raise InterruptedError("Cancelled")
                self.check_directory(destination, target_fd)
                self.check_directory("/".join(components(path)[:-1]), source_fd)
                if policy == "replace" and stat.S_ISREG(info.st_mode):
                    current = self.information(target_fd, name)
                    if current and not stat.S_ISREG(current.st_mode):
                        raise ValueError("Only regular files can be replaced")
                    os.replace(temporary, name, src_dir_fd=target_fd, dst_dir_fd=target_fd)
                else:
                    no_replace(temporary, name, target_fd, target_fd)
            finally:
                self._remove(target_fd, temporary)
            if move:
                self.trash(path)
            return target

    def _copy(self, source_fd, source, target_fd, target, cancelled, progress):
        if cancelled.is_set():
            raise InterruptedError("Cancelled")
        before = self.require_usable(source_fd, source)
        if stat.S_ISDIR(before.st_mode):
            os.mkdir(target, 0o700, dir_fd=target_fd)
            with contextlib.ExitStack() as stack:
                origin = os.open(source, DIRECTORY, dir_fd=source_fd)
                stack.callback(os.close, origin)
                destination = os.open(target, DIRECTORY, dir_fd=target_fd)
                stack.callback(os.close, destination)
                current = os.fstat(origin)
                if (current.st_dev, current.st_ino) != (before.st_dev, before.st_ino):
                    raise OSError("Source changed")
                for name in os.listdir(origin):
                    if not name.startswith(PREFIX):
                        self._copy(origin, name, destination, name, cancelled, progress)
                after = os.fstat(origin)
                if (before.st_mtime_ns, before.st_ctime_ns) != (after.st_mtime_ns, after.st_ctime_ns):
                    raise OSError("Source changed during copy")
        else:
            with contextlib.ExitStack() as stack:
                origin = os.open(source, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=source_fd)
                stack.callback(os.close, origin)
                destination = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=target_fd)
                stack.callback(os.close, destination)
                current = os.fstat(origin)
                if (current.st_dev, current.st_ino) != (before.st_dev, before.st_ino) or not stat.S_ISREG(current.st_mode):
                    raise OSError("Source changed")
                while chunk := os.read(origin, 1024 * 1024):
                    if cancelled.is_set():
                        raise InterruptedError("Cancelled")
                    view = memoryview(chunk)
                    while view:
                        view = view[os.write(destination, view):]
                    progress(len(chunk))
                after = os.fstat(origin)
                if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
                    raise OSError("Source changed during copy")
                os.fchmod(destination, stat.S_IMODE(before.st_mode) & 0o777)
                os.fsync(destination)

    @staticmethod
    def _remove(fd, name):
        information = SharedRoot.information(fd, name)
        if information:
            if stat.S_ISDIR(information.st_mode):
                shutil.rmtree(name, dir_fd=fd)
            else:
                os.unlink(name, dir_fd=fd)

    def trash(self, path):
        """Freedesktop trash on the source volume, readable by the native Files app."""
        with self.parent(path) as (fd, name):
            self.require_usable(fd, name)
            root = self.trash_directory
            root.mkdir(parents=True, mode=0o700, exist_ok=True)
            if root.stat().st_dev != os.fstat(fd).st_dev:
                top = (self.path / path).parent
                source_device = os.fstat(fd).st_dev
                while top.parent != top and top.parent.stat().st_dev == source_device:
                    top = top.parent
                root = top / (".Trash-" + str(os.getuid()))
                root.mkdir(mode=0o700, exist_ok=True)
            root_fd = os.open(root, DIRECTORY)
            try:
                self._private_trash(root_fd)
                for child in ("files", "info"):
                    with contextlib.suppress(FileExistsError):
                        os.mkdir(child, 0o700, dir_fd=root_fd)
                with contextlib.ExitStack() as stack:
                    files = os.open("files", DIRECTORY, dir_fd=root_fd)
                    stack.callback(os.close, files)
                    info = os.open("info", DIRECTORY, dir_fd=root_fd)
                    stack.callback(os.close, info)
                    self._private_trash(files)
                    self._private_trash(info)
                    if os.fstat(files).st_dev != os.fstat(fd).st_dev:
                        raise OSError("The shared volume cannot use this trash; no file was deleted")
                    key = uuid.uuid4().hex
                    metadata = "[Trash Info]\nPath=" + quote(str(self.path / path), safe="/") + "\nDeletionDate=" + datetime.now().strftime("%Y-%m-%dT%H:%M:%S") + "\n"
                    out = os.open(key + ".trashinfo", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=info)
                    with os.fdopen(out, "w") as stream:
                        stream.write(metadata)
                        stream.flush()
                        os.fsync(stream.fileno())
                    try:
                        no_replace(name, key, fd, files)
                    except BaseException:
                        os.unlink(key + ".trashinfo", dir_fd=info)
                        raise
            finally:
                os.close(root_fd)

    @staticmethod
    def _private_trash(fd):
        info = os.fstat(fd)
        if info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ValueError("Unsafe trash directory; no files were changed")
