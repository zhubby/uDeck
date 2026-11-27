"""[INPUT]: 依赖共享菜单、会话组件动作和 ACP 控制请求。
[OUTPUT]: 路由会话内操作、认证与结构化表单。
[POS]: AgentController 的交互入口。
[PROTOCOL]: Update this header on change, then check AGENTS.md
"""

import base64
import json
import mimetypes
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from PySide6.QtCore import QTimer

from udeck.i18n import Msg, tr

from .content import AUDIO_FORMATS, MAX_TEXT
from .install import command
from .session_events import records


class SessionActions:
    def _workspace_menu(self, key, default):
        values = {"cwd": default}
        body = tr(Msg.AGENT_PI_ACCESS if key == "pi" else Msg.AGENT_WORKSPACE)

        def configure(label, field, initial):
            self.prompt(tr(label), lambda text: values.update({field: text}), values.get(field, initial))

        def open_session():
            options = {}
            for field in ("additionalDirectories", "mcpServers"):
                if field in values:
                    parsed = json.loads(values[field] or "[]")
                    if not isinstance(parsed, list):
                        raise ValueError(tr(Msg.AGENT_INVALID_INPUT))
                    if field == "additionalDirectories":
                        if any(not isinstance(path, str) for path in parsed):
                            raise ValueError(tr(Msg.AGENT_INVALID_INPUT))
                        paths = [Path(path).expanduser().resolve(strict=True) for path in parsed]
                        if any(not path.is_dir() for path in paths):
                            raise ValueError(tr(Msg.AGENT_WORKSPACE_ERROR))
                        parsed = [str(path) for path in paths]
                    if parsed:
                        options[field] = parsed
            if prompt := values.get("systemPrompt", "").strip():
                options["systemPrompt"] = {"mode": values.get("systemMode", "append"),
                                           "content": [{"type": "text", "text": prompt}]}
            self._open(key, values["cwd"], options=options)

        def system_mode():
            def select(mode):
                values["systemMode"] = mode
                self.pop_menu()
            self.menu(tr(Msg.AGENT_SYSTEM_PROMPT), [
                ("append", lambda: select("append")), ("override", lambda: select("override")),
            ])

        def options():
            return [
                (tr(Msg.OPEN), open_session),
                (tr(Msg.FOLDER_PATH), lambda: configure(Msg.FOLDER_PATH, "cwd", default), values["cwd"]),
                (tr(Msg.AGENT_ADDITIONAL_DIRECTORIES), lambda: configure(
                    Msg.AGENT_ADDITIONAL_DIRECTORIES, "additionalDirectories", "[]")),
                (tr(Msg.AGENT_SYSTEM_PROMPT), lambda: configure(Msg.AGENT_SYSTEM_PROMPT, "systemPrompt", "")),
                (tr(Msg.AGENT_PROTOCOL_MODE), system_mode, values.get("systemMode", "append")),
                (tr(Msg.AGENT_MCP_SERVERS), lambda: configure(Msg.AGENT_MCP_SERVERS, "mcpServers", "[]")),
            ]

        self.menu(tr(Msg.AGENT_WORKSPACE_OPTIONS), options, body)

    def _session_action(self, operation, params):
        if operation == "attach" and self.chat.state == "ready":
            self.prompt(tr(Msg.AGENT_ATTACH), self._attach_file, self.chat.cwd + "/")
            return
        if operation == "remove_attachment":
            index = params.get("index")
            if type(index) is int and 0 <= index < len(self.attachments):
                self.attachments.pop(index)
                self.publish()
            return
        if not self.chat.rpc:
            return
        if operation == "choices":
            choices = [(
                item.get("text", ""),
                lambda item=item: self._choose_action(item),
                item.get("description", ""),
            ) for item in records(params.get("actions")) if isinstance(item.get("arguments"), dict)]
            self.menu(str(params.get("title", "")), choices)
        elif operation == "command":
            name = params.get("name")
            if isinstance(name, str) and name and self.chat.state == "ready":
                self.insertPrompt.emit("/" + name + (" " if params.get("hint") else ""))
        elif operation == "request":
            self._request_action(params)
        elif operation == "retry_auth":
            self.chat.retry_auth()
        elif operation == "open_remote":
            self._open_remote(params)
        elif operation == "remote_list":
            self.clear_menus()
            self.chat.session_action("list", params)
        elif operation == "delete_remote":
            if isinstance(params.get("sessionId"), str):
                self._confirm_action(Msg.AGENT_DELETE, "delete", params.get("title", ""),
                                     {"sessionId": params["sessionId"]})
        elif operation in {"close", "logout"}:
            label = Msg.AGENT_CLOSE_SESSION if operation == "close" else Msg.AGENT_LOGOUT
            self._confirm_action(label, operation, self.chat.cwd)
        elif operation in {"mode", "config", "authenticate", "child"}:
            method = {"mode": "set_mode", "config": "set_config_option",
                      "child": "cancel"}.get(operation, operation)
            terminal = self.chat.session_action(method, params)
            if terminal is not None:
                self._protocol_login(terminal)

    def _choose_action(self, item):
        self.clear_menus()
        self.publish()
        self._session_action(item.get("action", ""), item["arguments"])
        self.publish()

    def _attach_file(self, text):
        if not self.chat.rpc or self.chat.state != "ready" or len(self.attachments) >= 8:
            return
        path = Path(text).expanduser().resolve(strict=True)
        if not path.is_file():
            raise ValueError(tr(Msg.AGENT_OPEN_FAILED))
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        value = {"type": "resource_link", "name": path.name, "uri": path.as_uri(), "mimeType": mime,
                 "size": path.stat().st_size}
        caps = self.chat.rpc.prompt_capabilities
        if mime in ("image/png", "image/jpeg", "image/gif", "image/webp") and caps.get("image") is True:
            kind = "image"
        elif mime in AUDIO_FORMATS and caps.get("audio") is True:
            kind = "audio"
        elif mime.startswith("text/") and caps.get("embeddedContext") is True:
            kind = "resource"
        else:
            kind = ""
        if kind and value["size"] <= (MAX_TEXT if kind == "resource" else 1024 * 1024):
            with path.open("rb") as stream:
                data = stream.read(1024 * 1024 + 1)
            if kind == "resource" and len(data) <= MAX_TEXT:
                try:
                    value = {"type": "resource", "resource": {
                        "uri": path.as_uri(), "mimeType": mime, "text": data.decode("utf-8"),
                    }}
                except UnicodeError:
                    pass
            elif kind != "resource" and len(data) <= 1024 * 1024:
                value = {"type": kind, "mimeType": mime, "data": base64.b64encode(data).decode("ascii")}
                if kind == "image":
                    value["uri"] = path.as_uri()
        self.attachments.append((path.name, value))
        self.publish()

    def _confirm_action(self, label, method, body, params=None):
        def confirm():
            self.clear_menus()
            self.chat.session_action(method, params)

        self.menu(tr(label), [(tr(Msg.CANCEL), self.pop_menu), (tr(Msg.CONFIRM), confirm)], str(body))

    def _open_remote(self, params):
        if self.chat.busy or not isinstance(params.get("sessionId"), str):
            return
        remote_id = params["sessionId"]
        for entry in self.chat.store.list():
            if entry["agent"] == self.chat.agent and entry["remote"] == remote_id:
                self._resume(entry)
                return
        directory = params.get("cwd")
        if not isinstance(directory, str):
            return
        try:
            cwd = Path(directory).resolve(strict=True)
            if not cwd.is_dir():
                raise ValueError
        except (OSError, ValueError):
            self.error = tr(Msg.AGENT_WORKSPACE_ERROR)
            self.publish()
            return
        agent = self.chat.agent
        title = params.get("title") or cwd.name or "/"
        key = self.chat.store.create(agent, str(cwd), str(title), remote_id)
        self._resume({"agent": agent, "directory": str(cwd), "remote": remote_id, "id": key})

    def _protocol_login(self, terminal):
        argv, env = command(self.root, self.chat.agent)
        argv.extend(terminal["args"])
        attempt = tempfile.TemporaryDirectory(prefix="udeck-acp-auth-")
        request = Path(attempt.name) / "request.json"
        status = Path(attempt.name) / "status"
        client = self.chat.client
        deadline = time.monotonic() + 600
        try:
            request.touch(mode=0o600)
            request.write_text(json.dumps({"argv": argv, "env": {**env, **terminal["env"]}}), encoding="utf-8")
            self._launch_login([sys.executable, "-m", "udeck.apps.agent.terminal_auth", str(request), str(status)],
                               {}, self.chat.cwd)
        except OSError:
            attempt.cleanup()
            raise

        def poll():
            if client is not self.chat.client or self._closed:
                attempt.cleanup()
            elif status.is_file():
                code = status.read_text(encoding="ascii")
                attempt.cleanup()
                self.chat.protocol_auth_finished(code == "0")
            elif time.monotonic() >= deadline:
                attempt.cleanup()
                self.chat.protocol_auth_finished(False)
            else:
                QTimer.singleShot(400, self, poll)

        QTimer.singleShot(400, self, poll)

    def _launch_login(self, argv, env, cwd):
        subprocess.Popen([sys.executable, "-m", "udeck.terminal.main", "--new-window",
                          "--working-directory", cwd, "-T", "Agent", "-e", *argv],
                         env={**os.environ, **env}, start_new_session=True, stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.clear_menus()
        self.notice = tr(Msg.AGENT_LOGIN_RETURN)
        self.publish()

    def _request_action(self, params):
        token, decision = params.get("token"), params.get("decision")
        entry = self.chat.client_requests.get(token) if isinstance(token, str) else None
        if not entry or decision not in ("accept", "decline", "cancel") or not self.window or not self.window.isActive():
            return
        _identifier, method, payload = entry
        if decision == "accept" and method == "elicitation/create":
            if payload["mode"] == "form":
                self._elicitation_form(token, payload)
                return
            if payload["mode"] == "url":
                def open_url():
                    if token not in self.chat.client_requests or not self.window.isActive():
                        self.pop_menu()
                        return
                    self._launch_browser(payload["url"])
                    self.chat.respond_request(token, "accept")
                    self.clear_menus()
                    self.publish()

                self.menu(tr(Msg.AGENT_PROTOCOL_ELICITATION), [
                    (tr(Msg.CANCEL), self.pop_menu), (tr(Msg.AGENT_OPEN_LINK), open_url),
                ], payload["url"])
                return
        self.chat.respond_request(token, decision)

    @staticmethod
    def _launch_browser(url):
        subprocess.Popen([sys.executable, "-m", "udeck.apps.main", "browser", url],
                         start_new_session=True, stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def _elicitation_form(self, token, params):
        schema = params["requestedSchema"]
        fields = schema.get("properties", {})
        required = frozenset(schema.get("required") or [])
        values = {}

        def edit(key):
            spec = fields[key]
            title = str(spec.get("title") or key)
            kind = spec["type"]
            initial = values.get(key, spec.get("default"))

            def set_value(value):
                values[key] = value
                self.pop_menu()

            options = spec.get("oneOf", spec.get("anyOf", spec.get("enum")))
            actions = []
            if key not in required:
                def skip():
                    values.pop(key, None)
                    self.pop_menu()
                actions.append((tr(Msg.AGENT_SKIP_FIELD), skip))
            if kind == "boolean":
                self.menu(title, [(tr(Msg.ENABLED), lambda: set_value(True)),
                                  (tr(Msg.DISABLED), lambda: set_value(False)), *actions])
            elif kind == "string" and isinstance(options, list):
                choices = []
                for item in options:
                    value = item.get("const") if isinstance(item, dict) else item
                    if isinstance(value, str):
                        label = item.get("title") or value if isinstance(item, dict) else value
                        choices.append((label, lambda value=value: set_value(value)))
                self.menu(title, [*choices, *actions])
            else:
                def parse(text):
                    try:
                        values[key] = text if kind == "string" else json.loads(text)
                    except ValueError:
                        values.pop(key, None)

                draft = "" if initial is None else str(initial) if kind == "string" else json.dumps(initial)
                self.prompt(title, parse, draft, str(spec.get("description", "")))

        def complete():
            if self.chat.respond_request(token, "accept", values):
                self.clear_menus()
                self.publish()
            else:
                self.menu(tr(Msg.AGENT_PROTOCOL_ELICITATION), body=tr(Msg.AGENT_INVALID_INPUT))

        def form_options():
            options = [(str(spec.get("title") or key), lambda key=key: edit(key),
                        ("✓" if key in values else "*" if key in required else ""))
                       for key, spec in fields.items()]
            return [*options, (tr(Msg.CONFIRM), complete), (tr(Msg.CANCEL), self.pop_menu)]

        self.menu(tr(Msg.AGENT_PROTOCOL_ELICITATION), form_options, params["message"])
