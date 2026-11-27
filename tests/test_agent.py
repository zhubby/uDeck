"""[INPUT]: 依赖本地模拟 Agent、Qt 事件循环及临时状态目录。
[OUTPUT]: 验证 ACP 往返、权限、安装事务、会话按键和回复渲染。
[POS]: Agent 协议与安装边界测试。
[PROTOCOL]: Update this header on change, then check AGENTS.md
"""

import base64
import hashlib
import io
import sys
import tarfile
import textwrap
import time
from pathlib import Path

import pytest
from PySide6.QtCore import QBuffer, QCoreApplication, QIODevice, QPointF, Qt, QUrl
from PySide6.QtGui import QImage, QInputMethodEvent
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickItem
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest
from shiboken6 import delete

from udeck.apps.agent import catalog, install
from udeck.apps.agent.connection import load_profile, save_profile
from udeck.apps.agent.controller import AgentController
from udeck.apps.agent.conversation import Conversation
from udeck.apps.agent.sessions import SessionStore
from udeck.i18n import Msg, tr
from udeck.icons import IconProvider

_AGENT = """
import json
import sys

def emit(message):
    packet = json.dumps({"jsonrpc": "2.0", **message})
    sys.stdout.write(packet[:16])
    sys.stdout.flush()
    print(packet[16:], flush=True)

for row in sys.stdin:
    message = json.loads(row)
    method = message.get("method")
    if method == "initialize":
        result = {"protocolVersion": 1, "agentCapabilities": {"loadSession": True}}
    elif method == "session/new":
        result = {"sessionId": "remote"}
    elif method == "session/load":
        emit({"method": "session/update", "params": {"sessionId": "remote",
              "update": {"sessionUpdate": "agent_message_chunk", "content": {"type": "text", "text": "replay"}}}})
        result = {}
    elif method == "session/prompt":
        prompt = message["params"]["prompt"][0]["text"]
        prompt_id = message["id"]
        emit({"method": "session/update", "params": {"sessionId": "remote",
              "update": {"sessionUpdate": "agent_message_chunk", "content": {"type": "text", "text": "你好"}}}})
        if prompt == "permission":
            emit({"method": "session/request_permission", "id": "approve", "params": {
                  "sessionId": "remote", "toolCall": {"title": "Read"},
                  "options": [{"optionId": "once", "name": "Allow once", "kind": "allow_once"}]}})
        continue
    elif method == "session/cancel":
        emit({"id": prompt_id, "result": {"stopReason": "cancelled"}})
        continue
    elif message.get("id") == "approve":
        assert message["result"]["outcome"]["optionId"] == "once"
        emit({"id": prompt_id, "result": {"stopReason": "end_turn"}})
        continue
    else:
        continue
    emit({"id": message["id"], "result": result})
"""


def wait_until(predicate):
    deadline = time.monotonic() + 3
    while not predicate():
        if time.monotonic() >= deadline:
            pytest.fail("Qt event did not arrive")
        QTest.qWait(15)


def test_connection_profile_is_private_and_used_by_claude_launch(qt_application, tmp_path):
    controller = AgentController(tmp_path, tmp_path / "settings.json")
    controller._show_provider_settings("claude")
    profile = {"url": "https://gateway.example/anthropic", "model": "example-model",
               "key": "fixture-secret", "auth": "bearer"}
    try:
        controller.configureProvider("claude")
        controller.choose(0)
        controller.submit(profile["url"])
        controller.choose(1)
        controller.submit(profile["model"])
        controller.choose(2)
        controller.setDraft(profile["key"])
        assert profile["key"] not in controller.snapshotJson
        assert profile["key"] not in controller.viewSnapshotJson
        controller.dispatch("accept")
        controller.choose(3)
        controller.choose(1)
        controller.choose(4)
        assert not controller.menus
        assert load_profile(controller.root, "claude") == profile
        assert (controller.root / "claude-connection.json").stat().st_mode & 0o777 == 0o600
        folder = "c" * 32
        binary = controller.root / "versions" / folder / "bin" / "claude-agent-acp"
        binary.parent.mkdir(parents=True)
        binary.touch()
        item = {"folder": folder, "version": "0.113.0"}
        _, env = install.command(controller.root, "claude", item=item, connection=True)
        assert env["ANTHROPIC_BASE_URL"] == profile["url"]
        assert env["ANTHROPIC_MODEL"] == profile["model"]
        assert env["ANTHROPIC_AUTH_TOKEN"] == profile["key"]
        assert profile["key"] not in controller.snapshotJson
        with pytest.raises(ValueError):
            save_profile(controller.root, "claude", {**profile, "url": "https://user:secret@example.com"})
        assert load_profile(controller.root, "claude") == profile
    finally:
        controller.close()


def test_structured_updates_batch_and_preserve_history(qt_application, tmp_path):
    chat = Conversation(SessionStore(tmp_path))
    chat.key = chat.store.create("codex", str(tmp_path), "Reply types", "remote")
    chat.state = "sending"

    def event(kind, **payload):
        chat.events.append({"sessionUpdate": kind, **payload})

    def chunk(kind, text):
        event(kind, content={"type": "text", "text": text})

    try:
        chunk("user_message_chunk", "echo")
        chunk("agent_thought_chunk", "思考")
        chunk("agent_message_chunk", "开始")
        event("tool_call", toolCallId="tool", title="检查")
        event("plan_update", plan={"planId": "p", "type": "items", "entries": [{"content": "核对"}]})
        event("notice", title="通知")
        event("tool_call_update", toolCallId="tool", status="completed", content=[
            {"type": "diff", "path": "test.txt", "oldText": "old", "newText": "new"},
            {"type": "terminal", "terminalId": "terminal-1"},
            {"type": "session", "sessionId": "child"},
            {"type": "content", "content": {"type": "resource_link", "uri": "file:///test.txt"}},
        ])
        event("compaction_summary_chunk", compactionId="c", content={"type": "text", "text": "摘要"})
        event("compaction_update", compactionId="c", status="completed")
        event("subagent_update", sessionId="child", title="助手")
        event("session_message", messageId="m", senderSessionId="child", recipientSessionId="remote")
        event("session_message_chunk", messageId="m", content={"type": "text", "text": "已检查"})
        event("plan", entries=[{"content": "传统计划", "status": "pending", "priority": "high"}])
        event("available_commands_update", availableCommands=[{"name": "help", "description": "Help"}])
        event("current_mode_update", currentModeId="review")
        event("config_option_update", configOptions=[{
            "id": "enabled", "name": "Enabled", "type": "boolean", "currentValue": True,
        }])
        event("session_info_update", title="协议回归")
        event("usage_update", used=100, size=1000, cost={"amount": 0.02, "currency": "USD"})
        chunk("agent_message_chunk", "最终")
        chunk("agent_message_chunk", "结果")
        chat._flush()
        rows = chat.model.rows
        assert [row["kind"] for row in rows] == [
            "user", "thought", "agent", "tool", "plan", "notice", "compaction", "subagent",
            "subagent", "plan", "commands", "mode", "config", "session_info", "usage", "agent",
        ]
        assert rows[3]["status"] == "completed"
        assert [block["type"] for block in rows[3]["blocks"]] == ["diff", "terminal", "session", "resource_link"]
        assert rows[3]["blocks"][0]["newText"] == "new"
        assert rows[6]["blocks"][0]["text"] == "摘要"
        assert rows[8]["blocks"][0]["text"] == "已检查"
        assert rows[8]["text"] == "child → remote"
        assert rows[10]["blocks"][0]["arguments"]["name"] == "help"
        assert rows[11]["text"] == "review"
        assert rows[12]["blocks"][0]["arguments"]["value"] is False
        assert rows[13]["text"] == "协议回归"
        assert rows[14]["blocks"] == [{"type": "usage", "used": 100, "size": 1000}]
        assert rows[14]["detail"] == "0.02 USD"
        assert rows[-1]["streaming"] and rows[-1]["text"] == "最终结果"
        chat._save()
        persisted = chat.store.messages(chat.key)
        assert "streaming" not in persisted[-1]
        assert all(row["kind"] != "notice" for row in persisted)
        event("plan_removed", planId="p")
        chat._completed({"stopReason": "end_turn"}, None)
        assert not rows[-1].get("streaming")
        saved = chat.store.messages(chat.key)
        assert saved[:-1] == [row for row in persisted if row.get("entity") != ["plan", "p"]]
        assert saved[-1]["kind"] == "result" and saved[-1]["status"] == "end_turn"
    finally:
        chat.close()


def test_conversation_permission_stop_and_reopen(qt_application, tmp_path):
    script = tmp_path / "acp.py"
    script.write_text(textwrap.dedent(_AGENT))
    directory = tmp_path / "项目 directory"
    directory.mkdir()
    args = [sys.executable, str(script)]
    with_store = Conversation(SessionStore(tmp_path))
    try:
        with_store.open("codex", directory, args, {})
        wait_until(lambda: with_store.state == "ready")
        assert with_store.send("permission")
        assert not with_store.send("duplicate")
        wait_until(lambda: bool(with_store.permissions))
        with_store.respond("not-an-option")
        assert with_store.permissions
        with_store.respond("once")
        wait_until(lambda: with_store.state == "ready")
        assert with_store.model.rows[-3]["text"] == "你好"
        assert with_store.model.rows[-2]["kind"] == "permission"
        assert with_store.model.rows[-1]["status"] == "end_turn"
        assert with_store.send("stop")
        with_store.stop()
        wait_until(lambda: with_store.state == "ready")
        assert with_store.error == "stopped"
        assert not with_store.model.rows[-2].get("streaming")
        session = with_store.store.list()[0]
        assert session["directory"] == str(directory)
        assert with_store.store.messages(session["id"])[-2]["text"] == "你好"
        assert with_store.store.messages(session["id"])[-1]["status"] == "cancelled"
        before = len(with_store.store.messages(session["id"]))
        with_store.select(session)
        with_store.open("codex", directory, args, {}, resume=session)
        wait_until(lambda: with_store.state == "ready")
        assert len(with_store.model.rows) == before
    finally:
        with_store.close()


_FULL_AGENT = """
import json
import sys

authenticated = False

def emit(**packet):
    print(json.dumps({"jsonrpc": "2.0", **packet}), flush=True)

def update(kind, session="root", **fields):
    emit(method="session/update", params={"sessionId": session, "update": {"sessionUpdate": kind, **fields}})

for line in sys.stdin:
    packet = json.loads(line)
    method = packet.get("method")
    params = packet.get("params", {})
    identifier = packet.get("id")
    if method == "initialize":
        caps = params["clientCapabilities"]
        assert caps["fs"]["readTextFile"] and caps["terminal"] and "subagents" in caps
        result = {"protocolVersion": 1, "authMethods": [{"id": "oauth", "name": "Fixture authentication"}],
                  "agentCapabilities": {"loadSession": True, "sessionCapabilities": {"list": {}, "close": {}}}}
    elif method == "session/new" and not authenticated:
        emit(id=identifier, error={"code": -32000, "message": "Authentication required"})
        continue
    elif method == "authenticate":
        assert params["methodId"] == "oauth"
        authenticated = True
        result = {}
    elif method == "session/new":
        update("available_commands_update", availableCommands=[{"name": "review", "description": "Review"}])
        result = {"sessionId": "root", "modes": {"currentModeId": "review", "availableModes": [
            {"id": "review", "name": "Review"}, {"id": "edit", "name": "Edit"}]}}
    elif method == "session/load":
        session = params["sessionId"]
        update("user_message_chunk", session=session, content={"type": "text", "text": "Remote prompt"})
        update("agent_message_chunk", session=session, content={"type": "text", "text": "Remote answer"})
        update("session_message_chunk", session=session, messageId="inter-session",
               content={"type": "text", "text": "Coordinator update"})
        update("compaction_summary_chunk", session=session, compactionId="summary",
               content={"type": "text", "text": "Context summary"})
        update("compaction_update", session=session, compactionId="summary", status="completed")
        if len(sys.argv) > 2:
            update("user_message_chunk", session=session, content={"type": "text", "text": "New prompt"})
            update("agent_message_chunk", session=session, content={"type": "text", "text": "New answer"})
        result = {}
    elif method == "session/set_mode":
        assert params["modeId"] == "edit" and params["sessionId"] == "root"
        result = {}
    elif method == "session/set_config_option":
        assert params["configId"] == "preview" and params["value"] is False
        result = {"configOptions": [{"type": "boolean", "id": "preview", "name": "Preview",
                                     "currentValue": False}]}
    elif method == "session/prompt":
        prompt = params["prompt"][0]["text"]
        update("user_message_chunk", content={"type": "text", "text": prompt[:2]})
        update("usage_update", used=10, size=100)
        update("user_message_chunk", content={"type": "text", "text": prompt[2:]})
        update("subagent_update", sessionId="child", title="Child")
        update("agent_message_chunk", session="child", content={"type": "text", "text": "Child reply"})
        update("agent_message_chunk", content={"type": "text", "text": "Parent reply"})
        if prompt in ("form", "cancel form"):
            pending_prompt = identifier
            pending_form = prompt
            emit(id="form", method="elicitation/create", params={
                "sessionId": "root", "mode": "form", "message": "Confirm preview",
                "requestedSchema": {"type": "object", "properties": {"preview": {"type": "boolean"}},
                                    "required": ["preview"]},
            })
            continue
        if prompt == "url":
            pending_prompt = identifier
            emit(id="url", method="elicitation/create", params={
                "sessionId": "root", "mode": "url", "message": "Continue in browser",
                "elicitationId": "browser", "url": "https://example.org/",
            })
            continue
        result = {"stopReason": prompt}
    elif identifier == "form":
        if pending_form == "cancel form":
            assert packet["result"] == {"action": "cancel"}
            emit(id=pending_prompt, result={"stopReason": "cancelled"})
            continue
        assert packet["result"] == {"action": "accept", "content": {"preview": False}}
        emit(id=pending_prompt, result={"stopReason": "end_turn"})
        continue
    elif identifier == "url":
        assert packet["result"] == {"action": "accept"}
        emit(method="elicitation/complete", params={"elicitationId": "browser"})
        emit(id=pending_prompt, result={"stopReason": "end_turn"})
        continue
    elif method == "session/cancel":
        assert params["sessionId"] == "root"
        continue
    elif method == "session/list":
        result = {"sessions": [{"sessionId": "archived", "cwd": sys.argv[1], "title": "Archived"}],
                  "nextCursor": "next"}
    elif method == "session/close":
        result = {}
    else:
        continue
    emit(id=identifier, result=result)
"""


def test_acp_wire_auth_metadata_child_results_and_remote_history(qt_application, tmp_path):
    script = tmp_path / "protocol.py"
    script.write_text(_FULL_AGENT, encoding="utf-8")
    args = [sys.executable, str(script), str(tmp_path)]
    chat = Conversation(SessionStore(tmp_path))
    try:
        chat.open("codex", tmp_path, args, {})
        wait_until(lambda: chat.state == "auth")
        assert chat.model.rows[-1]["blocks"][0]["arguments"] == {"methodId": "oauth"}
        chat.session_action("authenticate", {"methodId": "oauth"})
        wait_until(lambda: chat.state == "ready")
        mode = next(row for row in chat.model.rows if row["kind"] == "mode")
        commands = next(row for row in chat.model.rows if row["kind"] == "commands")
        assert commands["blocks"][0]["text"] == "/review"
        chat.session_action("set_mode", {"modeId": "edit"})
        wait_until(lambda: mode["text"] == "Edit")
        for reason in ("end_turn", "max_tokens", "max_turn_requests", "refusal", "cancelled"):
            assert chat.send(reason)
            wait_until(lambda: chat.state == "ready")
            assert chat.model.rows[-1]["kind"] == "result"
            assert chat.model.rows[-1]["status"] == reason
        assert [row["text"] for row in chat.model.rows if row["kind"] == "user"] == [
            "end_turn", "max_tokens", "max_turn_requests", "refusal", "cancelled",
        ]
        assert any(row.get("origin") == "Child" and row.get("text") == "Child reply" for row in chat.model.rows)
        assert len([row for row in chat.model.rows if row["kind"] == "usage"]) == 1
        assert chat.send("form")
        wait_until(lambda: bool(chat.client_requests))
        token = next(iter(chat.client_requests))
        assert not chat.respond_request(token, "accept", {})
        assert chat.respond_request(token, "accept", {"preview": False})
        wait_until(lambda: chat.state == "ready")
        assert next(row for row in chat.model.rows if row["kind"] == "elicitation")["status"] == "completed"
        assert chat.send("cancel form")
        wait_until(lambda: bool(chat.client_requests))
        chat.stop()
        wait_until(lambda: chat.state == "ready")
        assert not chat.client_requests
        assert chat.model.rows[-1]["status"] == "cancelled"
        assert chat.send("url")
        wait_until(lambda: bool(chat.client_requests))
        token = next(iter(chat.client_requests))
        card = next(row for row in chat.model.rows if row.get("request") == token)
        assert chat.respond_request(token, "accept")
        assert card["status"] == "in_progress"
        wait_until(lambda: chat.state == "ready")
        assert card["status"] == "completed"
        assert card["detail"] == "https://example.org/"
        chat.session_action("list", {})
        wait_until(lambda: chat.model.rows[-1]["kind"] == "remote_sessions")
        assert [row["action"] for row in chat.model.rows[-1]["blocks"]] == ["open_remote", "remote_list"]
        chat.session_action("close", {})
        wait_until(lambda: chat.state == "idle")
        entry = {"id": chat.store.create("codex", str(tmp_path), "Archived", "archived"), "agent": "codex",
                 "directory": str(tmp_path), "remote": "archived"}
        chat.select(entry)
        chat.open("codex", tmp_path, args, {}, resume=entry)
        wait_until(lambda: chat.state == "ready")
        assert [row["text"] for row in chat.model.rows if row["kind"] in {"user", "agent"}] == [
            "Remote prompt", "Remote answer",
        ]
        chat.open("codex", tmp_path, [*args, "updated"], {}, resume=entry)
        wait_until(lambda: chat.state == "ready")
        assert [row["text"] for row in chat.model.rows if row["kind"] in {"user", "agent"}] == [
            "Remote prompt", "Remote answer", "New prompt", "New answer",
        ]
        assert [row["blocks"][0]["text"] for row in chat.model.rows if row["kind"] in {"subagent", "compaction"}] == [
            "Coordinator update", "Context summary",
        ]
    finally:
        chat.close()


def test_binary_install_rollback_preserves_active_on_bad_archive(qt_application, tmp_path, monkeypatch):
    monkeypatch.setattr(install, "supported_platform", lambda: True)
    distribution = {"version": "1.0.0", "url": "fixture", "sha256": ""}
    monkeypatch.setattr(catalog, "available", lambda _key: distribution)
    archive = tmp_path / "fixture.tar.gz"
    script = f"#!{sys.executable}\n" + textwrap.dedent(_AGENT)
    with tarfile.open(archive, "w:gz") as tar:
        member = tarfile.TarInfo("test-folder/opencode")
        member.mode = 0o755
        payload = script.encode()
        member.size = len(payload)
        tar.addfile(member, io.BytesIO(payload))
    checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
    distribution["sha256"] = checksum

    class Response(io.BytesIO):
        pass

    monkeypatch.setattr(catalog, "open_url", lambda _url, _hosts: Response(archive.read_bytes()))

    installer = install.Installer(tmp_path / "managed")
    try:
        first = installer._worker("install", "opencode")
        assert install.installed(installer.root, "opencode") == "1.0.0"
        distribution.update(version="1.0.1", sha256="0" * 64)
        with pytest.raises(install.InstallError, match="checksum"):
            installer._worker("install", "opencode")
        assert install.state(installer.root, "opencode")["active"] == first
        distribution["sha256"] = checksum
        second = installer._worker("install", "opencode")
        assert second["version"] == "1.0.1"
        assert installer._worker("rollback", "opencode") == first
        assert install.installed(installer.root, "opencode") == "1.0.0"
        assert len(list((installer.root / "versions").iterdir())) == 2
    finally:
        installer.close()


def test_archive_rejects_paths_outside_staging(qt_application, tmp_path):
    archive = tmp_path / "unsafe.tar"
    with tarfile.open(archive, "w") as tar:
        member = tarfile.TarInfo("../bad")
        member.size = 1
        tar.addfile(member, io.BytesIO(b"x"))
    destination = tmp_path / "destination"
    destination.mkdir()
    installer = install.Installer(tmp_path)
    try:
        with pytest.raises(tarfile.TarError):
            installer._unpack(archive, destination)
        assert not (tmp_path / "bad").exists()
    finally:
        installer.close()


def test_agent_window_shows_providers_and_live_transcript(qt_application, tmp_path):
    QQuickStyle.setStyle("Basic")
    controller = AgentController(tmp_path, tmp_path / "settings.json")
    controller.isolated = True
    engine = QQmlApplicationEngine()
    engine.addImageProvider("desktop", IconProvider())
    engine.rootContext().setContextProperty("controller", controller)
    engine.rootContext().setContextProperty("windowed", True)
    errors = []
    engine.warnings.connect(lambda warnings: errors.extend(warning.toString() for warning in warnings))
    source = Path(install.__file__).resolve().parents[1] / "common/qml/Main.qml"
    try:
        engine.load(QUrl.fromLocalFile(str(source)))
        assert engine.rootObjects(), errors
        window = engine.rootObjects()[0]
        controller.window = window
        controller.start()
        window.setWidth(960)
        window.setHeight(600)
        for name in ("appHeader", "appFooter"):
            assert window.findChild(QQuickItem, name).isVisible()
        app_tabs = window.findChild(QQuickItem, "appTabs")
        assert not app_tabs.isVisible()
        content = window.findChild(QQuickItem, "appPageContent")
        wait_until(lambda: content.height() == 600 - 66 - 62)
        controller.dispatch("next-tab")
        assert controller.page == "agent"
        settings = window.findChild(QQuickItem, "appSettings")
        position = settings.mapToItem(window.contentItem(), QPointF(settings.width() / 2, settings.height() / 2))
        QTest.mouseClick(window, Qt.MouseButton.LeftButton, pos=position.toPoint())
        assert controller.menus[-1]["title"] == tr(Msg.SETTINGS)
        assert controller.menus[-1]["options"][0]["title"] == tr(Msg.AGENT_MANAGE)
        controller.choose(0)
        assert controller.page == "agent-settings"

        def provider_visible():
            items = [window.contentItem()]
            while items:
                item = items.pop()
                if item.objectName() == "agentProvider-pi":
                    return item.isVisible()
                items.extend(item.childItems())
            return False

        wait_until(provider_visible)
        details = window.findChild(QQuickItem, "agentManageDetails")
        assert details and details.width() > 350
        assert details.mapToItem(window.contentItem(), QPointF(details.width(), 0)).x() <= window.width()
        controller.dispatch("down")
        controller.dispatch("accept")
        assert controller.menus[-1]["title"] == "Claude Code"
        controller.dispatch("back")
        assert controller.page == "agent-settings"
        controller.dispatch("back")
        assert controller.page == "agent"
        controller.newSession()
        assert controller.page == "agent-settings"
        controller.dispatch("back")
        script = tmp_path / "fixture.py"
        script.write_text(textwrap.dedent(_AGENT))
        controller.chat.open("codex", tmp_path, [sys.executable, str(script)], {})
        wait_until(lambda: controller.chat.state == "ready")
        assert controller.sendPrompt("permission")
        wait_until(lambda: bool(controller.chat.permissions))
        controller.chat.respond("once")
        wait_until(lambda: controller.chat.state == "ready")
        transcript = window.findChild(QQuickItem, "agentTranscript")
        wait_until(lambda: transcript.property("count") == 4)
        assert transcript.height() >= 260
        controller.chat.model.reset([
            {"kind": "user", "text": "Check the project", "status": ""},
            {"kind": "tool", "text": "Read file", "status": "completed", "detail": "pyproject.toml"},
            {"kind": "agent", "text": "A reply with enough lines to scroll.\n" * 70, "status": ""},
        ])
        wait_until(lambda: transcript.property("follow") and transcript.property("atYEnd")
                   and transcript.property("contentY") > transcript.property("originY") + transcript.height())
        tail = transcript.property("contentY")
        controller.dispatch("up")
        wait_until(lambda: transcript.property("contentY") < tail - 1)
        assert transcript.property("readIndex") == 2
        for _ in range(16):
            if transcript.property("readIndex") == 1:
                break
            controller.dispatch("up")
        assert transcript.property("readIndex") == 1
        wait_until(lambda: transcript.property("canExpand"))
        controller.dispatch("accept")
        assert transcript.property("readItem").property("expanded")
        controller.dispatch("left")
        wait_until(lambda: transcript.property("follow") and transcript.property("atYEnd"))
        assert transcript.property("readIndex") == -1
        composer_bar = window.findChild(QQuickItem, "agentComposerBar")
        prompt = window.findChild(QQuickItem, "agentPrompt")
        send = window.findChild(QQuickItem, "agentComposerAction")
        assert send.parentItem() == composer_bar
        assert 0 < send.x() < send.x() + send.width() < composer_bar.width()
        assert not send.isEnabled()
        line_height = composer_bar.height()
        controller.dispatch("right")
        wait_until(prompt.hasActiveFocus)
        assert composer_bar.height() == line_height
        controller.dispatch("next-tab")
        assert controller.page == "agent"
        controller.dispatch("back")
        wait_until(lambda: not prompt.hasActiveFocus())
        prompt.setProperty("text", "Draft survives settings")
        controller.dispatch("up")
        wait_until(lambda: transcript.property("readIndex") >= 0)
        reading_index = transcript.property("readIndex")
        controller.command("settings")
        controller.choose(0)
        controller.dispatch("back")
        assert controller.page == "agent"
        assert transcript.property("readIndex") == reading_index
        assert prompt.property("text") == "Draft survives settings"
        prompt.setProperty("text", "")
        controller.dispatch("context")
        assert controller.menus[-1]["title"] == tr(Msg.AGENT_HISTORY)
        controller.dispatch("back")
        controller.dispatch("right")
        wait_until(prompt.hasActiveFocus)
        QCoreApplication.sendEvent(prompt, QInputMethodEvent("ni", []))
        assert prompt.property("inputMethodComposing")
        controller.dispatch("accept")
        assert controller.chat.state == "ready"
        commit = QInputMethodEvent()
        commit.setCommitString("你好")
        QCoreApplication.sendEvent(prompt, commit)
        assert prompt.property("text") == "你好"
        assert send.isEnabled()
        QTest.keyClick(window, Qt.Key.Key_Return)
        assert controller.chat.state == "sending"
        assert controller.chat.model.rows[-1]["text"] == "你好"
        assert send.property("text") == controller.translate(Msg.AGENT_STOP, controller.language)
        controller.dispatch("quick-settings")
        wait_until(lambda: controller.chat.state == "ready")
        assert controller.chat.error == "stopped"
        prompt.setProperty("text", "Send from the inline button")
        modal = window.findChild(QQuickItem, "applicationModal")
        wait_until(lambda: send.isEnabled() and not modal.isVisible())
        target = send.mapToItem(window.contentItem(), QPointF(send.width() / 2, send.height() / 2))
        QTest.mouseClick(window, Qt.MouseButton.LeftButton, pos=target.toPoint())
        assert controller.chat.state == "sending"
        assert controller.chat.model.rows[-1]["text"] == "Send from the inline button"
        controller.dispatch("quick-settings")
        wait_until(lambda: controller.chat.state == "ready")
        assert not errors, errors
    finally:
        controller.close()
        delete(engine)


def visible_items(root, name=None):
    pending = [root]
    while pending:
        item = pending.pop()
        if item.isVisible():
            if name is None or item.objectName() == name:
                yield item
            pending.extend(reversed(item.childItems()))


def test_agent_window_renders_reply_types_and_streams_text(qt_application, tmp_path, monkeypatch):
    monkeypatch.delenv("UDECK_REDUCED_MOTION", raising=False)
    QQuickStyle.setStyle("Basic")
    controller = AgentController(tmp_path, tmp_path / "settings.json")
    controller.isolated = True
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("controller", controller)
    engine.rootContext().setContextProperty("windowed", True)
    errors = []
    engine.warnings.connect(lambda warnings: errors.extend(warning.toString() for warning in warnings))
    source = Path(install.__file__).resolve().parents[1] / "common/qml/Main.qml"
    try:
        engine.load(QUrl.fromLocalFile(str(source)))
        assert engine.rootObjects(), errors
        window = engine.rootObjects()[0]
        window.resize(960, 600)
        window.requestActivate()
        controller.window = window
        controller.start()
        controller.chat.agent, controller.chat.cwd = "codex", str(tmp_path)
        controller.publish()
        wait_until(window.isActive)
        wait_until(lambda: window.findChild(QQuickItem, "agentTranscript") is not None)
        transcript = window.findChild(QQuickItem, "agentTranscript")

        model = controller.chat.model
        model.reset([{"kind": "agent", "text": "", "streaming": True}])
        wait_until(lambda: list(visible_items(transcript, "agentReplyRow-agent")))
        source_text = "# 项目报告\n- 读取了 **配置** 和 `main.py`。👩🏽‍💻\n" * 4
        model.rows[0]["text"] = source_text
        model.redraw(0)
        wait_until(lambda: list(visible_items(transcript, "agentReplyText")))
        reply = next(visible_items(transcript, "agentReplyText"))
        full_length = len(source_text.encode("utf-16-le")) // 2
        wait_until(lambda: 0 < reply.property("displayedLength") < full_length)
        assert reply.property("showingRaw")
        model.rows[0]["streaming"] = False
        model.redraw(0)
        wait_until(lambda: not reply.property("showingRaw"))
        assert reply.property("displayedLength") == full_length
        assert "font-weight:700;\">配置</span>" in reply.property("text")
        assert "monospace" in reply.property("text")
        assert ">main.py</span>" in reply.property("text")

        monkeypatch.setenv("UDECK_REDUCED_MOTION", "1")
        controller.publish()
        model.rows[0].update(text="下一段回复", streaming=True)
        model.redraw(0)
        wait_until(lambda: reply.property("displayedLength") == 5)
        assert not reply.property("showingRaw")

        image = QImage(160, 96, QImage.Format.Format_RGB32)
        image.fill(Qt.GlobalColor.darkCyan)
        image_buffer = QBuffer()
        image_buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        assert image.save(image_buffer, "PNG")
        pixel = base64.b64encode(bytes(image_buffer.data())).decode()
        model.reset([
            {"kind": "plan", "blocks": [{"type": "plan", "text": "Review configuration", "status": "completed"}]},
            {"kind": "thought", "text": "Inspect the source tree."},
            {"kind": "tool", "text": "Update settings", "status": "completed", "detail": "settings.ini",
             "blocks": [{"type": "diff", "path": "settings.ini", "oldText": "mode=off", "newText": "mode=on"},
                        {"type": "terminal", "terminalId": "term-42"}, {"type": "session", "sessionId": "child-4"}]},
        ])
        wait_until(lambda: transcript.property("atYEnd"))
        assert not list(visible_items(next(visible_items(transcript, "agentReplyRow-thought")), "agentReplyText"))
        controller.dispatch("up")
        wait_until(lambda: transcript.property("readIndex") == 1)
        controller.dispatch("accept")
        wait_until(lambda: transcript.property("readItem").property("expanded"))
        assert next(visible_items(transcript.property("readItem"), "agentReplyText")).property("sourceText") == (
            "Inspect the source tree."
        )
        controller.dispatch("down")
        wait_until(lambda: transcript.property("readIndex") == 2)
        controller.dispatch("accept")
        wait_until(lambda: transcript.property("readItem").property("expanded"))
        tool = transcript.property("readItem")
        assert {item.property("sourceText") for item in visible_items(tool, "agentReplyText")} == {
            "Update settings", "mode=off", "mode=on",
        }
        assert {"settings.ini", "term-42", "child-4"} <= {
            item.property("text") for item in visible_items(tool) if item.property("text") is not None
        }

        model.reset([
            {"kind": "notice", "text": "Context limit approaching", "detail": "The agent will compact soon."},
            {"kind": "compaction", "status": "completed", "blocks": [{"type": "text", "text": "A short summary."}]},
            {"kind": "subagent", "text": "Project audit", "detail": "Read-only inspection."},
            {"kind": "agent", "blocks": [{"type": "image", "mimeType": "image/png", "data": pixel},
                 {"type": "resource_link", "name": "Manifest", "uri": "file:///tmp/manifest"},
                 {"type": "resource", "uri": "file:///tmp/readme", "text": "An embedded file."},
                 {"type": "audio", "mimeType": "audio/wav", "data": base64.b64encode(b"invalid audio").decode()}]},
        ])
        wait_until(lambda: any(item.property("decoded") for item in visible_items(transcript, "agentReplyImage")))
        audio_row = next(visible_items(transcript, "agentReplyRow-agent"))
        wait_until(lambda: audio_row.property("actionLabel") == Msg.PLAY.value)
        assert {"Manifest", "file:///tmp/manifest", "An embedded file."} <= {
            item.property("text") for item in visible_items(audio_row) if item.property("text") is not None
        }
        transcript.setProperty("follow", False)
        transcript.positionViewAtBeginning()
        transcript.setProperty("readIndex", 0)
        wait_until(lambda: transcript.property("canExpand"))
        notice = transcript.property("readItem")
        assert notice.objectName() == "agentReplyRow-notice"
        assert any(item.property("text") == "Context limit approaching" for item in visible_items(notice))
        assert not any(item.property("text") == "The agent will compact soon." for item in visible_items(notice))
        controller.dispatch("accept")
        wait_until(lambda: any(item.property("text") == "The agent will compact soon."
                               for item in visible_items(notice)))
        assert not errors, errors
    finally:
        controller.close()
        delete(engine)


def test_acp_window_dispatches_command_mode_and_form(qt_application, tmp_path):
    QQuickStyle.setStyle("Basic")
    controller = AgentController(tmp_path, tmp_path / "settings.json")
    controller.isolated = True
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("controller", controller)
    engine.rootContext().setContextProperty("windowed", True)
    errors = []
    engine.warnings.connect(lambda warnings: errors.extend(warning.toString() for warning in warnings))
    source = Path(install.__file__).resolve().parents[1] / "common/qml/Main.qml"
    try:
        engine.load(QUrl.fromLocalFile(str(source)))
        assert engine.rootObjects(), errors
        window = engine.rootObjects()[0]
        window.resize(960, 600)
        window.requestActivate()
        controller.window = window
        controller.start()
        wait_until(window.isActive)
        script = tmp_path / "protocol.py"
        script.write_text(_FULL_AGENT, encoding="utf-8")
        controller.chat.open("codex", tmp_path, [sys.executable, str(script), str(tmp_path)], {})
        wait_until(lambda: controller.chat.state == "auth")
        controller.runSessionAction("authenticate", {"methodId": "oauth"})
        wait_until(lambda: controller.chat.state == "ready")
        transcript = window.findChild(QQuickItem, "agentTranscript")
        model = controller.chat.model

        def select_row(kind):
            index = next(i for i, row in enumerate(model.rows) if row["kind"] == kind)
            transcript.positionViewAtIndex(index, 2)
            transcript.setProperty("readIndex", index)
            wait_until(lambda: transcript.property("canExpand"))

        select_row("commands")
        controller.dispatch("accept")
        wait_until(lambda: transcript.property("readItem").property("expanded"))
        controller.dispatch("accept")
        prompt = window.findChild(QQuickItem, "agentPrompt")
        wait_until(lambda: prompt.property("text") == "/review" and prompt.hasActiveFocus())
        controller.dispatch("back")
        wait_until(lambda: not prompt.hasActiveFocus())
        select_row("mode")
        controller.dispatch("accept")
        wait_until(lambda: bool(controller.menus))
        controller.choose(1)
        mode = next(row for row in model.rows if row["kind"] == "mode")
        wait_until(lambda: mode["text"] == "Edit")
        controller.runSessionAction("config", {"configId": "preview", "value": False})
        wait_until(lambda: any(row["kind"] == "config" for row in model.rows))
        config = next(row for row in model.rows if row["kind"] == "config")
        assert config["blocks"][0]["arguments"] == {"configId": "preview", "value": True}
        select_row("config")
        controller.dispatch("accept")
        wait_until(lambda: any(item.property("text") == "Preview"
                               for item in visible_items(transcript.property("readItem"))))
        controller.insertPrompt.emit("form")
        wait_until(prompt.hasActiveFocus)
        QTest.keyClick(window, Qt.Key.Key_Return)
        wait_until(lambda: bool(controller.chat.client_requests))
        wait_until(lambda: transcript.property("follow") and transcript.property("atYEnd")
                   and any(visible_items(transcript, "agentReplyRow-elicitation")))
        assert model.rows[-1]["kind"] == "elicitation"
        assert model.rows[-2]["text"] == "Parent reply"
        controller.dispatch("down")
        wait_until(lambda: transcript.property("canExpand"))
        assert transcript.property("readItem").objectName() == "agentReplyRow-elicitation"
        controller.dispatch("accept")
        wait_until(lambda: bool(controller.menus))
        controller.choose(1)
        assert controller.menus[-1]["body"] == "Confirm preview"
        controller.choose(0)
        controller.choose(1)
        controller.choose(1)
        wait_until(lambda: controller.chat.state == "ready")
        assert model.rows[-1]["status"] == "end_turn"
        assert not errors, errors
    finally:
        controller.close()
        delete(engine)
