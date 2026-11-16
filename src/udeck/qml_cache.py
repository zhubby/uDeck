"""
[INPUT]: 依赖 Python、QML 源码和用户缓存环境变量。
[OUTPUT]: 为当前源码选择独立的 Qt 编译缓存目录。
[POS]: 三类图形入口共用的启动边界，避免升级复用旧缓存。
[PROTOCOL]: Update this header on change, then check AGENTS.md
"""

import hashlib
import os
from pathlib import Path


def configure_qml_cache(source_root=None):
    if os.environ.get("QML_DISABLE_DISK_CACHE") == "1" or "QML_DISK_CACHE_PATH" in os.environ:
        return
    root = Path(source_root) if source_root is not None else Path(__file__).parent
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if path.suffix not in (".py", ".qml") or not path.is_file():
            continue
        digest.update(path.relative_to(root).as_posix().encode() + b"\0")
        digest.update(path.read_bytes() + b"\0")
    cache = Path(os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache")))
    os.environ["QML_DISK_CACHE_PATH"] = str(cache / "udeck/qml" / digest.hexdigest())
