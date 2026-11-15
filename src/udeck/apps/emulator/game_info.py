"""Lightweight selected-game facts, without launch checks or filesystem reads."""

import math
from datetime import datetime
from pathlib import Path

from udeck.i18n import Msg, tr


def play_seconds(value):
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
        return 0
    try:
        return value if math.isfinite(value) else 0
    except OverflowError:
        return 0


def play_time(seconds):
    seconds = play_seconds(seconds)
    if 0 < seconds < 60:
        return tr(Msg.EMU_LESS_THAN_MINUTE)
    minutes = int(seconds // 60)
    if minutes < 60:
        return tr(Msg.EMU_PLAY_MINUTES, minutes=minutes)
    return tr(Msg.EMU_PLAY_HOURS_MINUTES, hours=minutes // 60, minutes=minutes % 60)


def game_info(item, catalog, data):
    if not item or item.get("kind") == "playlist":
        return []
    identifier = item.get("gameId", item["id"])
    record = data.get("positions", {}).get(identifier)
    record = record if isinstance(record, dict) else {}
    seconds = play_seconds(record.get("seconds"))
    last = tr(Msg.EMU_PLAY_TIME_UNKNOWN if seconds or identifier in data.get("recent", []) else Msg.EMU_NOT_PLAYED)
    timestamp = play_seconds(record.get("lastPlayed"))
    if timestamp:
        try:
            # Epoch seconds stay portable; presentation follows the device's timezone.
            last = datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M")
        except (OSError, ValueError, OverflowError):
            pass
    platform = catalog.platforms.get(catalog.canonical(item.get("platform", "")))
    database = item.get("dbName", "").removesuffix(".lpl")
    system = database.split(" - ", 1)[-1] if database else platform.title if platform else tr(Msg.EMU_UNKNOWN_SYSTEM)
    suffix = item.get("format", "").upper()
    archive = Path(item.get("path", "")).suffix[1:].upper() if item.get("archiveMember") else ""
    if archive:
        suffix += " / " + archive
    if suffix:
        system += " · " + suffix
    try:
        core = catalog.resolve({**item, "id": identifier}, require_available=False)
        core_name = core.name if core.status == "available" else core.name + " · " + tr(Msg.CHECKING)
    except ValueError:
        explicit = item.get("coreId") or item.get("playlistCoreId") or item.get("playlistDefaultCoreId")
        if not item.get("playlistPath"):
            explicit = explicit or catalog.preferences.get("gameCores", {}).get(identifier)
        core = catalog.cores.get(explicit)
        core_name = (core.name if core else explicit or "")
        core_name = core_name + " · " + tr(Msg.UNAVAILABLE) if core_name else tr(Msg.UNAVAILABLE)
    return [{"key": "system", "label": tr(Msg.EMU_GAME_SYSTEM), "value": system},
            {"key": "core", "label": tr(Msg.EMU_GAME_CORE), "value": core_name},
            {"key": "lastPlayed", "label": tr(Msg.EMU_LAST_PLAYED), "value": last},
            {"key": "playTime", "label": tr(Msg.EMU_PLAY_TIME), "value": play_time(seconds)}]
