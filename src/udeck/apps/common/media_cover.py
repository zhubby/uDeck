"""
[INPUT]: 依赖 FFmpeg、媒体索引指纹与本地缓存目录。
[OUTPUT]: 提供音乐及视频封面缓存路径，并提取单张 JPEG。
[POS]: 库扫描线程调用。音乐取内嵌图片，视频还可提取单帧。
[PROTOCOL]: Update this header on change, then check AGENTS.md
"""

import os
import subprocess
import tempfile
from pathlib import Path


def media_cover_dir(app):
    root = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    return root.absolute() / "udeck" / f"{app}-covers"


def _extract(ffmpeg, path, mapping, seconds, bounds):
    seek = ["-ss", f"{seconds:.3f}"] if seconds else []
    try:
        result = subprocess.run([
            ffmpeg, "-v", "error", "-nostdin", "-threads", "1", "-filter_threads", "1",
            "-protocol_whitelist", "file,pipe", *seek, "-i", str(path), "-map", mapping,
            "-frames:v", "1", "-vf", f"scale={bounds}:force_original_aspect_ratio=decrease:force_divisible_by=2",
            "-c:v", "mjpeg", "-threads", "1", "-q:v", "5", "-f", "image2pipe", "pipe:1",
        ], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=3, check=True)
    except (OSError, subprocess.SubprocessError):
        return b""
    jpeg = result.stdout
    return jpeg if jpeg.startswith(b"\xff\xd8") and jpeg.endswith(b"\xff\xd9") else b""


def generate_media_cover(ffmpeg, item, target, cancelled, *, video):
    path = Path(item["path"])

    def unchanged():
        stat = path.stat()
        return not path.is_symlink() and [stat.st_size, stat.st_mtime_ns] == item["stamp"]

    try:
        if cancelled() or not unchanged():
            return None
        if target.is_file():
            return target
        attempts = [("0:v:disp:attached_pic:0", 0)]
        if video:
            seconds = min(60, max(0, item["duration"] * 0.15))
            attempts.append(("0:V:0", seconds))
            if seconds:
                attempts.append(("0:V:0", 0))
        bounds = "512:288" if video else "512:512"
        for mapping, timestamp in attempts:
            if cancelled():
                return None
            jpeg = _extract(ffmpeg, path, mapping, timestamp, bounds)
            if jpeg:
                break
        else:
            return None
        if cancelled() or not unchanged():
            return None

        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with tempfile.NamedTemporaryFile(dir=target.parent, prefix=".cover-", delete=False) as output:
            temporary = Path(output.name)
            try:
                output.write(jpeg)
                output.close()
                temporary.replace(target)
            finally:
                temporary.unlink(missing_ok=True)
        return target
    except OSError:
        return None
