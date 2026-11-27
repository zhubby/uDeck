"""[INPUT]: 依赖 ACP 内容块、工具输出和计划条目。
[OUTPUT]: 提供有界、可保存的消息内容块。
[POS]: 会话存储与展示前的协议转换。
[PROTOCOL]: Update this header on change, then check AGENTS.md
"""

import base64
import binascii

MAX_TEXT = 256 * 1024
_MAX_MEDIA = 2 * 1024 * 1024
_MAX_BLOCKS = 24
_IMAGE = frozenset({"image/png", "image/jpeg", "image/webp", "image/gif"})
AUDIO_FORMATS = {
    "audio/wav": "wav", "audio/x-wav": "wav", "audio/mpeg": "mp3",
    "audio/mp4": "m4a", "audio/ogg": "ogg", "audio/flac": "flac", "audio/webm": "webm",
}


def string(value, limit=MAX_TEXT):
    return value[:limit] if isinstance(value, str) else ""


def media_data(value, allowed):
    if not allowed or not isinstance(value, str) or not value or len(value) > _MAX_MEDIA:
        return ""
    try:
        base64.b64decode(value, validate=True)
    except (ValueError, binascii.Error):
        return ""
    return value


def content_block(block):
    if not isinstance(block, dict):
        return None
    kind = block.get("type")
    if kind == "text":
        text = string(block.get("text"))
        return {"type": kind, "text": text} if text else None
    if kind in ("image", "audio"):
        mime = string(block.get("mimeType"), 100).lower()
        data = media_data(block.get("data"), mime in (_IMAGE if kind == "image" else AUDIO_FORMATS))
        return {"type": kind, "mimeType": mime, "data": data, "uri": string(block.get("uri"), 2000)}
    if kind == "resource_link":
        result = {"type": kind, "name": string(block.get("title") or block.get("name"), 1000),
                  "mimeType": string(block.get("mimeType"), 100), "uri": string(block.get("uri"), 2000),
                  "text": string(block.get("description"), 4000)}
        if type(block.get("size")) is int and block["size"] >= 0:
            result["byteSize"] = str(block["size"])
        return result
    if kind == "resource" and isinstance(resource := block.get("resource"), dict):
        mime = string(resource.get("mimeType"), 100).lower()
        return {"type": kind, "uri": string(resource.get("uri"), 2000), "mimeType": mime,
                "text": string(resource.get("text"), 16000),
                "data": media_data(resource.get("blob"), mime in _IMAGE or mime in AUDIO_FORMATS)}
    return None


def blocks(values, *, tool=False):
    if not isinstance(values, list):
        return []
    result = []
    media_size = 0
    for value in values[:_MAX_BLOCKS]:
        if not isinstance(value, dict):
            continue
        kind = value.get("type")
        if tool and kind == "diff":
            block = {"type": kind, "path": string(value.get("path"), 2000),
                     "oldText": string(value["oldText"], 16000) if isinstance(value.get("oldText"), str) else None,
                     "newText": string(value.get("newText"), 16000)}
        elif tool and kind in ("terminal", "session"):
            field = "terminalId" if kind == "terminal" else "sessionId"
            block = {"type": kind, field: string(value.get(field), 2000)}
        else:
            block = content_block(value.get("content") if tool and kind == "content" else value)
        if block:
            media_size += len(block.get("data", ""))
            if media_size > _MAX_MEDIA:
                block["data"] = ""
            result.append(block)
    return result


def append_block(target, block):
    if not block:
        return
    if block["type"] == "text" and target and target[-1]["type"] == "text":
        text = target[-1]["text"]
        target[-1]["text"] = text + block["text"][:MAX_TEXT - len(text)]
    elif len(target) < _MAX_BLOCKS:
        if block.get("data") and sum(len(item.get("data", "")) for item in target) + len(block["data"]) > _MAX_MEDIA:
            block["data"] = ""
        target.append(block)


def plan_blocks(entries):
    if not isinstance(entries, list):
        return []
    return [{"type": "plan", "text": string(entry["content"], 2000),
             "status": string(entry.get("status"), 80), "priority": string(entry.get("priority"), 80)}
            for entry in entries[:32] if isinstance(entry, dict) and isinstance(entry.get("content"), str)]
