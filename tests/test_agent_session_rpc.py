"""[INPUT]: 依赖 ACP v1 会话请求和能力声明。
[OUTPUT]: 验证请求参数、能力门控和子会话操作限制。
[POS]: ACP 出站协议回归。
[PROTOCOL]: Update this header on change, then check AGENTS.md
"""

import pytest

from udeck.apps.agent.session_rpc import SessionRpc


class RecordingClient:
    def __init__(self):
        self.requests = []
        self.notifications = []

    def request(self, method, params, callback, *, timeout):
        self.requests.append((method, params, timeout))
        callback({"method": method}, None)
        return len(self.requests)

    def notify(self, method, params):
        self.notifications.append((method, params))


@pytest.fixture
def rpc(tmp_path):
    return SessionRpc(RecordingClient(), {
        "agentCapabilities": {
            "loadSession": True,
            "sessionCapabilities": {
                "list": {}, "delete": {}, "resume": {}, "close": {}, "additionalDirectories": {},
                "systemPrompt": {"mode": {"override": {}}},
            },
            "auth": {"logout": {}},
            "promptCapabilities": {"image": True, "embeddedContext": True},
            "mcpCapabilities": {"http": True},
        },
        "authMethods": [
            {"id": "oauth", "name": "OAuth"},
            {"id": "cli", "name": "CLI", "type": "terminal", "args": ["login"], "env": {"TERM": "xterm"}},
        ],
    }, tmp_path)


@pytest.mark.parametrize(("action", "params", "session_id", "method", "extra"), [
    ("authenticate", {"methodId": "oauth"}, None, "authenticate", {}),
    ("logout", {}, None, "logout", {}),
    ("new", {}, None, "session/new", {"cwd", "mcpServers"}),
    ("load", {}, "root", "session/load", {"sessionId", "cwd", "mcpServers"}),
    ("list", {"cursor": "page-2"}, None, "session/list", {}),
    ("delete", {}, "root", "session/delete", {"sessionId"}),
    ("resume", {}, "root", "session/resume", {"sessionId", "cwd", "mcpServers"}),
    ("close", {}, "root", "session/close", {"sessionId"}),
    ("set_mode", {"modeId": "ask"}, "root", "session/set_mode", {"sessionId"}),
    ("set_config_option", {"configId": "speed", "value": False}, "root",
     "session/set_config_option", {"sessionId", "type"}),
    ("set_config_option", {"configId": "model", "value": "small"}, "root",
     "session/set_config_option", {"sessionId"}),
    ("prompt", {"prompt": [{"type": "text", "text": "hello"}]}, "root", "session/prompt", {"sessionId"}),
])
def test_builds_agent_requests(rpc, action, params, session_id, method, extra):
    replies = []
    assert rpc.request(action, params, lambda *reply: replies.append(reply), session_id=session_id, timeout=1234)
    sent, payload, timeout = rpc.client.requests.pop()
    assert sent == method
    assert timeout == 1234
    assert payload.keys() == params.keys() | extra
    assert all(payload[key] == value for key, value in params.items())
    if "sessionId" in extra:
        assert payload["sessionId"] == session_id
    if "type" in extra:
        assert payload["type"] == "boolean"
    assert replies == [({"method": method}, None)]


def test_checks_capabilities_before_dispatch(tmp_path):
    client = RecordingClient()
    rpc = SessionRpc(client, {}, tmp_path)
    for action in ("load", "list", "delete", "resume", "close", "authenticate", "logout"):
        assert not rpc.supported(action)
    replies = []
    assert not rpc.request("resume", {}, lambda *reply: replies.append(reply), session_id="root")
    assert replies[0][1]["code"] == -32601
    assert not rpc.request("new", {"additionalDirectories": [str(tmp_path)]})
    assert not rpc.request("new", {"cwd": "relative"})
    assert not rpc.request("new", {"systemPrompt": {"mode": "append", "content": [{"type": "text", "text": "hello"}]}})
    assert not rpc.request("new", {"mcpServers": [{"type": "sse", "name": "test", "url": "https://example.test"}]})
    assert not rpc.request("prompt", {"prompt": [{"type": "image"}]}, session_id="root")
    assert not client.requests


def test_propagates_failed_send(rpc, monkeypatch):
    def fail(method, params, callback, *, timeout):
        callback(None, {"code": -1})

    monkeypatch.setattr(rpc.client, "request", fail)
    responses = []
    assert not rpc.request("new", {}, lambda *reply: responses.append(reply))
    assert responses == [(None, {"code": -1})]


def test_terminal_auth_and_negotiated_session_options(rpc):
    assert rpc.terminal_auth("cli") == {"args": ["login"], "env": {"TERM": "xterm"}}
    assert rpc.terminal_auth("oauth") is None
    assert not rpc.request("authenticate", {"methodId": "cli"})
    params = {
        "mcpServers": [{"type": "http", "name": "test", "url": "https://example.test", "headers": []}],
        "additionalDirectories": [rpc.cwd],
        "systemPrompt": {"mode": "override", "content": [{"type": "text", "text": "hello"}]},
    }
    assert rpc.request("new", params)
    assert rpc.client.requests[0][1] == {**params, "cwd": rpc.cwd}


def test_validates_mcp_and_prompt_shapes(rpc):
    assert not rpc.request("new", {"mcpServers": [{"name": "local", "command": "/usr/bin/test"}]})
    assert rpc.request("new", {"mcpServers": [{
        "name": "local", "command": "/usr/bin/test", "args": ["--help"], "env": [],
    }]})
    assert not rpc.request("new", {"mcpServers": [{
        "type": "http", "name": "remote", "url": "https://example.test", "headers": {},
    }]})
    assert not rpc.request("prompt", {"prompt": [{"type": "image"}]}, session_id="root")
    assert not rpc.request("prompt", {"prompt": [{"type": "resource", "resource": {}}]}, session_id="root")
    assert rpc.request("prompt", {"prompt": [
        {"type": "resource_link", "name": "context", "uri": "file:///tmp/example"},
        {"type": "resource", "resource": {"uri": "file:///tmp/example", "text": ""}},
        {"type": "image", "data": "AA==", "mimeType": "image/png"},
    ]}, session_id="root")


def test_subagent_patch_and_cancel(rpc):
    assert rpc.update_subagent("root", {"sessionId": "child", "title": "Their task", "capabilities": {"cancel": {}}})
    assert rpc.update_subagent("child", {"sessionId": "grandchild"})
    assert not rpc.update_subagent("grandchild", {"sessionId": "root"})
    assert not rpc.update_subagent("root", {"sessionId": "grandchild"})
    assert rpc.accepts_update("root", "grandchild")
    assert not rpc.accepts_update("another-root", "grandchild")
    assert not rpc.request("prompt", {"prompt": [{"type": "text", "text": "hello"}]}, session_id="child")
    assert not rpc.request("delete", {}, session_id="child")
    assert rpc.request("cancel", {}, session_id="child")
    assert rpc.client.notifications == [("session/cancel", {"sessionId": "child"})]
    assert rpc.update_subagent("root", {"sessionId": "child", "capabilities": None})
    assert rpc.subagents["child"]["title"] == "Their task"
    assert not rpc.request("cancel", {}, session_id="child")
