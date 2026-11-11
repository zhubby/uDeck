import configparser
import errno
import os
import stat
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote_to_bytes

from .file_locations import mounted_locations
from .files import FileOperations, available_name, file_kind, rename_noreplace
from .i18n import Msg, tr


def private_directory(path):
    try:
        information = path.lstat()
        return stat.S_ISDIR(information.st_mode) and information.st_uid == os.getuid() and not information.st_mode & 0o077
    except OSError:
        return False


def trash_roots():
    home = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share"))) / "Trash"
    roots = [{"path": str(home), "top": str(Path.home()), "home": True}]
    for mount in mounted_locations():
        top = Path(mount["path"])
        roots.append({"path": str(top / (".Trash-" + str(os.getuid()))), "top": str(top), "home": False})
        shared = top / ".Trash"
        try:
            information = shared.lstat()
            if stat.S_ISDIR(information.st_mode) and information.st_mode & stat.S_ISVTX:
                roots.append({"path": str(shared / str(os.getuid())), "top": str(top), "home": False})
        except OSError:
            pass
    return roots


def identity(path):
    information = path.lstat()
    return (information.st_dev, information.st_ino, information.st_mode,
            information.st_size, information.st_mtime_ns, information.st_ctime_ns)


class TrashStore:
    def __init__(self, roots=None):
        self.roots = roots

    def _roots(self):
        return self.roots if self.roots is not None else trash_roots()

    def _entry(self, root, name):
        directory = Path(root["path"])
        if not all(private_directory(path) for path in (directory, directory / "files", directory / "info")):
            raise ValueError(tr(Msg.UNSAFE_TRASH_DIRECTORY_NO_FILES_WERE_CHANGED))
        if Path(name).name != name or name in ("", ".", ".."):
            raise ValueError(tr(Msg.INVALID_TRASH_ENTRY))
        metadata = directory / "info" / (name + ".trashinfo")
        descriptor = os.open(metadata, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, "rb") as reader:
            information = os.fstat(reader.fileno())
            if not stat.S_ISREG(information.st_mode) or information.st_uid != os.getuid() or information.st_size > 65536:
                raise ValueError(tr(Msg.INVALID_TRASH_METADATA))
            text = reader.read(65537).decode("utf-8")
        parser = configparser.ConfigParser(interpolation=None, strict=True)
        parser.read_string(text)
        section = parser["Trash Info"]
        value = os.fsdecode(unquote_to_bytes(section["Path"]))
        original = Path(value)
        if "\x00" in value or ".." in original.parts:
            raise ValueError(tr(Msg.INVALID_ORIGINAL_TRASH_PATH))
        if root["home"]:
            if not original.is_absolute():
                raise ValueError(tr(Msg.INVALID_ORIGINAL_TRASH_PATH))
        else:
            top = Path(root["top"]).resolve()
            original = original if original.is_absolute() else top / original
            if not original.resolve().is_relative_to(top):
                raise ValueError(tr(Msg.INVALID_ORIGINAL_TRASH_PATH))
        if original.resolve().is_relative_to(directory.resolve()) or original.name in ("", ".", ".."):
            raise ValueError(tr(Msg.INVALID_ORIGINAL_TRASH_PATH))
        source = directory / "files" / name
        information = source.lstat()
        kind, mime, icon = file_kind(original.name, stat.S_ISDIR(information.st_mode))
        return {"id": str(source), "path": str(source), "name": original.name,
                "directory": stat.S_ISDIR(information.st_mode), "kind": kind, "mime": mime, "icon": icon,
                "size": information.st_size, "sizeLabel": FileOperations.format_size(information.st_size),
                "modified": information.st_mtime_ns,
                "modifiedLabel": datetime.fromtimestamp(information.st_mtime).strftime("%Y-%m-%d %H:%M"),
                "subtitle": str(original), "originalPath": str(original), "deletedAt": section.get("DeletionDate", ""),
                "trash": True, "trashRoot": root, "trashName": name,
                "trashIdentity": identity(source), "metadataIdentity": identity(metadata)}

    def entries(self):
        entries = []
        for root in self._roots():
            directory = Path(root["path"])
            if not private_directory(directory):
                continue
            try:
                for metadata in (directory / "info").iterdir():
                    if metadata.name.endswith(".trashinfo"):
                        try:
                            entries.append(self._entry(root, metadata.name[:-10]))
                        except (OSError, ValueError, KeyError, UnicodeError, configparser.Error):
                            continue
            except OSError:
                continue
        return sorted(entries, key=lambda entry: entry["deletedAt"], reverse=True)

    def restore(self, entry, directory=None):
        root = next((root for root in self._roots() if root == entry.get("trashRoot")), None)
        if root is None:
            raise ValueError(tr(Msg.TRASH_LOCATION_IS_NO_LONGER_AVAILABLE))
        current = self._entry(root, entry["trashName"])
        if any(current[key] != entry.get(key) for key in ("originalPath", "trashIdentity", "metadataIdentity")):
            raise ValueError(tr(Msg.TRASH_ENTRY_CHANGED_REFRESH_BEFORE_RESTORING))
        original = Path(current["originalPath"])
        parent = Path(directory) if directory is not None else original.parent
        if not parent.is_dir():
            raise ValueError(tr(Msg.ORIGINAL_FOLDER_IS_UNAVAILABLE_CHOOSE_RESTORE_TO_FOLDER_INSTEAD))
        source = Path(current["path"])
        while True:
            target = parent / available_name(parent, original.name)
            try:
                rename_noreplace(source, target)
                break
            except FileExistsError:
                continue
            except OSError as error:
                if error.errno == errno.EXDEV:
                    raise ValueError(tr(Msg.RESTORE_NEEDS_A_FOLDER_ON_THE_SAME_FILE_SYSTEM_THE_TRASH_ENTRY_IS_UNCHANGED)) from error
                raise
        (Path(root["path"]) / "info" / (entry["trashName"] + ".trashinfo")).unlink()
        return target
