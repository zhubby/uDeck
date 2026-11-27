"""[INPUT]: 依赖用户数据目录、SQLite 与 ACP 历史回放。
[OUTPUT]: 提供会话索引、消息历史和回放去重。
[POS]: 对话持久化，凭据由上游 Agent 保存。
[PROTOCOL]: Update this header on change, then check AGENTS.md
"""

import json
import sqlite3
import time
import uuid

from .content import append_block, content_block

_REPLAY_ENTITY_CHUNKS = {
    "compaction_summary_chunk": ("compaction", "compactionId"),
    "session_message_chunk": ("session_message", "messageId"),
}


def reconcile_replay(rows, updates, session_id):
    """已有本地记录时，只接收能按用户消息对齐的新轮次。"""
    local = []
    for row in rows:
        if row["kind"] == "user" and row.get("source", session_id) == session_id:
            local.append(_user_text(row["text"], row.get("blocks", [])))
    if not local:
        return updates
    turns = []
    pending = None
    for index, (source, update) in enumerate(updates):
        if source != session_id:
            continue
        kind = update.get("sessionUpdate")
        if kind == "user_message_chunk":
            if pending is None:
                pending = []
                turns.append((index, pending))
            append_block(pending, content_block(update.get("content")))
        elif kind in ("agent_message_chunk", "agent_thought_chunk", "tool_call"):
            pending = None
    replayed = [_user_text("", received) for _, received in turns]
    # Agent 可回放完整历史，也可只回放最近一段。
    overlap = next((size for size in range(min(len(local), len(replayed)), 0, -1)
                    if local[-size:] == replayed[:size]), 0)
    cutoff = turns[overlap][0] if 0 < overlap < len(turns) else len(updates)
    chunks = ("agent_message_chunk", "agent_thought_chunk", "user_message_chunk")
    saved_entities = {tuple(row["entity"]) for row in rows if row.get("entity")}
    replayed_entities = set()
    result = []
    for index, (source, update) in enumerate(updates):
        kind = update.get("sessionUpdate")
        if index < cutoff and kind in chunks:
            continue
        if kind in _REPLAY_ENTITY_CHUNKS:
            name, field = _REPLAY_ENTITY_CHUNKS[kind]
            identifier = update.get(field)
            if isinstance(identifier, str):
                entity = (name, identifier) if source == session_id else (name, source, identifier)
                if index < cutoff and entity in saved_entities and entity not in replayed_entities:
                    continue
        elif kind in ("compaction_update", "session_message"):
            name, field, content = ("compaction", "compactionId", "summary") if kind == "compaction_update" else (
                "session_message", "messageId", "content")
            identifier = update.get(field)
            if content in update and isinstance(identifier, str):
                replayed_entities.add((name, identifier) if source == session_id else (name, source, identifier))
        result.append((source, update))
    return result


def _user_text(text, blocks):
    return text or "".join(block["text"] for block in blocks if block["type"] == "text")


class SessionStore:
    def __init__(self, root):
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        path = root / "sessions.sqlite3"
        path.touch(mode=0o600, exist_ok=True)
        self.db = sqlite3.connect(path, timeout=1)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY, agent TEXT NOT NULL, directory TEXT NOT NULL,
                title TEXT NOT NULL, remote TEXT, updated INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS messages (
                session TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                position INTEGER NOT NULL, data TEXT NOT NULL,
                PRIMARY KEY (session, position)
            );
            PRAGMA foreign_keys = ON;
        """)

    def list(self):
        return [dict(row) for row in self.db.execute(
            "SELECT * FROM sessions ORDER BY updated DESC, rowid DESC")]

    def messages(self, key):
        return [json.loads(row[0]) for row in self.db.execute(
            "SELECT data FROM messages WHERE session = ? ORDER BY position", (key,))]

    def create(self, agent, directory, title, remote):
        key = uuid.uuid4().hex
        with self.db:
            self.db.execute("INSERT INTO sessions VALUES (?, ?, ?, ?, ?, ?)",
                            (key, agent, directory, title, remote, time.time_ns()))
        return key

    def save(self, key, start, messages, *, truncate=False):
        with self.db:
            if truncate:
                self.db.execute("DELETE FROM messages WHERE session = ? AND position >= ?", (key, start))
            rows = ({name: value for name, value in message.items() if name != "streaming"}
                    for message in messages if not message.get("transient"))
            self.db.executemany(
                "INSERT OR REPLACE INTO messages VALUES (?, ?, ?)",
                ((key, index, json.dumps(message, ensure_ascii=False))
                 for index, message in enumerate(rows, start)))
            self.db.execute("UPDATE sessions SET updated = ? WHERE id = ?", (time.time_ns(), key))

    def rename(self, key, title):
        with self.db:
            self.db.execute("UPDATE sessions SET title = ? WHERE id = ?", (title, key))

    def delete(self, key):
        with self.db:
            self.db.execute("DELETE FROM sessions WHERE id = ?", (key,))

    def close(self):
        self.db.close()
