import os
import re
import subprocess
from pathlib import Path

from .files import FileOperations
from .i18n import Msg, tr


def mount_path(value):
    return re.sub(r"\\([0-7]{3})", lambda match: chr(int(match[1], 8)), value)


def mounted_locations(text=None):
    if text is None:
        try:
            text = Path("/proc/self/mountinfo").read_text(errors="replace")
        except OSError:
            return []
    locations = []
    for line in text.splitlines():
        before, separator, after = line.partition(" - ")
        fields, filesystem = before.split(), after.split()
        if not separator or len(fields) < 6 or len(filesystem) < 2:
            continue
        directory = Path(mount_path(fields[4]))
        if not directory.is_absolute() or not any(directory != base and directory.is_relative_to(base)
                for base in (Path("/media"), Path("/run/media"), Path("/mnt"))):
            continue
        try:
            information = os.statvfs(directory)
            available, capacity = information.f_bavail * information.f_frsize, information.f_blocks * information.f_frsize
        except OSError:
            available, capacity = 0, 0
        locations.append({"id": "mount:" + fields[0], "mountId": fields[0], "path": str(directory),
                          "name": directory.name, "icon": "drive-removable-media", "device": mount_path(filesystem[1]),
                          "readonly": "ro" in fields[5].split(","), "available": available, "capacity": capacity,
                          "details": tr(Msg.READ_ONLY) if "ro" in fields[5].split(",") else tr(Msg.SIZE_FREE, size=FileOperations.format_size(available)) if capacity else "",
                          "mount": True})
    return locations


def user_locations(home=None, configuration=None):
    home = Path(home) if home is not None else Path.home()
    configuration = Path(configuration) if configuration is not None else Path(
        os.environ.get("XDG_CONFIG_HOME", str(home / ".config"))) / "user-dirs.dirs"
    try:
        text = configuration.read_text()
    except (OSError, UnicodeError):
        text = ""
    result = [{"id": "home", "path": str(home), "name": tr(Msg.HOME_FOLDER), "icon": "user-home"}]
    definitions = (("DOWNLOAD", "Downloads", tr(Msg.DOWNLOADS)), ("DOCUMENTS", "Documents", tr(Msg.DOCUMENTS)),
                   ("MUSIC", "Music", tr(Msg.MUSIC)), ("VIDEOS", "Videos", tr(Msg.VIDEOS)),
                   ("PICTURES", "Pictures", tr(Msg.PICTURES)))
    for identifier, fallback, label in definitions:
        match = re.search(r'^XDG_' + identifier + r'_DIR="([^"\n]*)"\s*$', text, re.MULTILINE)
        value = match[1].replace("${HOME}", str(home)).replace("$HOME", str(home)) if match else str(home / fallback)
        if any(character in value for character in ("$", "`", "\x00")):
            continue
        directory = Path(value)
        if directory.is_absolute() and directory.is_dir() and directory != home:
            result.append({"id": identifier.lower(), "path": str(directory), "name": label, "icon": "folder"})
    result.extend([{"id": "root", "path": "/", "name": tr(Msg.FILE_SYSTEM), "icon": "drive-harddisk"},
                   {"id": "trash", "path": "trash:///", "name": tr(Msg.TRASH), "icon": "user-trash"}])
    return result


def unmount(location):
    current = next((entry for entry in mounted_locations()
                    if all(entry.get(key) == location.get(key) for key in ("path", "mountId", "device"))), None)
    directory = Path(location.get("path", "/")).resolve()
    if current is None or not any(directory != base and directory.is_relative_to(base)
            for base in (Path("/media"), Path("/run/media"), Path("/mnt"))):
        raise ValueError(tr(Msg.THE_MOUNTED_DEVICE_CHANGED_REFRESH_LOCATIONS_AND_TRY_AGAIN))
    try:
        subprocess.run(["gio", "mount", "--unmount", "--", directory.as_uri()], check=True,
                       capture_output=True, text=True, errors="replace", timeout=30)
    except subprocess.CalledProcessError as error:
        raise RuntimeError(tr(Msg.COULD_NOT_UNMOUNT_DEVICE_REASON, reason=error.stderr.strip())) from error
