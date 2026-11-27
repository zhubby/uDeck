"""[INPUT]: 依赖同名 LRC、音频标签和常规文件读取器。
[OUTPUT]: 提供按毫秒排序的歌词行或纯文本歌词。
[POS]: Music 的本地歌词解析边界；优先解析同名文件。
[PROTOCOL]: Update this header on change, then check AGENTS.md
"""

import re
from pathlib import Path

from udeck.file_preview import read_regular

MAX_LYRIC_BYTES = 128 * 1024
MAX_CUES = 2000
TIME_TAG = re.compile(r"\[(\d{1,4}):([0-5]\d)(?:[.:](\d{1,3}))?\]")
METADATA_TAG = re.compile(r"\[[a-z][\w-]*:[^\]]*\]", re.IGNORECASE)
OFFSET_TAG = re.compile(r"\[offset:\s*([+-]?\d{1,9})\s*\]", re.IGNORECASE)


def parse_lyrics(text):
    cues, plain = [], []
    offset = 0
    for line in text[:MAX_LYRIC_BYTES].splitlines():
        line = line.strip(" \t\ufeff")
        if match := OFFSET_TAG.fullmatch(line):
            offset = int(match[1])
        elif match := TIME_TAG.match(line):
            times = []
            end = 0
            while match:
                minutes, seconds, fraction = match.groups()
                times.append((int(minutes) * 60 + int(seconds)) * 1000 + int((fraction or "").ljust(3, "0")))
                end = match.end()
                match = TIME_TAG.match(line, end)
            content = line[end:].strip()[:1024]
            cues.extend((start, content) for start in times[:MAX_CUES - len(cues)])
        elif line and not METADATA_TAG.fullmatch(line):
            plain.append({"text": line[:1024]})

    if not any(text for _, text in cues):
        return {"timed": False, "lines": plain}

    grouped = {}
    for start, content in sorted(cues, key=lambda cue: cue[0]):
        translations = grouped.setdefault(max(0, start + offset), {})
        if content:
            translations[content] = None
    return {"timed": True, "lines": [{"start": start, "text": "\n".join(lines)} for start, lines in grouped.items()]}


def track_lyrics(item):
    path = Path(item["path"]).with_suffix(".lrc")
    try:
        data = read_regular(path, MAX_LYRIC_BYTES)
        if len(data) <= MAX_LYRIC_BYTES:
            try:
                text = data.decode("utf-16" if data.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig")
            except UnicodeError:
                text = data.decode("gb18030")
            if (lyrics := parse_lyrics(text))["lines"]:
                return lyrics
    except (OSError, ValueError):
        pass

    tags = item.get("metadata", {}).get("format", {}).get("tags", {})
    for name, text in tags.items():
        if name.lower().rstrip(" -") in {"lyrics", "unsyncedlyrics", "unsynced lyrics"} and isinstance(text, str):
            if (lyrics := parse_lyrics(text))["lines"]:
                return lyrics
    return {"timed": False, "lines": []}
