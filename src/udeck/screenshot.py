"""Capture the actual Wayland desktop and publish only a verified PNG."""

import os
import subprocess
import tempfile
import uuid
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QStandardPaths
from PySide6.QtGui import QImageReader

from .i18n import tr


def capture_screen(directory=None):
    pictures = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.PicturesLocation)
    directory = Path(directory) if directory else Path(pictures or Path.home() / 'Pictures') / 'Screenshots'
    directory.mkdir(parents=True, exist_ok=True)
    if directory.is_symlink():
        raise ValueError(tr('Unsafe screenshot directory'))
    descriptor, temporary = tempfile.mkstemp(prefix='.screenshot-', suffix='.png', dir=directory)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            subprocess.run(['grim', '-t', 'png', '-'], stdout=stream, stderr=subprocess.PIPE, check=True, timeout=15)
            stream.flush()
            os.fsync(stream.fileno())
        reader = QImageReader(temporary, b'png')
        if reader.read().isNull():
            raise ValueError(tr('The screenshot did not contain a valid PNG image'))
        name = 'Screenshot-' + datetime.now().astimezone().strftime('%Y-%m-%d-%H%M%S-%f') + '-' + uuid.uuid4().hex[:8] + '.png'
        path = directory / name
        os.link(temporary, path)
        return path
    finally:
        Path(temporary).unlink(missing_ok=True)
