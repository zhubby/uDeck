"""[INPUT]: 依赖 ACP 双向调用、本地会话库与 Qt 显示模型。
[OUTPUT]: 提供会话生命周期、交互请求与增量对话模型。
[POS]: 连接控制器动作与本机 Agent。
[PROTOCOL]: Update this header on change, then check AGENTS.md
"""

import sqlite3
from pathlib import Path

from PySide6.QtCore import QAbstractListModel, QModelIndex, QObject, Qt, QTimer, Signal

from udeck.i18n import Msg, render, tr

from .acp import AcpClient
from .client_events import ClientEvents
from .content import MAX_TEXT, append_block, blocks, content_block, plan_blocks, string
from .session_events import (
    METADATA_EVENTS,
    action,
    child_result_blocks,
    display_json,
    metadata_row,
    records,
    result_row,
    text_block,
)
from .session_rpc import SessionRpc
from .sessions import reconcile_replay

_KIND = Qt.ItemDataRole.UserRole + 1
_ROLES = {
    _KIND + index: (name, f"entry{name.capitalize()}".encode(), default)
    for index, (name, default) in enumerate((
        ("kind", ""), ("text", ""), ("status", ""), ("detail", ""), ("blocks", []), ("streaming", False),
        ("origin", ""),
    ))
}
_CHUNKS = {"agent_message_chunk": "agent", "agent_thought_chunk": "thought"}
_ENTITIES = {
    "tool_call": ("tool", "toolCallId"),
    "tool_call_update": ("tool", "toolCallId"),
    "compaction_update": ("compaction", "compactionId"),
    "compaction_summary_chunk": ("compaction", "compactionId"),
    "subagent_update": ("subagent", "sessionId"),
    "session_message": ("session_message", "messageId"),
    "session_message_chunk": ("session_message", "messageId"),
}


class Transcript(QAbstractListModel):
    def __init__(self, parent):
        super().__init__(parent)
        self.rows = []
        self.language = getattr(parent.parent(), "language", "en")

    def roleNames(self):
        return {key: name for key, (_, name, _) in _ROLES.items()}

    def rowCount(self, parent=None):
        return 0 if parent is not None and parent.isValid() else len(self.rows)

    def data(self, index, role):
        if role not in _ROLES or not index.isValid() or index.row() >= len(self.rows):
            return None
        field, _, default = _ROLES[role]
        return render(self.rows[index.row()].get(field, default), self.language)

    def reset(self, rows):
        self.beginResetModel()
        self.rows = rows
        self.endResetModel()

    def append(self, row):
        index = len(self.rows)
        self.beginInsertRows(QModelIndex(), index, index)
        self.rows.append(row)
        self.endInsertRows()
        return index

    def redraw(self, index):
        model_index = self.index(index, 0)
        self.dataChanged.emit(model_index, model_index, list(_ROLES))

    def retranslate(self, language):
        if language == self.language:
            return
        self.language = language
        if self.rows:
            self.dataChanged.emit(self.index(0, 0), self.index(len(self.rows) - 1, 0), list(_ROLES))

    def remove(self, index):
        self.beginRemoveRows(QModelIndex(), index, index)
        self.rows.pop(index)
        self.endRemoveRows()


class Conversation(QObject, ClientEvents):
    changed = Signal()

    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self.model = Transcript(self)
        self.client = None
        self.rpc = None
        self.connection_request = None
        self.start_updates = []
        self.metadata = {}
        self.prompt_index = None
        self.user_echo = []
        self.prompt_blocks = []
        self.control_busy = False
        self.connection_options = {}
        self.client_requests = {}
        self.request_serial = 0
        self.retiring = set()
        self.state = "idle"
        self.key = ""
        self.agent = ""
        self.cwd = ""
        self.remote = ""
        self.permissions = {}
        self.events = []
        self.dirty = set()
        self.truncate = False
        self.entities = {}
        self.response = None
        self.error = ""
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(55)
        self.timer.timeout.connect(self._flush)
        self.save_timer = QTimer(self)
        self.save_timer.setSingleShot(True)
        self.save_timer.setInterval(350)
        self.save_timer.timeout.connect(self._save)

    @property
    def busy(self):
        return self.control_busy or self.state in {"starting", "sending", "stopping"}

    def select(self, session):
        self.stop_connection()
        self.key = session["id"]
        self.agent = session["agent"]
        self.cwd = session["directory"]
        self.remote = session["remote"]
        self.error = ""
        self.dirty.clear()
        self.model.reset(self.store.messages(self.key))
        self.changed.emit()

    def open(self, agent, cwd, argv, env, *, resume=None, load_history=False, options=None):
        self.stop_connection()
        if resume and self.key != resume["id"]:
            self.model.reset(self.store.messages(resume["id"]))
        elif not resume:
            self.key = self.remote = ""
            self.dirty.clear()
            self.model.reset([])
        self.error = ""
        self.state = "starting"
        self.agent, self.cwd = agent, str(cwd)
        if resume:
            self.key, self.remote = resume["id"], resume["remote"]
        self.connection_options = dict(options or {})
        self.connection_request = ("new", self.connection_options, self._created)
        client = AcpClient(argv, cwd, env=env, parent=self, capabilities={
            "subagents": {}, "auth": {"terminal": True},
            "session": {"notices": {}, "compaction": {}, "configOptions": {"boolean": {}}},
        })
        self.client = client
        client.update.connect(lambda params: self._queue(client, params))
        client.permission.connect(lambda identifier, params: self._permission(client, identifier, params))
        client.disconnected.connect(lambda reason: self._lost(client, reason))
        client.client_action.connect(lambda key, method, params: self._client_request(client, key, method, params))
        client.client_action_closed.connect(lambda key: self._client_request_closed(client, key))
        client.client_result.connect(lambda key, method, value, error: self._client_result(
            client, key, method, value, error))
        client.request_cancelled.connect(lambda key: self._permission_cancelled(client, key))
        client.terminal_changed.connect(lambda sid, key, value: self._terminal(client, sid, key, value))
        client.elicitation_completed.connect(lambda value: self._elicitation_complete(client, value))

        def ready(result, error):
            if client is not self.client:
                return
            if error or not isinstance(result, dict) or result.get("protocolVersion") != 1:
                self._failed("protocol")
                return
            self.rpc = SessionRpc(client, result, self.cwd)
            if resume:
                method = "resume" if not load_history and self.model.rows and self.rpc.supported("resume") else "load"
                if not self.rpc.supported(method) and self.rpc.supported("resume"):
                    method = "resume"
                if not self.rpc.supported(method):
                    self._failed("resume")
                    return
                self.connection_request = (method, {**self.connection_options, "sessionId": resume["remote"]},
                                           self._loaded)
                client.set_session_roots(resume["remote"], self._roots())
            self._connect_session()

        client.start(ready)
        QTimer.singleShot(16000, self, lambda: self._fail_start(client))
        self.changed.emit()

    def _connect_session(self):
        method, params, callback = self.connection_request
        self.rpc.request(method, params, callback, timeout=30000)

    def _roots(self):
        return [self.cwd, *self.connection_options.get("additionalDirectories", [])]

    def session_action(self, method, params=None):
        rpc = self.rpc
        if not rpc or self.control_busy:
            return
        if self.state != "ready" and not (self.state == "auth" and method == "authenticate"):
            if method == "cancel" and self.state == "sending":
                rpc.request(method, params)
            return
        if method == "authenticate":
            terminal = rpc.terminal_auth((params or {}).get("methodId"))
            if terminal is not None:
                return terminal
        self.control_busy = True
        self.changed.emit()

        def completed(value, error):
            if rpc is not self.rpc:
                return
            self.control_busy = False
            if error:
                self._card("result", text=tr(Msg.AGENT_PROTOCOL_REQUEST), status="failed",
                           detail=string(error.get("message"), 1000), transient=True)
            elif method == "authenticate" and self.connection_request:
                self.state, self.error = "starting", ""
                self._connect_session()
            elif method == "list":
                self._remote_list(value)
            elif method == "delete":
                target = params["sessionId"]
                for entry in self.store.list():
                    if entry["agent"] == self.agent and entry["remote"] == target:
                        if entry["id"] == self.key:
                            self.stop_connection()
                            self.key = self.remote = ""
                            self.model.reset([])
                        self.store.delete(entry["id"])
            elif method == "set_config_option" and isinstance(value, dict):
                self._metadata_result("config", value)
            elif method == "set_mode":
                self._metadata_result("mode", {"currentModeId": params["modeId"]})
            if not error and method in {"close", "logout"}:
                self.stop_connection()
            if method != "list" and not error:
                self._card("result", text=tr(Msg.DONE), detail=method, status="completed", transient=True)
            self.changed.emit()

        identifier = (params or {}).get("sessionId", self.remote)
        rpc.request(method, params, completed, session_id=identifier if method not in {
            "authenticate", "logout", "list",
        } else None, timeout=120000 if method == "authenticate" else 15000)

    def _remote_list(self, value):
        value = value if isinstance(value, dict) else {}
        choices = []
        for item in records(value.get("sessions")):
            identifier = string(item.get("sessionId"), 4096)
            cwd = string(item.get("cwd"), 4096)
            if not identifier or not cwd:
                continue
            title = string(item.get("title"), 240) or Path(cwd).name or identifier
            args = {"sessionId": identifier, "cwd": cwd, "title": title}
            choices.append(action(title, "open_remote", args, detail=cwd))
            if self.rpc.supported("delete", session_id=identifier):
                choices.append(action(tr(Msg.AGENT_DELETE) + " · " + title, "delete_remote", args))
        if (cursor := string(value.get("nextCursor"), 4096)):
            choices.append(action(tr(Msg.AGENT_MORE_SESSIONS), "remote_list", {"cursor": cursor}))
        self._card("remote_sessions", blocks=choices, transient=True,
                   text="" if choices else tr(Msg.AGENT_EMPTY_HISTORY))

    def _metadata_result(self, kind, value):
        modified = set()
        self._update_metadata(kind, value, self.remote, modified)
        self.dirty.update(modified)
        for index in modified:
            self.model.redraw(index)
        self._save()

    def _connection_card(self):
        if not self.rpc.auth_methods:
            return
        choices = []
        for method in self.rpc.auth_methods:
            identifier = method["id"]
            choices.append(action(string(method["name"], 240), "authenticate", {"methodId": identifier},
                                  detail=string(method.get("description"), 1000)))
        self._card("auth", transient=True, blocks=choices)

    def retry_auth(self):
        if self.state == "auth" and self.connection_request and self.rpc and not self.control_busy:
            self.state, self.error = "starting", ""
            self.changed.emit()
            self._connect_session()

    def protocol_auth_finished(self, success):
        self._card("result", text=tr(Msg.DONE if success else Msg.AGENT_AUTH_REQUIRED),
                   status="completed" if success else "failed", transient=True)
        if success and self.state == "auth":
            self.retry_auth()
        else:
            self.changed.emit()

    def _fail_start(self, client):
        if client is self.client and self.state == "starting" and not client.group:
            self._failed("launch")

    def _created(self, result, error):
        remote = result.get("sessionId") if isinstance(result, dict) else None
        if error or not isinstance(remote, str) or not remote:
            self._request_failed(error, "connection")
            return
        try:
            self.key = self.store.create(self.agent, self.cwd, self.cwd.rsplit("/", 1)[-1] or "/", remote)
        except (OSError, sqlite3.Error):
            self._failed("storage")
            return
        self.remote = remote
        self.client.set_session_roots(remote, self._roots())
        self._release_start_updates(result)

    def _loaded(self, result, error):
        if error:
            self._request_failed(error, "resume")
            return
        if self.connection_request[0] == "load":
            self.start_updates = reconcile_replay(self.model.rows, self.start_updates, self.remote)
        self.entities.update(
            (tuple(row["entity"]), index) for index, row in enumerate(self.model.rows)
            if isinstance(row.get("entity"), list) and all(isinstance(key, str) for key in row["entity"]))
        self.metadata.update((tuple(row["entity"]), row["metadata"].copy()) for row in self.model.rows
                             if isinstance(row.get("metadata"), dict) and row.get("entity"))
        self._release_start_updates(result)

    def _release_start_updates(self, result):
        self.connection_request = None
        self._connection_card()
        if isinstance(result, dict):
            if isinstance(result.get("modes"), dict):
                self._metadata_result("mode", result["modes"])
            if isinstance(result.get("configOptions"), list):
                self._metadata_result("config", result)
        updates, self.start_updates = self.start_updates, []
        for session_id, update in updates:
            self._accept_update(session_id, update)
        self._flush(final=True)
        self._ready()

    def _request_failed(self, error, fallback):
        if isinstance(error, dict) and error.get("code") == -32000:
            if self.connection_request and self.rpc and self.rpc.auth_methods:
                self.state = "auth"
                self.error = "login"
                self.start_updates.clear()
                self._connection_card()
                self.changed.emit()
                return
            fallback = "login"
        self._failed(fallback)

    def _ready(self):
        self.state = "ready"
        self.changed.emit()

    def _failed(self, reason):
        self.stop_connection()
        self.error = reason
        self.changed.emit()

    def _lost(self, client, _reason):
        if client is self.client:
            if self.state in {"sending", "stopping"}:
                self._flush(final=True)
                self._append_row({"kind": "result", "text": tr(Msg.AGENT_DISCONNECTED), "status": "failed"})
            self._failed("disconnected")

    def send(self, text):
        if not text.strip() or len(text) > MAX_TEXT:
            return False
        return self.send_blocks([{"type": "text", "text": text}])

    def send_blocks(self, prompt):
        if self.state != "ready" or self.control_busy or not self.rpc or not prompt:
            return False
        self.entities.pop(("plan", None), None)
        rendered = blocks(prompt)
        if not rendered:
            return False
        self.prompt_blocks = rendered
        self.user_echo = []
        row = {"kind": "user", "text": "", "blocks": rendered}
        if len(rendered) == 1 and rendered[0]["type"] == "text":
            row = {"kind": "user", "text": rendered[0]["text"]}
        index = self.model.append(row)
        self.prompt_index = index
        self.dirty.add(index)
        self._save()
        self.state = "sending"
        if not self.rpc.request("prompt", {"prompt": prompt}, self._completed,
                                session_id=self.remote, timeout=0):
            return False
        self.changed.emit()
        return True

    def stop(self):
        if self.state != "sending":
            return
        self.state = "stopping"
        self._flush(final=True)
        self._cancel_permissions()
        client = self.client
        client.notify("session/cancel", {"sessionId": self.remote})
        self._cancel_client_requests()
        QTimer.singleShot(3500, self, lambda: self._stop_timeout(client))
        self.changed.emit()

    def _stop_timeout(self, client):
        if self.client is client and self.state == "stopping":
            self._flush(final=True)
            self._append_row(result_row({}, None, stopping=True))
            self._failed("stopped")

    def _completed(self, result, error):
        self._flush(final=True)
        report = result_row(result, error, stopping=self.state == "stopping")
        self._append_row(report)
        self._save()
        self._cancel_permissions()
        self._cancel_client_requests()
        if error:
            self.prompt_index = None
            if self.state == "stopping":
                self.error = "stopped"
                self._ready()
            else:
                self._request_failed(error, "prompt")
        else:
            self.error = "stopped" if self.state == "stopping" or (
                isinstance(result, dict) and result.get("stopReason") == "cancelled") else ""
            self.prompt_index = None
            self._ready()

    def _permission(self, client, identifier, params):
        if (client is not self.client or self.state not in {"ready", "sending"} or not self.rpc
                or not self.rpc.accepts_update(self.remote, params.get("sessionId"))):
            client.answer_permission(identifier)
            return
        options = params.get("options")
        if not isinstance(options, list) or len(self.permissions) >= 16:
            client.answer_permission(identifier)
            return
        options = [item for item in options[:24] if isinstance(item, dict)
                   and isinstance(item.get("optionId"), str) and isinstance(item.get("name"), str)]
        if not options:
            client.answer_permission(identifier)
            return
        tool = params.get("toolCall")
        detail = ""
        if isinstance(tool, dict):
            title = str(tool.get("title", ""))[:1000]
            locations = tool.get("locations")
            paths = [location["path"][:400] for location in locations[:5]
                     if isinstance(location, dict) and isinstance(location.get("path"), str)
                     ] if isinstance(locations, list) else []
            detail = "\n".join([title, *paths])
        self._flush(final=True)
        self.permissions[identifier] = (detail, options)
        self._card("permission", text=detail, status="pending", transient=True,
                   permission=identifier, blocks=[
                       text_block(string(item["name"], 200)) for item in options
                   ])
        self.changed.emit()

    def respond(self, option):
        if self.permissions and self.client:
            identifier = next(iter(self.permissions))
            _title, options = self.permissions[identifier]
            if option is not None and option not in {item["optionId"] for item in options}:
                return
            del self.permissions[identifier]
            self.client.answer_permission(identifier, option)
            self._finish_permission(identifier, "completed" if option is not None else "cancelled")
            self.changed.emit()

    def _cancel_permissions(self):
        if self.client:
            for identifier in self.permissions:
                self.client.answer_permission(identifier)
                self._finish_permission(identifier, "cancelled")
        self.permissions.clear()

    def _queue(self, client, params):
        session_id, update = params.get("sessionId"), params.get("update")
        if client is not self.client or not isinstance(update, dict) or not isinstance(session_id, str):
            return
        if self.state == "starting":
            if len(self.start_updates) < 4096:
                self.start_updates.append((session_id, update))
            else:
                self._failed("protocol")
        elif self._accept_update(session_id, update) and not self.timer.isActive():
            self.timer.start()

    def _accept_update(self, session_id, update):
        if not self.remote or not self.rpc or not self.rpc.accepts_update(self.remote, session_id):
            return False
        if update.get("sessionUpdate") == "subagent_update":
            if not self.rpc.update_subagent(session_id, update):
                return False
            child_id = update["sessionId"]
            child = self.rpc.subagents[child_id]
            try:
                allowed = [Path(path) for path in self._roots()]
                parents = self.rpc.subagents.get(session_id, {})
                inherited = parents.get("effectiveRoots", allowed)
                primary = child.get("cwd") or (inherited[0] if inherited else None)
                extra = child.get("additionalDirectories")
                roots = [primary, *(extra if isinstance(extra, list) else inherited[1:])]
                resolved = [Path(path).resolve() for path in roots
                            if isinstance(path, (str, Path)) and Path(path).is_absolute()]
                child["effectiveRoots"] = [path for path in resolved if any(
                    path.is_relative_to(root) for root in allowed)]
                self.client.set_session_roots(child_id, child["effectiveRoots"])
            except (OSError, ValueError, RuntimeError):
                self.client.clear_session(child_id)
        self.events.append((session_id, update))
        return True

    def _flush(self, *, final=False):
        self.timer.stop()
        events, self.events = self.events, []
        modified = set()
        for event in events:
            session_id, update = event if isinstance(event, tuple) else (self.remote, event)
            kind = update.get("sessionUpdate")
            if not isinstance(kind, str):
                continue
            if kind == "user_message_chunk":
                block = content_block(update.get("content"))
                if self.prompt_index is not None and session_id == self.remote:
                    append_block(self.user_echo, block)
                else:
                    self._chunk("user", block, modified, session_id)
            elif kind in _CHUNKS:
                self._chunk(_CHUNKS[kind], content_block(update.get("content")), modified, session_id)
            elif kind in _ENTITIES:
                self._entity(kind, update, modified, session_id)
            elif kind in ("plan", "plan_update", "plan_removed"):
                self._plan(kind, update, modified, session_id)
            elif kind in METADATA_EVENTS:
                self._update_metadata(METADATA_EVENTS[kind], update, session_id, modified)
            elif kind == "notice" and (title := string(update.get("title"), 1000)):
                self._end_response(modified)
                self.model.append({"kind": "notice", "text": title, "transient": True,
                                   "status": string(update.get("severity"), 80),
                                   "detail": string(update.get("description"), 4000)})
        self._commit_echo(modified)
        if final:
            self._end_response(modified)
        for index in modified:
            self.model.redraw(index)
        self.dirty.update(modified)
        if (self.dirty or self.truncate) and not self.save_timer.isActive():
            self.save_timer.start()

    def _commit_echo(self, modified):
        if self.prompt_index is None or not self.user_echo:
            return
        row = self.model.rows[self.prompt_index]
        received = [block.copy() for block in self.user_echo]
        if all(block["type"] == "text" for block in received):
            received.extend(block for block in self.prompt_blocks if block["type"] != "text")
        if len(received) == 1 and received[0]["type"] == "text":
            row.update(text=received[0]["text"], blocks=[])
        else:
            row.update(text="", blocks=received)
        modified.add(self.prompt_index)

    def _append_row(self, row):
        index = self.model.append(row)
        if not row.get("transient"):
            self.dirty.add(index)
            if not self.save_timer.isActive():
                self.save_timer.start()

    def _card(self, kind, **fields):
        self._append_row({"kind": kind, **fields})

    def _update_metadata(self, kind, payload, session_id, modified):
        key = (kind, session_id)
        data = self.metadata.setdefault(key, {})
        data.update({name: value for name, value in payload.items() if name not in ("_meta", "sessionUpdate")})
        row = self._upsert(key, kind, modified, boundary=False)
        row.update(metadata_row(kind, data))
        row["metadata"] = data.copy()
        if session_id != self.remote:
            child = self.rpc.subagents.get(session_id, {}) if self.rpc else {}
            row["origin"] = string(child.get("title"), 240) or session_id
            for block in row["blocks"]:
                if block["type"] == "action":
                    block["disabled"] = True

    def _end_response(self, modified):
        if self.response is not None:
            row = self.model.rows[self.response]
            if row.pop("streaming", False):
                modified.add(self.response)
            self.response = None

    def _chunk(self, kind, block, modified, session_id):
        if not block:
            return
        plain = block["type"] == "text"
        row = self.model.rows[self.response] if self.response is not None else None
        if row is None or row["kind"] != kind or row.get("source") != session_id or not plain or "blocks" in row:
            self._end_response(modified)
            row = {"kind": kind, "text": "", "source": session_id,
                   "streaming": plain and kind != "user" and self.state == "sending"}
            if session_id != self.remote and self.rpc:
                row["origin"] = string(self.rpc.subagents.get(session_id, {}).get("title"), 240) or session_id
            self.response = self.model.append(row)
        if plain:
            row["text"] += block["text"][:MAX_TEXT - len(row["text"])]
        else:
            row["blocks"] = [block]
        modified.add(self.response)

    def _upsert(self, key, kind, modified, *, boundary=True):
        if key not in self.entities:
            if boundary:
                self._end_response(modified)
            row = {"kind": kind}
            if key[-1] is not None:
                row["entity"] = list(key)
            self.entities[key] = self.model.append(row)
        index = self.entities[key]
        modified.add(index)
        return self.model.rows[index]

    def _entity(self, event, update, modified, session_id):
        kind, id_field = _ENTITIES[event]
        identifier = string(update.get(id_field), 2000)
        if not identifier:
            return
        key = (kind, identifier) if session_id == self.remote else (kind, session_id, identifier)
        row = self._upsert(key, "subagent" if kind == "session_message" else kind, modified)
        if session_id != self.remote and self.rpc:
            row["origin"] = string(self.rpc.subagents.get(session_id, {}).get("title"), 240) or session_id
        if kind == "tool":
            self._tool(row, update)
        elif event.endswith("_chunk"):
            append_block(row.setdefault("blocks", []), content_block(update.get("content")))
            if kind == "compaction":
                row.setdefault("status", "in_progress")
        elif kind == "compaction":
            row["status"] = string(update.get("status"), 80)
            if "summary" in update:
                row["blocks"] = blocks(update["summary"])
            if "error" in update:
                row["detail"] = string(update["error"], 4000)
        elif kind == "subagent":
            if "title" in update or "text" not in row:
                row["text"] = string(update.get("title"), 1000) or identifier
            if "description" in update:
                row["detail"] = string(update["description"], 4000)
            if "state" in update:
                state = update["state"]
                row["status"] = string(state.get("state"), 80) if isinstance(state, dict) else ""
                row["childResult"] = child_result_blocks(state)
            if self.rpc:
                child = self.rpc.subagents.get(identifier, {})
                child_blocks = [text_block(str(path)) for path in child.get("effectiveRoots", [])]
                child_blocks.extend(row.get("childResult", []))
                if self.rpc.supported("cancel", session_id=identifier):
                    child_blocks.append(action(tr(Msg.AGENT_STOP), "child", {"sessionId": identifier}))
                row["blocks"] = child_blocks
        else:
            for field in ("senderSessionId", "recipientSessionId", "senderMessageId", "recipientMessageId"):
                if field in update:
                    row[field] = string(update[field], 1000)
            row["text"] = " → ".join(row[field] for field in ("senderSessionId", "recipientSessionId") if row.get(field))
            row["detail"] = " → ".join(row[field] for field in ("senderMessageId", "recipientMessageId") if row.get(field))
            if "content" in update:
                row["blocks"] = blocks(update["content"])

    def _plan(self, event, update, modified, session_id):
        plan = update.get("plan") if event == "plan_update" else update
        if not isinstance(plan, dict):
            return
        identifier = string(plan.get("planId"), 2000) if event != "plan" else None
        if identifier == "":
            return
        key = ("plan", identifier) if session_id == self.remote else ("plan", session_id, identifier)
        if event == "plan_removed":
            index = self.entities.pop(key, None)
            if index is not None:
                self.model.remove(index)
                for entity, position in self.entities.items():
                    self.entities[entity] = position - (position > index)
                if self.response is not None and self.response > index:
                    self.response -= 1
                if self.prompt_index is not None and self.prompt_index > index:
                    self.prompt_index -= 1
                modified.clear()
                modified.update(range(len(self.model.rows)))
                self.dirty.clear()
                self.truncate = True
            return
        self._upsert(key, "plan", modified).update(
            text=string(plan.get("content")), detail=string(plan.get("path"), 2000),
            blocks=plan_blocks(plan.get("entries")))

    @staticmethod
    def _tool(row, update):
        if isinstance(update.get("title"), str):
            row["text"] = update["title"][:4000]
        if isinstance(update.get("status"), str):
            row["status"] = update["status"][:80]
        if "content" in update:
            row["toolContent"] = blocks(update["content"], tool=True)
        elif "toolContent" not in row:
            row["toolContent"] = row.get("blocks", [])
        if "locations" in update:
            row["detail"] = "\n".join(
                f'{location["path"][:1000]}:{location["line"]}' if type(location.get("line")) is int
                else location["path"][:1000] for location in records(update["locations"])
                if isinstance(location.get("path"), str))
        fields = row.setdefault("toolFields", {})
        for field, label in (("kind", Msg.AGENT_TOOL_KIND), ("name", Msg.AGENT_TOOL_NAME),
                             ("rawInput", Msg.AGENT_TOOL_INPUT), ("rawOutput", Msg.AGENT_TOOL_OUTPUT)):
            if field in update:
                if update[field] is None:
                    fields.pop(field, None)
                else:
                    fields[field] = text_block(display_json(update[field]), tr(label))
        row["blocks"] = [*row["toolContent"], *fields.values()]

    def _save(self):
        self.save_timer.stop()
        if not self.key or not (self.dirty or self.truncate):
            return
        start, end = (0, len(self.model.rows)) if self.truncate else (min(self.dirty), max(self.dirty) + 1)
        position = start - sum(1 for row in self.model.rows[:start] if row.get("transient"))
        rows = self.model.rows[start:end]
        try:
            self.store.save(self.key, position, rows, truncate=self.truncate)
        except (OSError, sqlite3.Error):
            self.error = "storage"
            self.changed.emit()
        else:
            self.dirty.clear()
            self.truncate = False

    def stop_connection(self):
        if self.client and self.state in {"sending", "stopping"}:
            self.client.notify("session/cancel", {"sessionId": self.remote})
        self._flush(final=True)
        self._save()
        self.entities.clear()
        self.metadata.clear()
        self.start_updates.clear()
        self.connection_request = None
        self.prompt_index = None
        self.user_echo = []
        self.prompt_blocks = []
        self.control_busy = False
        for token in self.client_requests:
            self._finish_card("request", token, "cancelled")
        self.client_requests.clear()
        self.rpc = None
        self.truncate = False
        self._cancel_permissions()
        if self.client:
            client, self.client = self.client, None
            self.retiring.add(client)
            client.destroyed.connect(lambda: self.retiring.discard(client))
            client.close()
        self.state = "idle"

    def close(self):
        self.stop_connection()
        for client in tuple(self.retiring):
            client.close(wait=True)
        self.store.close()
