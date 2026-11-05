import ctypes
import errno
import os
import shutil
import stat
import subprocess
import sys
import threading
import uuid
from pathlib import Path


class InvalidName(ValueError):
    pass


class CollisionError(FileExistsError):
    pass


def rename_noreplace(source, target):
    library = ctypes.CDLL(None, use_errno=True)
    arguments = (os.fsencode(source), os.fsencode(target))
    if sys.platform == "linux" and hasattr(library, "renameat2"):
        function = library.renameat2
        function.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        result = function(-100, arguments[0], -100, arguments[1], 1)
    elif sys.platform == "darwin" and hasattr(library, "renamex_np"):
        function = library.renamex_np
        function.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
        result = function(*arguments, 4)
    else:
        raise OSError(errno.ENOTSUP, "当前文件系统不支持安全的无覆盖重命名")
    if result:
        error = ctypes.get_errno()
        if error in (errno.EEXIST, errno.ENOTEMPTY):
            raise CollisionError("同名项目已存在，未覆盖任何文件")
        raise OSError(error, os.strerror(error), str(target))


def validate_name(name):
    if not name.strip() or name in (".", "..") or "/" in name or "\x00" in name:
        raise InvalidName("名称不能为空，也不能包含路径分隔符")
    return name


class FileOperations:
    def list_directory(self, directory, show_hidden=False):
        directory = Path(directory)
        result = []
        for entry in directory.iterdir():
            if not show_hidden and entry.name.startswith("."):
                continue
            try:
                is_directory = entry.is_dir()
                information = entry.lstat()
                size = information.st_size
                subtitle = "文件夹" if is_directory else self.format_size(size)
                if entry.is_symlink():
                    subtitle += " · 链接"
                result.append({
                    "id": str(entry), "path": str(entry), "name": entry.name,
                    "directory": is_directory, "subtitle": subtitle,
                    "icon": "folder" if is_directory else "text-x-generic",
                })
            except OSError:
                result.append({"id": str(entry), "path": str(entry), "name": entry.name,
                               "directory": False, "subtitle": "不可访问", "icon": "dialog-warning"})
        return sorted(result, key=lambda entry: (not entry["directory"], entry["name"].casefold()))

    @staticmethod
    def format_size(size):
        for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
            if size < 1024:
                return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} PiB"

    def mkdir(self, directory, name):
        target = Path(directory) / validate_name(name)
        if os.path.lexists(target):
            raise CollisionError("同名项目已存在")
        target.mkdir()
        return target

    def rename(self, source, name):
        source = Path(source)
        target = source.parent / validate_name(name)
        if source == target:
            return target
        if os.path.lexists(target):
            raise CollisionError("同名项目已存在，请使用其他名称")
        rename_noreplace(source, target)
        return target

    def transfer(self, source, directory, move=False, replace=False, cancelled=None):
        source = Path(source)
        directory = Path(directory)
        target = directory / source.name
        cancelled = cancelled or threading.Event()
        if source == target or (source.is_dir() and not source.is_symlink() and directory.resolve().is_relative_to(source.resolve())):
            raise ValueError("不能复制到原位置或自己的子目录")
        if os.path.lexists(target):
            if not replace:
                raise CollisionError("目标已存在，是否覆盖同名文件？")
            if target.is_dir() and not target.is_symlink():
                raise ValueError("不能覆盖文件夹，请先重命名")
        if cancelled.is_set():
            raise InterruptedError("操作已取消")
        if move:
            try:
                if replace and not (source.is_dir() and not source.is_symlink()):
                    os.replace(source, target)
                else:
                    rename_noreplace(source, target)
                return target
            except OSError as error:
                if error.errno != errno.EXDEV:
                    raise
        staging = directory / f".udeck-transfer-{uuid.uuid4().hex}"
        versions = {}

        def version(path):
            information = path.lstat()
            return (information.st_dev, information.st_ino, information.st_mode,
                    information.st_size, information.st_mtime_ns, information.st_ctime_ns)

        def copy_entry(origin, destination):
            if cancelled.is_set():
                raise InterruptedError("操作已取消")
            versions[origin] = version(origin)
            mode = versions[origin][2]
            if stat.S_ISLNK(mode):
                destination.symlink_to(os.readlink(origin))
            elif stat.S_ISDIR(mode):
                destination.mkdir(mode=0o700)
                for child in origin.iterdir():
                    copy_entry(child, destination / child.name)
                shutil.copystat(origin, destination, follow_symlinks=False)
            elif stat.S_ISREG(mode):
                descriptor = os.open(origin, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
                with os.fdopen(descriptor, "rb") as reader:
                    information = os.fstat(reader.fileno())
                    if not stat.S_ISREG(information.st_mode) or information.st_ino != versions[origin][1]:
                        raise RuntimeError("源文件发生变化，已取消复制")
                    writer_descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                    with os.fdopen(writer_descriptor, "wb") as writer:
                        while chunk := reader.read(1024 * 1024):
                            if cancelled.is_set():
                                raise InterruptedError("操作已取消")
                            writer.write(chunk)
                shutil.copystat(origin, destination, follow_symlinks=False)
            else:
                raise ValueError("不复制设备、套接字或管道文件")

        try:
            copy_entry(source, staging)
            if cancelled.is_set():
                raise InterruptedError("操作已取消")
            if any(version(path) != original for path, original in versions.items()):
                raise RuntimeError("源项目在复制期间发生变化，源文件已保留，请重试")
            if replace and not (staging.is_dir() and not staging.is_symlink()):
                os.replace(staging, target)
            else:
                rename_noreplace(staging, target)
            if move:
                try:
                    if cancelled.is_set() or any(version(path) != original for path, original in versions.items()):
                        raise RuntimeError("源项目已改变或操作已取消")
                    self.trash(source)
                except Exception as error:
                    raise RuntimeError(f"目标已复制，但源项目仍保留；跨文件系统移动仅使用回收站，不会永久删除源文件。\n{error}") from error
            return target
        finally:
            if staging.is_dir() and not staging.is_symlink():
                shutil.rmtree(staging)
            elif os.path.lexists(staging):
                staging.unlink()

    def trash(self, path):
        self._gio("trash", path)

    def open(self, path):
        self._gio("open", path)

    def _gio(self, action, path):
        try:
            subprocess.run(["gio", action, "--", str(path)], check=True, capture_output=True,
                           text=True, errors="replace", timeout=30)
        except subprocess.CalledProcessError as error:
            reason = (error.stderr or "").strip() or f"GIO 退出状态 {error.returncode}"
            raise RuntimeError(f"系统文件服务失败：{reason}") from error
