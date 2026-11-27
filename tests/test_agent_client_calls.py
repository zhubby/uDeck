"""[INPUT]: 依赖 ACP 客户端、Qt 事件循环与测试目录。
[OUTPUT]: 验证文件、终端、结构化表单与请求取消。
[POS]: ACP 客户端方法的协议回归。
[PROTOCOL]: Update this header on change, then check AGENTS.md
"""

import sys

from PySide6.QtTest import QTest

from udeck.apps.agent.acp import AcpClient


def make_client(tmp_path, monkeypatch):
    client = AcpClient([sys.executable], tmp_path)
    replies = {}
    monkeypatch.setattr(client, "_send", lambda packet: not replies.update({packet["id"]: packet}))
    client.set_session_roots("s", [tmp_path])
    return client, replies


def send(client, request_id, method, **params):
    client._message({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})


def test_acp_files_use_selected_roots_and_explicit_write(qt_application, tmp_path, monkeypatch):
    client, replies = make_client(tmp_path, monkeypatch)
    approvals = []
    client.client_action.connect(lambda *args: approvals.append(args))
    target = tmp_path / "example.txt"
    target.write_text("first\n第二行\nlast\n")
    link = tmp_path / "linked.txt"
    link.symlink_to(target)
    try:
        send(client, 1, "fs/read_text_file", sessionId="s", path=str(target), line=2, limit=1)
        assert replies[1]["result"] == {"content": "第二行\n"}
        send(client, 2, "fs/read_text_file", sessionId="s", path=str(link))
        assert "error" in replies[2]
        send(client, 3, "fs/read_text_file", sessionId="unknown", path=str(target))
        assert "error" in replies[3]
        send(client, 4, "fs/write_text_file", sessionId="s", path=str(target), content="经过批准\n")
        assert approvals[0][:2] == (4, "fs/write_text_file")
        assert 4 not in replies and "first" in target.read_text()
        assert client.respond_action(4, "accept")
        assert replies[4]["result"] == {}
        assert target.read_text() == "经过批准\n"
        send(client, 5, "fs/write_text_file", sessionId="s", path=str(target), content="取消")
        client._message({"jsonrpc": "2.0", "method": "$/cancel_request", "params": {"requestId": 5}})
        assert replies[5]["error"]["code"] == -32800
        assert not client.respond_action(5, "accept")
        assert target.read_text() == "经过批准\n"
    finally:
        client.close()


def test_acp_terminal_lifecycle_and_utf8_boundary(qt_application, tmp_path, monkeypatch):
    client, replies = make_client(tmp_path, monkeypatch)
    try:
        send(client, 1, "terminal/create", sessionId="s", command=sys.executable,
             args=["-c", "print('甲乙丙', end='')"], outputByteLimit=7)
        assert 1 not in replies
        assert client.respond_action(1, "accept")
        for _ in range(200):
            if 1 in replies:
                break
            QTest.qWait(10)
        terminal = replies[1]["result"]["terminalId"]
        send(client, 2, "terminal/wait_for_exit", sessionId="s", terminalId=terminal)
        for _ in range(200):
            if 2 in replies:
                break
            QTest.qWait(10)
        assert replies[2]["result"] == {"exitCode": 0}
        send(client, 3, "terminal/output", sessionId="s", terminalId=terminal)
        assert replies[3]["result"] == {"output": "乙丙", "truncated": True, "exitStatus": {"exitCode": 0}}
        send(client, 4, "terminal/release", sessionId="s", terminalId=terminal)
        assert replies[4]["result"] == {}
        send(client, 5, "terminal/output", sessionId="s", terminalId=terminal)
        assert replies[5]["error"]["code"] == -32002
    finally:
        client.close()


def test_acp_cancelled_terminal_wait_and_kill(qt_application, tmp_path, monkeypatch):
    client, replies = make_client(tmp_path, monkeypatch)
    try:
        send(client, 1, "terminal/create", sessionId="s", command=sys.executable,
             args=["-c", "import time; time.sleep(30)"])
        assert client.respond_action(1, "accept")
        for _ in range(200):
            if 1 in replies:
                break
            QTest.qWait(10)
        terminal = replies[1]["result"]["terminalId"]
        send(client, 2, "terminal/wait_for_exit", sessionId="s", terminalId=terminal)
        client._message({"jsonrpc": "2.0", "method": "$/cancel_request", "params": {"requestId": 2}})
        assert replies[2]["error"]["code"] == -32800
        send(client, 3, "terminal/wait_for_exit", sessionId="s", terminalId=terminal)
        send(client, 4, "terminal/kill", sessionId="s", terminalId=terminal)
        assert replies[4]["result"] == {}
        for _ in range(200):
            if 3 in replies:
                break
            QTest.qWait(10)
        assert replies[3]["result"] == {"signal": "SIGKILL"}
        assert replies[2]["error"]["code"] == -32800
    finally:
        client.close(wait=True)


def test_acp_elicitation_validates_content_and_completion(qt_application, tmp_path, monkeypatch):
    client, replies = make_client(tmp_path, monkeypatch)
    completed = []
    client.elicitation_completed.connect(completed.append)
    try:
        send(client, "form", "elicitation/create", sessionId="s", mode="form", message="Pick values",
             requestedSchema={"type": "object", "required": ["amount", "flags"], "properties": {
                 "amount": {"type": "integer", "minimum": 1},
                 "flags": {"type": "array", "items": {"anyOf": [
                     {"const": "a", "title": "First"}, {"const": "b", "title": "Second"},
                 ]}},
             }})
        assert not client.respond_action("form", "accept", {"amount": False, "flags": ["a"]})
        assert not client.respond_action("form", "accept", {"amount": 1, "flags": ["unknown"]})
        assert client.respond_action("form", "accept", {"amount": 1, "flags": ["a", "b"]})
        assert replies["form"]["result"] == {"action": "accept", "content": {"amount": 1, "flags": ["a", "b"]}}
        send(client, "url", "elicitation/create", sessionId="s", mode="url", message="Continue",
             elicitationId="browser", url="https://example.org/")
        assert client.respond_action("url", "accept")
        assert replies["url"]["result"] == {"action": "accept"}
        client._message({"jsonrpc": "2.0", "method": "elicitation/complete", "params": {"elicitationId": "browser"}})
        assert completed == [{"elicitationId": "browser", "sessionId": "s"}]
    finally:
        client.close()
