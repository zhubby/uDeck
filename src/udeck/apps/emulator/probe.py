"""One disposable process per native core. Never imported by the UI to load cores."""

import ctypes
import ctypes.util
import hashlib
import json
import os
import sys
from pathlib import Path


def inspect_core(path):
    if sys.platform == "linux":
        # RetroArch links these globally, and loads cores with LAZY | LOCAL.
        # NOW, or omitting frontend libraries, produces false missing-symbol errors.
        for name in ("stdc++", "udev", "GL", "EGL", "GLESv2"):
            library = ctypes.util.find_library(name)
            if library:
                ctypes.CDLL(library, mode=os.RTLD_LAZY | os.RTLD_GLOBAL)
    core = ctypes.CDLL(str(path), mode=os.RTLD_LAZY | os.RTLD_LOCAL)
    core.retro_api_version.restype = ctypes.c_uint
    if core.retro_api_version() != 1:
        raise ValueError("Unsupported libretro API version")

    class SystemInfo(ctypes.Structure):
        _fields_ = [("name", ctypes.c_char_p), ("version", ctypes.c_char_p),
                    ("extensions", ctypes.c_char_p), ("need_fullpath", ctypes.c_bool),
                    ("block_extract", ctypes.c_bool)]

    info = SystemInfo()
    core.retro_get_system_info.argtypes = [ctypes.POINTER(SystemInfo)]
    core.retro_get_system_info(ctypes.byref(info))
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return {"status": "available", "name": (info.name or b"").decode(errors="replace"),
            "version": (info.version or b"").decode(errors="replace"),
            "extensions": (info.extensions or b"").decode(errors="replace"),
            "blockExtract": bool(info.block_extract), "coreHash": digest.hexdigest()}


if __name__ == "__main__":
    try:
        import resource

        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        result = inspect_core(Path(sys.argv[1]).resolve(strict=True))
    except Exception as error:
        result = {"status": "incompatible", "reason": str(error)[:1200]}
    print(json.dumps(result), flush=True)
    # This is an API-only probe: retro_init/deinit were deliberately not called.
    # Some cores assume initialization in static destructors. Do not run those
    # destructors in this disposable process or mislabel a successful API query.
    os._exit(0)
