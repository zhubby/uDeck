"""Bounded native file copies and process-shared game ownership."""

import contextlib
import fcntl
import os
import shutil
import stat
import tempfile
from pathlib import Path, PurePosixPath

MAX_FILE = 512 * 1024 * 1024
MAX_TOTAL = 2 * 1024 * 1024 * 1024


def safe_relative(name):
    if not isinstance(name, str) or "\x00" in name:
        raise ValueError("Invalid save path")
    path = PurePosixPath(name)
    if (not name or "\\" in name or path.is_absolute() or ".." in path.parts
            or any(part.startswith(".") for part in path.parts) or str(path) != name):
        raise ValueError("Invalid save path")
    return path


def regular_file(path, *, empty=False):
    path = Path(path)
    for parent in (path, *path.parents):
        if parent.is_symlink():
            raise ValueError("Symbolic links are not supported for saves")
    value = path.stat()
    if not stat.S_ISREG(value.st_mode) or value.st_size > MAX_FILE or (not empty and value.st_size == 0):
        raise ValueError("Invalid or empty native save file")
    return value


def copy_file(source, target, *, overwrite=True):
    source, target = Path(source), Path(target)
    regular_file(source, empty=True)
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    for parent in (target, *target.parents):
        if parent.is_symlink():
            raise ValueError("Symbolic links are not supported for saves")
    descriptor, temporary = tempfile.mkstemp(prefix=".save-", dir=target.parent)
    try:
        source_fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(source_fd, "rb") as incoming, os.fdopen(descriptor, "wb") as outgoing:
            size = os.fstat(incoming.fileno())
            if not stat.S_ISREG(size.st_mode) or size.st_size > MAX_FILE:
                raise ValueError("Invalid native save file")
            shutil.copyfileobj(incoming, outgoing, 1024 * 1024)
            outgoing.flush()
            os.fsync(outgoing.fileno())
        if overwrite:
            os.replace(temporary, target)
        else:
            os.link(temporary, target)
    finally:
        Path(temporary).unlink(missing_ok=True)


@contextlib.contextmanager
def lock(path, *, blocking=True):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
        except BlockingIOError:
            raise RuntimeError("A game is running or a save operation is in progress") from None
        yield
    finally:
        os.close(descriptor)


def native_tree(root):
    root = Path(root)
    if not root.exists():
        return {}
    if root.is_symlink():
        raise ValueError("Symbolic links are not supported for saves")
    files, total = {}, 0
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ValueError("Symbolic links are not supported for saves")
        if path.is_dir():
            continue
        name = path.relative_to(root).as_posix()
        safe_relative(name)
        total += regular_file(path, empty=True).st_size
        if len(files) >= 4096 or total > MAX_TOTAL:
            raise ValueError("Save directory is too large")
        files[name] = path
    return files


def recover_tree(root):
    """Recover an interrupted swap before readers create or seed a directory."""
    root = Path(root)
    previous = root.with_name("." + root.name + "-previous")
    if root.is_symlink() or previous.is_symlink():
        raise ValueError("Symbolic links are not supported for saves")
    if previous.exists():
        if not root.exists():
            os.replace(previous, root)
        else:
            shutil.rmtree(previous)


def replace_tree(root, files):
    """Stage all SRAM companions before replacing the committed generation."""
    root = Path(root)
    root.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    recover_tree(root)
    previous = root.with_name("." + root.name + "-previous")
    staging = Path(tempfile.mkdtemp(prefix=".sram-", dir=root.parent))
    try:
        for name, source in files.items():
            safe_relative(name)
            copy_file(source, staging / name)
        if root.exists():
            os.replace(root, previous)
        try:
            os.replace(staging, root)
        except OSError:
            if previous.exists():
                os.replace(previous, root)
            raise
        if previous.exists():
            shutil.rmtree(previous)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
