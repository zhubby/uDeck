"""
[INPUT]: 依赖 FFmpeg、视频索引指纹与本地缓存目录。
[OUTPUT]: 提供视频封面缓存路径与单张 JPEG 封面。
[POS]: 视频库的封面提取层；扫描线程调用，数据写入本地缓存。
[PROTOCOL]: Update this header on change, then check AGENTS.md
"""

import os
import subprocess
import tempfile
from pathlib import Path


def video_cover_dir():
    root = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    return root.absolute() / "udeck" / "video-covers"


def _extract(ffmpeg, path, mapping, seconds):
    seek = ["-ss", f"{seconds:.3f}"] if seconds else []
    try:
        result = subprocess.run([
            ffmpeg, "-v", "error", "-nostdin", "-threads", "1", "-filter_threads", "1",
            "-protocol_whitelist", "file,pipe", *seek, "-i", str(path), "-map", mapping,
            "-frames:v", "1", "-vf", "scale=512:288:force_original_aspect_ratio=decrease:force_divisible_by=2",
            "-c:v", "mjpeg", "-threads", "1", "-q:v", "5", "-f", "image2pipe", "pipe:1",
        ], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=3, check=True)
    except (OSError, subprocess.SubprocessError):
        return b""
    jpeg = result.stdout
    return jpeg if jpeg.startswith(b"\xff\xd8") and jpeg.endswith(b"\xff\xd9") else b""


def generate_video_cover(ffmpeg, item, target, cancelled):
    path = Path(item["path"])

    def unchanged():
        stat = path.stat()
        return not path.is_symlink() and [stat.st_size, stat.st_mtime_ns] == item["stamp"]

    try:
        if cancelled() or not unchanged():
            return None
        if target.is_file():
            return target
        seconds = min(60, max(0, item["duration"] * 0.15))
        attempts = [("0:v:disp:attached_pic:0", 0), ("0:V:0", seconds)]
        if seconds:
            attempts.append(("0:V:0", 0))
        for mapping, timestamp in attempts:
            if cancelled():
                return None
            jpeg = _extract(ffmpeg, path, mapping, timestamp)
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
