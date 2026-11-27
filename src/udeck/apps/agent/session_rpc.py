"""[INPUT]: 依赖 ACP v1 能力声明和 JSON-RPC 客户端。
[OUTPUT]: 校验会话、认证与配置请求，跟踪子会话权限。
[POS]: 连接层与会话控制器之间的出站协议边界。
[PROTOCOL]: Update this header on change, then check AGENTS.md
"""

from pathlib import Path

_METHODS = {
    "authenticate": "authenticate",
    "logout": "logout",
    "new": "session/new",
    "load": "session/load",
    "list": "session/list",
    "delete": "session/delete",
    "resume": "session/resume",
    "close": "session/close",
    "set_mode": "session/set_mode",
    "set_config_option": "session/set_config_option",
    "prompt": "session/prompt",
    "cancel": "session/cancel",
}
_SESSION_METHODS = frozenset(_METHODS) - {"authenticate", "logout", "new", "list"}
_CHILD_FIELDS = ("title", "description", "state", "capabilities", "cwd", "additionalDirectories", "_meta")
_PROMPT_CAPABILITIES = {"image": "image", "audio": "audio", "resource": "embeddedContext"}


def _record(value):
    return value if isinstance(value, dict) else {}


def _id(value):
    return isinstance(value, str) and bool(value)


def _absolute(value):
    return _id(value) and "\x00" not in value and Path(value).is_absolute()


def _strings(values):
    return isinstance(values, list) and all(isinstance(value, str) and "\x00" not in value for value in values)


def _named_values(values):
    return isinstance(values, list) and all(
        isinstance(value, dict) and _id(value.get("name")) and isinstance(value.get("value"), str)
        for value in values)


def _ignore(_result, _error):
    pass


class SessionRpc:
    def __init__(self, client, initialize_result, cwd):
        self.client = client
        self.cwd = str(cwd)
        self.capabilities = _record(initialize_result.get("agentCapabilities"))
        self.session_capabilities = _record(self.capabilities.get("sessionCapabilities"))
        self.prompt_capabilities = _record(self.capabilities.get("promptCapabilities"))
        self.mcp_capabilities = _record(self.capabilities.get("mcpCapabilities"))
        methods = initialize_result.get("authMethods")
        self.auth_methods = [method for method in methods
                             if isinstance(method, dict) and _id(method.get("id"))
                             and isinstance(method.get("name"), str)] if isinstance(methods, list) else []
        self.subagents = {}

    def supported(self, action, *, session_id=None):
        if session_id in self.subagents and action in _SESSION_METHODS:
            capabilities = _record(self.subagents[session_id].get("capabilities"))
            return action == "cancel" and isinstance(capabilities.get("cancel"), dict)
        if action == "load":
            return self.capabilities.get("loadSession") is True
        if action in {"list", "delete", "resume", "close"}:
            return isinstance(self.session_capabilities.get(action), dict)
        if action == "logout":
            return isinstance(_record(self.capabilities.get("auth")).get("logout"), dict)
        if action == "authenticate":
            return any(method.get("type", "agent") == "agent" for method in self.auth_methods)
        return action in _METHODS

    def terminal_auth(self, method_id):
        for method in self.auth_methods:
            if method["id"] != method_id or method.get("type") != "terminal":
                continue
            args = method.get("args", [])
            env = method.get("env", {})
            if (_strings(args)
                    and isinstance(env, dict) and all(_id(key) and "=" not in key and "\x00" not in key
                    and isinstance(value, str) and "\x00" not in value for key, value in env.items())):
                return {"args": args, "env": env}
        return None

    def request(self, action, params, callback=None, *, session_id=None, timeout=15000):
        callback = callback or _ignore
        if params is not None and not isinstance(params, dict):
            callback(None, {"code": -32602, "message": "Invalid request parameters"})
            return False
        payload = dict(params or {})
        target = session_id if session_id is not None else payload.get("sessionId")
        if target is not None and not _id(target):
            callback(None, {"code": -32602, "message": "Invalid session identifier"})
            return False
        if not self.supported(action, session_id=target):
            callback(None, {"code": -32601, "message": "Method not supported"})
            return False
        if action in _SESSION_METHODS:
            payload["sessionId"] = target
        if action in {"new", "load", "resume"}:
            payload.setdefault("cwd", self.cwd)
            payload.setdefault("mcpServers", [])
        if error := self._validate(action, payload):
            callback(None, {"code": -32602, "message": error})
            return False
        if action == "cancel":
            sent = self.client.notify(_METHODS[action], payload)
            if sent is False:
                callback(None, {"code": -1, "message": "Connection closed"})
                return False
            callback({}, None)
            return True
        return self.client.request(_METHODS[action], payload, callback, timeout=timeout) is not None

    def _validate(self, action, payload):
        if action in _SESSION_METHODS and not _id(payload.get("sessionId")):
            return "Missing session identifier"
        if action in {"new", "load", "resume"}:
            return self._validate_workspace(payload)
        if action == "authenticate" and not any(
                method["id"] == payload.get("methodId") and method.get("type", "agent") == "agent"
                for method in self.auth_methods):
            return "Unknown authentication method"
        if action == "list":
            if payload.get("cwd") is not None and not _absolute(payload["cwd"]):
                return "Invalid working directory"
            if payload.get("cursor") is not None and not isinstance(payload["cursor"], str):
                return "Invalid pagination cursor"
        if action == "set_mode" and not _id(payload.get("modeId")):
            return "Missing mode identifier"
        if action == "set_config_option":
            value = payload.get("value")
            if not _id(payload.get("configId")) or not (_id(value) or type(value) is bool):
                return "Invalid configuration value"
            if type(value) is bool:
                payload["type"] = "boolean"
            elif payload.get("type") == "boolean":
                return "Invalid boolean configuration value"
        if action == "prompt":
            prompt = payload.get("prompt")
            if not isinstance(prompt, list) or not prompt:
                return "Missing prompt blocks"
            for block in prompt:
                if not self._prompt_allowed(_record(block)):
                    return "Unsupported prompt content"
        return None

    def _prompt_allowed(self, block):
        kind = block.get("type")
        if kind == "text":
            return isinstance(block.get("text"), str)
        if kind == "resource_link":
            return _id(block.get("name")) and _id(block.get("uri"))
        if not isinstance(kind, str) or self.prompt_capabilities.get(_PROMPT_CAPABILITIES.get(kind)) is not True:
            return False
        if kind == "resource":
            resource = _record(block.get("resource"))
            return _id(resource.get("uri")) and (
                isinstance(resource.get("text"), str) or isinstance(resource.get("blob"), str))
        return _id(block.get("mimeType")) and isinstance(block.get("data"), str)

    def _validate_workspace(self, payload):
        if not _absolute(payload.get("cwd")):
            return "Invalid working directory"
        if "additionalDirectories" in payload:
            directories = payload["additionalDirectories"]
            if not (isinstance(self.session_capabilities.get("additionalDirectories"), dict)
                    and isinstance(directories, list) and all(_absolute(path) for path in directories)):
                return "Invalid additional workspace directories"
        if payload.get("systemPrompt") is not None:
            capability = self.session_capabilities.get("systemPrompt")
            prompt = _record(payload["systemPrompt"])
            mode = prompt.get("mode")
            content = prompt.get("content")
            can_override = isinstance(_record(_record(capability).get("mode")).get("override"), dict)
            if not (isinstance(capability, dict) and (mode == "append" or mode == "override" and can_override)
                    and isinstance(content, list) and content and all(
                    _record(block).get("type") == "text" and isinstance(block.get("text"), str)
                    for block in content)):
                return "Unsupported system prompt"
        servers = payload["mcpServers"]
        if not isinstance(servers, list):
            return "Invalid MCP server list"
        for entry in servers:
            server = _record(entry)
            kind = server.get("type", "stdio")
            if not _id(server.get("name")):
                return "Missing MCP server name"
            if (kind == "stdio" and _absolute(server.get("command"))
                    and _strings(server.get("args")) and _named_values(server.get("env"))):
                continue
            if (kind in ("http", "sse") and self.mcp_capabilities.get(kind) is True
                    and _id(server.get("url")) and _named_values(server.get("headers"))):
                continue
            return "Unsupported MCP server transport"
        return None

    def update_subagent(self, parent_id, update):
        child_id = update.get("sessionId")
        if not _id(parent_id) or not _id(child_id) or self.accepts_update(child_id, parent_id):
            return False
        child = self.subagents.setdefault(child_id, {"sessionId": child_id, "parentId": parent_id})
        if child["parentId"] != parent_id:
            return False
        child.update({key: update[key] for key in _CHILD_FIELDS if key in update})
        return True

    def accepts_update(self, root_id, update_id):
        if not _id(root_id) or not _id(update_id):
            return False
        while update_id != root_id and update_id in self.subagents:
            update_id = self.subagents[update_id]["parentId"]
        return update_id == root_id
