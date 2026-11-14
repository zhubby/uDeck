"""RetroArch native save management and background rclone synchronization."""

import os
from pathlib import Path

SERVICE = "io.github.zhubby.uDeck.EmulatorSaves"
OBJECT_PATH = "/io/github/zhubby/uDeck/EmulatorSaves"


def data_directory(directory=None):
    return Path(directory) if directory is not None else Path(os.environ.get(
        "XDG_DATA_HOME", str(Path.home() / ".local/share"))) / "udeck/apps"
