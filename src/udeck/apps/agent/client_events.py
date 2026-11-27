"""[INPUT]: 依赖 ACP 客户端回调与会话模型。
[OUTPUT]: 按事件顺序展示请求、终端输出和交互回执。
[POS]: Conversation 的客户端回调入口。
[PROTOCOL]: Update this header on change, then check AGENTS.md
"""

from udeck.i18n import Msg, tr

from .content import string
from .session_events import action, display_json


class ClientEvents:
    def _client_request(self, client, identifier, method, params):
        if client is not self.client:
            return
        if self.state == "stopping":
            client.respond_action(identifier, "cancel")
            return
        self._flush(final=True)
        self.request_serial += 1
        token = str(self.request_serial)
        self.client_requests[token] = identifier, method, params
        if method == "elicitation/create":
            title, detail = string(params.get("message"), 4000), string(params.get("url"), 4096)
        elif method == "terminal/create":
            title = str(params.get("command", ""))[:240]
            detail = display_json({key: params[key] for key in ("args", "cwd") if key in params})
        else:
            title, detail = string(params.get("path"), 2000), string(params.get("content"), 4000)
        self._card("elicitation" if method == "elicitation/create" else "request", text=title, detail=detail,
                   request=token, elicitation=params.get("elicitationId"), status="pending", transient=True, blocks=[
                       action(tr(Msg.DENY), "request", {"token": token, "decision": "decline"}),
                       action(tr(Msg.CONFIRM), "request", {"token": token, "decision": "accept"}),
                   ])

    def respond_request(self, token, decision, content=None):
        entry = self.client_requests.get(token)
        if not entry or not self.client:
            return False
        return self.client.respond_action(entry[0], decision, content)

    def _cancel_client_requests(self):
        for token in tuple(self.client_requests):
            self.respond_request(token, "cancel")

    def _client_request_closed(self, client, identifier):
        if client is not self.client:
            return
        token = self._request_token(identifier)
        if token is not None:
            self._finish_card("request", token, "pending")

    def _request_token(self, identifier):
        return next((key for key, value in self.client_requests.items() if value[0] == identifier), None)

    def _client_result(self, client, identifier, method, value, error):
        if client is not self.client:
            return
        token = self._request_token(identifier)
        if error:
            status = "cancelled" if error.get("code") == -32800 else "failed"
        elif isinstance(value, dict) and value.get("action") in ("decline", "cancel"):
            status = "cancelled"
        else:
            status = "completed"
        detail = string(error.get("message"), 1000) if error else ""
        if token is not None:
            _, _, payload = self.client_requests.pop(token)
            if method == "elicitation/create" and payload.get("mode") == "url":
                if status == "completed":
                    status = "in_progress"
                detail = detail or string(payload.get("url"), 4096)
            if isinstance(value, dict) and isinstance(value.get("terminalId"), str):
                detail = value["terminalId"]
            self._finish_card("request", token, status, detail=detail)
        elif method in ("terminal/output", "terminal/wait_for_exit") and not error:
            return  # 终端组件持续接收同一终端的输出和退出状态。
        elif method != "session/request_permission":
            self._card("request", text=method, status=status, detail=detail, transient=True)

    def _permission_cancelled(self, client, identifier):
        if client is self.client and self.permissions.pop(identifier, None) is not None:
            self._finish_permission(identifier, "cancelled")
            self.changed.emit()

    def _finish_permission(self, identifier, status):
        self._finish_card("permission", identifier, status)

    def _finish_card(self, key, identifier, status, *, detail=None):
        for index in range(len(self.model.rows) - 1, -1, -1):
            row = self.model.rows[index]
            if row.get(key) == identifier:
                row.update(blocks=[], status=status)
                if detail is not None:
                    row["detail"] = detail
                self.model.redraw(index)
                return

    def _terminal(self, client, session_id, identifier, value):
        if client is not self.client:
            return
        modified = set()
        row = self._upsert(("terminal", identifier), "terminal", modified, boundary=False)
        status = value.get("exitStatus")
        row.update(text=identifier, detail=string(value.get("output"), 64000),
                   status="running" if status is None else "completed" if status.get("exitCode") == 0 else "failed",
                   blocks=[], transient=True)
        if status is not None:
            row["blocks"].append({"type": "text", "text": display_json(status)})
        if value.get("truncated"):
            row["blocks"].append({"type": "text", "text": tr(Msg.AGENT_OUTPUT_TRUNCATED)})
        for index in modified:
            self.model.redraw(index)

    def _elicitation_complete(self, client, params):
        if client is self.client:
            self._finish_card("elicitation", params["elicitationId"], "completed")
