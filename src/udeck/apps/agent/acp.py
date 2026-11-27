"""[INPUT]: 依赖 Qt 子进程、ACP v1 JSON-RPC 与受控客户端方法。
[OUTPUT]: 提供双向请求、通知、请求取消与进程回收。
[POS]: Agent 的本机协议传输层。
[PROTOCOL]: Update this header on change, then check AGENTS.md
"""

import json
import os
import signal
from itertools import count

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, QTimer, Signal

from .client_calls import CAPABILITIES, ClientCalls

_MAX_FRAME = 8 * 1024 * 1024
INITIALIZE = {
    "protocolVersion": 1,
    "clientCapabilities": {"fs": {"readTextFile": False, "writeTextFile": False},
                           "terminal": False,
                           "plan": {},
                           "session": {"notices": {}, "compaction": {}}},
    "clientInfo": {"name": "udeck-agent", "title": "Agent", "version": "1"},
}


class AcpClient(QObject):
    update = Signal(object)
    permission = Signal(object, object)
    request_cancelled = Signal(object)
    client_action = Signal(object, str, object)
    client_action_closed = Signal(object)
    client_result = Signal(object, str, object, object)
    elicitation_completed = Signal(object)
    terminal_changed = Signal(str, str, object)
    disconnected = Signal(str)

    def __init__(self, argv, cwd, *, env=None, parent=None, supports_client_calls=True, capabilities=None):
        super().__init__(parent)
        self.process = QProcess(self)
        self.process.setProgram(argv[0])
        self.process.setArguments(argv[1:])
        self.process.setWorkingDirectory(str(cwd))
        if os.name == "posix":
            self.process.setUnixProcessParameters(QProcess.UnixProcessFlag.CreateNewSession)
        environment = QProcessEnvironment.systemEnvironment()
        for name, value in (env or {}).items():
            environment.insert(name, value)
        self.process.setProcessEnvironment(environment)
        self.buffer = bytearray()
        self.ids = count(1)
        self.pending = {}
        self.incoming = {}
        self.permissions = set()
        self.closing = False
        self.group = 0
        self.calls = ClientCalls(self, enabled=supports_client_calls)
        self.initialize = {
            **INITIALIZE, "clientCapabilities": {
                **INITIALIZE["clientCapabilities"],
                **(CAPABILITIES if supports_client_calls else {}),
                **(capabilities or {}),
            },
        }
        self.process.started.connect(self._started)
        self.process.readyReadStandardOutput.connect(self._read)
        self.process.readyReadStandardError.connect(self.process.readAllStandardError)
        self.process.finished.connect(self._finished)
        self.process.errorOccurred.connect(self._process_error)

    def _started(self):
        self.group = self.process.processId()

    def start(self, callback):
        self.process.started.connect(lambda: self.request("initialize", self.initialize, callback))
        self.process.start()

    def _send(self, value):
        if self.closing or self.process.state() != QProcess.ProcessState.Running:
            return False
        try:
            encoded = json.dumps({"jsonrpc": "2.0", **value}, ensure_ascii=False, allow_nan=False).encode("utf-8")
        except (ValueError, TypeError, RecursionError):
            return False
        if len(encoded) > _MAX_FRAME:
            return False
        return self.process.write(encoded + b"\n") >= 0

    def request(self, method, params, callback, *, timeout=15000):
        identifier = next(self.ids)
        if not self._send({"id": identifier, "method": method, "params": params}):
            callback(None, {"code": -1})
            return None
        self.pending[identifier] = callback
        if timeout:
            QTimer.singleShot(timeout, self, lambda: self.cancel_request(identifier, code=-2))
        return identifier

    def notify(self, method, params):
        return self._send({"method": method, "params": params})

    def cancel_request(self, identifier, *, code=-32800):
        if identifier in self.pending:
            self.notify("$/cancel_request", {"requestId": identifier})
            self._reply(identifier, None, {"code": code, "message": "Request cancelled"})

    def set_session_roots(self, session_id, roots):
        self.calls.set_roots(session_id, roots)

    def clear_session(self, session_id):
        self.calls.clear_session(session_id)

    def respond_action(self, identifier, action, content=None):
        return self.calls.respond(identifier, action, content)

    def answer(self, identifier, result=None, *, error=None):
        if identifier not in self.incoming:
            return
        method = self.incoming.pop(identifier)
        failure = None
        if error is not None:
            failure = {"code": error.code, "message": str(error)}
            self._send({"id": identifier, "error": failure})
        elif not self._send({"id": identifier, "result": result}) and not self.closing:
            failure = {"code": -32603, "message": "Could not send response"}
            self._send({"id": identifier, "error": failure})
        if not self.closing:
            self.client_result.emit(identifier, method, result, failure)

    def answer_permission(self, identifier, option=None):
        if identifier not in self.permissions:
            return
        self.permissions.remove(identifier)
        outcome = {"outcome": "cancelled"} if option is None else {
            "outcome": "selected", "optionId": option,
        }
        self.answer(identifier, {"outcome": outcome})

    def _reply(self, identifier, result, error):
        callback = self.pending.pop(identifier, None)
        if callback:
            self.calls.cancel_scope(identifier)
            callback(result, error)

    def _read(self):
        self.buffer.extend(bytes(self.process.readAllStandardOutput()))
        frames = self.buffer.split(b"\n")
        self.buffer = frames.pop()
        if len(self.buffer) > _MAX_FRAME:
            self._fail("frame")
            return
        for frame in frames:
            if self.closing:
                break
            try:
                if len(frame) > _MAX_FRAME:
                    raise ValueError("Frame exceeds limit")
                self._message(json.loads(frame))
            except (ValueError, TypeError, RecursionError):
                self._fail("protocol")
                break

    def _message(self, message):
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
            raise ValueError("Invalid ACP message")
        identifier = message.get("id")
        if identifier is not None and (type(identifier) not in (int, str)):
            raise ValueError("Invalid request ID")
        method = message.get("method")
        params = message.get("params")
        if method is None and type(identifier) is int:
            error = message.get("error")
            self._reply(identifier, message.get("result"), error if isinstance(error, dict) else None)
        elif "id" not in message and isinstance(params, dict):
            self._notification(method, params)
        elif isinstance(method, str) and "id" in message:
            self._incoming_request(identifier, method, params)

    def _notification(self, method, params):
        if method == "session/update":
            self.update.emit(params)
        elif method == "$/cancel_request":
            if "requestId" not in params:
                return
            identifier = params.get("requestId")
            if type(identifier) not in (int, str, type(None)) or identifier not in self.incoming:
                return
            if identifier in self.permissions:
                self.permissions.remove(identifier)
                self.request_cancelled.emit(identifier)
            self.calls.cancel(identifier)
        elif method == "elicitation/complete":
            self.calls.complete(params)

    def _incoming_request(self, identifier, method, params):
        if identifier in self.incoming:
            return
        self.incoming[identifier] = method
        if method == "session/request_permission":
            self.permissions.add(identifier)
            self.permission.emit(identifier, params if isinstance(params, dict) else {})
        elif not self.calls.dispatch(identifier, method, params):
            self.incoming.pop(identifier)
            self._send({"id": identifier, "error": {"code": -32601, "message": "Method not found"}})

    def _process_error(self, error):
        if error == QProcess.ProcessError.FailedToStart:
            self._fail("launch")

    def _finished(self, code, _status):
        self._signal_group(signal.SIGKILL)
        self.group = 0
        if not self.closing:
            self.close(wait=True)
            self.disconnected.emit(str(code))
        self.deleteLater()

    def _fail(self, reason):
        if not self.closing:
            self.close()
            self.disconnected.emit(reason)

    def _signal_group(self, signum):
        if os.name == "posix" and self.group:
            try:
                os.killpg(self.group, signum)
                return
            except (ProcessLookupError, PermissionError):
                pass
        if self.process.state() != QProcess.ProcessState.NotRunning:
            if signum == signal.SIGTERM:
                self.process.terminate()
            else:
                self.process.kill()

    def close(self, *, wait=False):
        if not self.closing:
            self.closing = True
            self.calls.close(wait=wait)
            self.pending.clear()
            self.incoming.clear()
            self.permissions.clear()
            self.buffer.clear()
            self.process.closeWriteChannel()
        elif wait:
            self.calls.close(wait=True)
        if self.process.state() == QProcess.ProcessState.NotRunning:
            self.deleteLater()
        elif wait:
            if not self.process.waitForFinished(150):
                self._signal_group(signal.SIGKILL)
                self.process.waitForFinished(700)
        else:
            QTimer.singleShot(150, self, lambda: self._signal_group(signal.SIGTERM))
            QTimer.singleShot(800, self, lambda: self._signal_group(signal.SIGKILL))
