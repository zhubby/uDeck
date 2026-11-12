"""Rollback a saved configuration without another allocation or serialization."""

import os
import uuid
from contextlib import contextmanager


@contextmanager
def configuration_transaction(settings, value):
    path = settings.path
    backup = path.with_name("." + path.name + "-rollback-" + uuid.uuid4().hex)
    existed = path.exists() or path.is_symlink()
    if existed:
        # Keep the old inode until activation succeeds, including on a full disk.
        os.link(path, backup, follow_symlinks=False)
    try:
        settings.save(value)
        yield
    except BaseException:
        if existed:
            os.replace(backup, path)
        else:
            path.unlink(missing_ok=True)
        raise
    finally:
        backup.unlink(missing_ok=True)
