"""[INPUT]: 依赖 ACP 客户端请求、用户选择的目录与 Qt 子进程。
[OUTPUT]: 提供文本文件读写、终端生命周期和结构化输入应答。
[POS]: 执行代理请求的客户端方法并维护会话权限边界。
[PROTOCOL]: Update this header on change, then check AGENTS.md
"""

import math
import os
import signal
import stat
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, QRegularExpression, QTimer

from udeck.network_files.filesystem import SharedRoot

_LIMIT = 1024 * 1024
_REQUEST_LIMIT = 24
_TERMINAL_LIMIT = 8
_ENV = ("HOME", "USER", "LOGNAME", "SHELL", "PATH", "LANG", "LC_ALL", "LC_CTYPE", "TERM", "TMPDIR")

CAPABILITIES = {
    "fs": {"readTextFile": True, "writeTextFile": True},
    "terminal": True,
    "elicitation": {"form": {}, "url": {}},
}


class CallError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def _invalid(message):
    return CallError(-32602, message)


def _id(value):
    return isinstance(value, str) and 0 < len(value) <= 4096


def _positive(value, *, zero=False):
    return type(value) is int and value >= (0 if zero else 1)


def _safe_url(value):
    if not _id(value) or any(ord(char) < 33 or ord(char) == 127 for char in value):
        return False
    try:
        parsed = urlsplit(value)
        return parsed.scheme in ("https", "http") and bool(parsed.hostname) and parsed.username is None
    except ValueError:
        return False


def _form_schema(params):
    schema = params.get("requestedSchema")
    if not isinstance(schema, dict) or schema.get("type", "object") != "object":
        raise _invalid("Invalid elicitation form schema")
    fields, required = schema.get("properties", {}), schema.get("required")
    if not isinstance(fields, dict) or len(fields) > 64:
        raise _invalid("Invalid elicitation form fields")
    if required is not None and (not isinstance(required, list)
                                 or any(not isinstance(name, str) or name not in fields for name in required)):
        raise _invalid("Invalid required elicitation fields")
    for name, spec in fields.items():
        if not _id(name) or not isinstance(spec, dict) or not isinstance(spec.get("type"), str):
            raise _invalid("Invalid elicitation field")
        if spec["type"] == "array" and not isinstance(spec.get("items"), dict):
            raise _invalid("Invalid array field")
    return fields, required or []


def _options(value, spec):
    options = spec.get("oneOf", spec.get("anyOf"))
    if isinstance(options, list):
        return any(isinstance(option, dict) and value == option.get("const") for option in options)
    options = spec.get("enum")
    return not isinstance(options, list) or value in options


def _within(value, spec, minimum, maximum):
    return ((type(spec.get(minimum)) not in (int, float) or value >= spec[minimum])
            and (type(spec.get(maximum)) not in (int, float) or value <= spec[maximum]))


def _form_value(value, spec):
    kind = spec.get("type")
    if kind == "boolean":
        return type(value) is bool
    if kind in ("integer", "number"):
        if type(value) is int:
            return -(2**63) <= value < 2**63 and _within(value, spec, "minimum", "maximum")
        return (kind == "number" and type(value) is float and math.isfinite(value)
                and _within(value, spec, "minimum", "maximum"))
    if kind == "array":
        items = spec["items"]
        return (isinstance(value, list) and len(value) <= 256
                and items.get("type", "string") == "string"
                and _within(len(value), spec, "minItems", "maxItems")
                and all(isinstance(item, str) and _options(item, items) for item in value)
                and len(value) == len(set(value)))
    if kind != "string" or not isinstance(value, str) or len(value) > 16384:
        return False
    if not _within(len(value), spec, "minLength", "maxLength") or not _options(value, spec):
        return False
    pattern = spec.get("pattern")
    if isinstance(pattern, str):
        if len(pattern) > 4096:
            return False
        expression = QRegularExpression("(*LIMIT_MATCH=100000)(*LIMIT_DEPTH=1000)" + pattern)
        if not expression.isValid() or not expression.match(value).hasMatch():
            return False
    return _format_valid(value, spec.get("format"))


def _format_valid(value, kind):
    try:
        if kind == "email":
            address = value.rsplit("@", 1)
            return len(address) == 2 and all(address) and not any(char.isspace() for char in value)
        if kind == "uri":
            return not any(char.isspace() for char in value) and bool(urlsplit(value).scheme)
        if kind == "date":
            return date.fromisoformat(value).isoformat() == value
        if kind == "date-time":
            return len(value) > 10 and value[10] in "Tt" and datetime.fromisoformat(value).tzinfo is not None
    except ValueError:
        return False
    return True


def _form_response(params, content):
    fields, required = _form_schema(params)
    return (isinstance(content, dict) and len(content) <= len(fields)
            and all(name in content for name in required)
            and all(name in fields and _form_value(value, fields[name]) for name, value in content.items()))


class Terminal(QObject):
    def __init__(self, calls, request, session, command, arguments, environment, cwd, limit):
        super().__init__(calls.client)
        self.calls = calls
        self.session = session
        self.identifier = uuid4().hex
        self.output = bytearray()
        self.truncated = False
        self.limit = limit
        self.status = None
        self.create_request = request
        self.creating = True
        self.waiters = set()
        self.group = 0
        self.killed = False
        self.released = False
        self.process = QProcess(self)
        self.process.setProgram(command)
        self.process.setArguments(arguments)
        self.process.setWorkingDirectory(cwd)
        self.process.setProcessEnvironment(environment)
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        if os.name == "posix":
            self.process.setUnixProcessParameters(QProcess.UnixProcessFlag.CreateNewSession)
        self.process.started.connect(self._started)
        self.process.readyReadStandardOutput.connect(self._read)
        self.process.finished.connect(self._finished)
        self.process.errorOccurred.connect(self._failed)
        self.changed = QTimer(self, interval=55, singleShot=True)
        self.changed.timeout.connect(self._publish)

    def _started(self):
        self.group = self.process.processId()
        self.process.closeWriteChannel()
        if self.released:
            self.kill()
            return
        if self.creating:
            self.calls.client.answer(self.create_request, {"terminalId": self.identifier})
            self.creating = False
        self._publish()

    def _read(self):
        self.output.extend(bytes(self.process.readAllStandardOutput()))
        if len(self.output) > self.limit:
            index = len(self.output) - self.limit
            while index < len(self.output) and self.output[index] & 0xC0 == 0x80:
                index += 1
            del self.output[:index]
            self.truncated = True
        if not self.changed.isActive():
            self.changed.start()

    def result(self):
        output = self.output.decode("utf-8", errors="replace")
        encoded = output.encode("utf-8")
        if len(encoded) > self.limit:
            output = encoded[-self.limit:].decode("utf-8", errors="ignore") if self.limit else ""
            self.truncated = True
        result = {"output": output, "truncated": self.truncated}
        if self.status is not None:
            result["exitStatus"] = self.status
        return result

    def _publish(self):
        if not self.released:
            self.calls.client.terminal_changed.emit(self.session, self.identifier, self.result())

    def _finished(self, code, status):
        self._read()
        self.changed.stop()
        self.kill(mark=False)
        self.group = 0
        if status == QProcess.ExitStatus.NormalExit:
            self.status = {"exitCode": code}
        elif self.killed:
            self.status = {"signal": "SIGKILL"}
        else:
            # Qt reports a crash without guaranteeing the Unix signal number.
            self.status = {"exitCode": None, "signal": None}
        for request in tuple(self.waiters):
            self.calls.client.answer(request, self.status)
        self.waiters.clear()
        self._publish()
        if self.released:
            self.deleteLater()

    def _failed(self, error):
        if error == QProcess.ProcessError.FailedToStart:
            if self.creating:
                self.calls.client.answer(self.create_request, error=CallError(-32603, "Could not start terminal"))
                self.creating = False
            self.calls.terminals.pop(self.identifier, None)
            self.deleteLater()

    def kill(self, *, mark=True):
        self.killed |= mark and self.process.state() != QProcess.ProcessState.NotRunning
        if self.group:
            try:
                os.killpg(self.group, signal.SIGKILL)
                return
            except (ProcessLookupError, PermissionError):
                pass
        if self.process.state() != QProcess.ProcessState.NotRunning:
            self.process.kill()

    def release(self, *, wait=False):
        self.released = True
        self.changed.stop()
        self.calls.terminals.pop(self.identifier, None)
        cancelled = CallError(-32800, "Terminal released")
        for request in tuple(self.waiters):
            self.calls.client.answer(request, error=cancelled)
        self.waiters.clear()
        if self.creating:
            self.calls.client.answer(self.create_request, error=cancelled)
            self.creating = False
        self.kill()
        if self.process.state() == QProcess.ProcessState.NotRunning:
            self.deleteLater()
        elif wait:
            self.process.waitForFinished(500)


class ClientCalls:
    def __init__(self, client, *, enabled):
        self.client = client
        self.enabled = enabled
        self.roots = {}
        self.actions = {}
        self.terminals = {}
        self.urls = {}

    def set_roots(self, session, paths):
        opened = []
        for path in dict.fromkeys(paths):
            try:
                opened.append(SharedRoot(path))
            except (OSError, ValueError, RuntimeError):
                continue
        for root in self.roots.get(session, ()):
            root.close()
        self.roots[session] = opened

    def clear_session(self, session):
        for identifier, (_, params) in tuple(self.actions.items()):
            if params.get("sessionId") == session:
                self.cancel(identifier)
        for terminal in tuple(self.terminals.values()):
            if terminal.session == session:
                terminal.release()
        for elicitation, params in tuple(self.urls.items()):
            if params.get("sessionId") == session:
                del self.urls[elicitation]
        for root in self.roots.pop(session, ()):
            root.close()

    def _root(self, session, path, *, directory=False):
        if not _id(path) or "\x00" in path:
            raise _invalid("Invalid absolute path")
        target = Path(path)
        if not target.is_absolute() or ".." in target.parts:
            raise _invalid("Invalid absolute path")
        roots = self.roots.get(session, ())
        for root in roots:
            if target.is_relative_to(root.path):
                relative = target.relative_to(root.path)
                if relative.parts or directory:
                    return root, relative.as_posix() if relative.parts else ""
        raise _invalid("Path is outside the selected workspace")

    def _read_file(self, session, params):
        root, path = self._root(session, params.get("path"))
        line, limit = params.get("line"), params.get("limit")
        if (line is not None and not _positive(line)) or (limit is not None and not _positive(limit, zero=True)):
            raise _invalid("Invalid line range")
        with root.open_file(path) as stream:
            source = stream.read(_LIMIT + 1)
        if len(source) > _LIMIT:
            raise _invalid("Text file exceeds the 1 MiB limit")
        start = 0 if line is None else line - 1
        if start or limit is not None:
            lines = source.split(b"\n")
            end = len(lines) if limit is None else start + limit
            selected = lines[start:end]
            source = b"\n".join(selected) + (b"\n" if selected and end < len(lines) else b"")
        return {"content": source.decode("utf-8")}

    def _write_file(self, session, params):
        root, path = self._root(session, params["path"])
        data = params["content"].encode("utf-8")
        with root.parent(path) as (directory, name):
            current = root.information(directory, name)
        upload = root.begin_upload(path, len(data), "replace")
        try:
            if current is not None:
                os.fchmod(upload.fd, stat.S_IMODE(current.st_mode) & 0o777)
            upload.write(data)
            upload.commit()
        finally:
            upload.abort()
        return {}

    def _terminal_spec(self, session, params):
        command = params.get("command")
        args = params.get("args")
        variables = params.get("env")
        limit = params.get("outputByteLimit")
        if args is None:
            args = []
        if variables is None:
            variables = []
        if (not _id(command) or "\x00" in command or not isinstance(args, list) or len(args) > 256
                or any(not isinstance(arg, str) or "\x00" in arg or len(arg) > 32768 for arg in args)):
            raise _invalid("Invalid terminal command or arguments")
        if not isinstance(variables, list) or len(variables) > 128:
            raise _invalid("Invalid terminal environment")
        environment = QProcessEnvironment()
        for key in _ENV:
            if key in os.environ:
                environment.insert(key, os.environ[key])
        for entry in variables:
            if not isinstance(entry, dict):
                raise _invalid("Invalid terminal environment")
            key, value = entry.get("name"), entry.get("value")
            if (not _id(key) or "=" in key or "\x00" in key or not isinstance(value, str)
                    or "\x00" in value or len(value) > 32768):
                raise _invalid("Invalid terminal environment")
            environment.insert(key, value)
        roots = self.roots.get(session)
        cwd = params.get("cwd")
        if cwd is None:
            if not roots:
                raise _invalid("No workspace directory is available")
            cwd = str(roots[0].path)
        root, relative = self._root(session, cwd, directory=True)
        with root.directory(relative):
            pass
        if limit is not None and not _positive(limit, zero=True):
            raise _invalid("Invalid terminal output limit")
        return command, args, environment, cwd, _LIMIT if limit is None else min(limit, _LIMIT)

    def _queue(self, identifier, method, params):
        if len(self.actions) >= _REQUEST_LIMIT:
            raise CallError(-32800, "Too many pending approval requests")
        self.actions[identifier] = method, params
        self.client.client_action.emit(identifier, method, params)

    def _elicitation(self, identifier, method, params):
        session, request = params.get("sessionId"), params.get("requestId")
        if (session is None) == (request is None):
            raise _invalid("Elicitation requires one request or session scope")
        if session is not None and (not _id(session) or session not in self.roots):
            raise CallError(-32002, "Unknown session")
        if request is not None and (type(request) not in (int, str) or request not in self.client.pending):
            raise CallError(-32002, "Unknown request")
        if not isinstance(params.get("message"), str):
            raise _invalid("Elicitation message is required")
        mode = params.get("mode")
        if mode == "form":
            _form_schema(params)
        elif mode == "url":
            if not _id(params.get("elicitationId")) or not _safe_url(params.get("url")):
                raise _invalid("An HTTP or HTTPS elicitation URL is required")
            if (params["elicitationId"] in self.urls
                    or any(pending.get("elicitationId") == params["elicitationId"]
                           for _, pending in self.actions.values())):
                raise _invalid("Duplicate elicitation ID")
        else:
            self.client.answer(identifier, {"action": "decline"})
            return
        self._queue(identifier, method, params)

    def dispatch(self, identifier, method, params):
        if not self.enabled:
            return False
        if method not in ("fs/read_text_file", "fs/write_text_file", "terminal/create", "terminal/output",
                          "terminal/wait_for_exit", "terminal/kill", "terminal/release", "elicitation/create"):
            return False
        try:
            if not isinstance(params, dict):
                raise _invalid("Request parameters must be an object")
            if method == "elicitation/create":
                self._elicitation(identifier, method, params)
                return True
            session = params.get("sessionId")
            if not _id(session) or session not in self.roots:
                raise CallError(-32002, "Unknown session")
            if method == "fs/read_text_file":
                self.client.answer(identifier, self._read_file(session, params))
            elif method == "fs/write_text_file":
                self._root(session, params.get("path"))
                content = params.get("content")
                if not isinstance(content, str) or len(content.encode("utf-8")) > _LIMIT:
                    raise _invalid("Text content exceeds the 1 MiB limit or is invalid")
                self._queue(identifier, method, params)
            elif method == "terminal/create":
                self._terminal_spec(session, params)
                self._queue(identifier, method, params)
            else:
                self._terminal_call(identifier, method, session, params.get("terminalId"))
        except (CallError, OSError, ValueError) as error:
            self.client.answer(identifier, error=self._error(error))
        return True

    @staticmethod
    def _error(error):
        if isinstance(error, CallError):
            return error
        if isinstance(error, FileNotFoundError):
            return CallError(-32002, "File or directory not found")
        if isinstance(error, UnicodeError):
            return _invalid("Text must be valid UTF-8")
        return _invalid("File or terminal operation is not available for this path")

    def _terminal_call(self, request, method, session, identifier):
        terminal = self.terminals.get(identifier) if _id(identifier) else None
        if terminal is None or terminal.session != session:
            raise CallError(-32002, "Unknown terminal")
        if method == "terminal/wait_for_exit":
            if terminal.status is not None:
                self.client.answer(request, terminal.status)
            else:
                if len(terminal.waiters) >= _REQUEST_LIMIT:
                    raise CallError(-32800, "Too many terminal wait requests")
                terminal.waiters.add(request)
        elif method == "terminal/output":
            self.client.answer(request, terminal.result())
        else:
            if method == "terminal/kill":
                terminal.kill()
            else:
                terminal.release()
            self.client.answer(request, {})

    def respond(self, identifier, action, content):
        entry = self.actions.get(identifier)
        if not entry or action not in ("accept", "decline", "cancel"):
            return False
        method, params = entry
        if method == "elicitation/create" and action == "accept":
            if params["mode"] == "form" and not _form_response(params, content):
                return False
            if params["mode"] == "url" and (len(self.urls) >= _REQUEST_LIMIT
                                            or params["elicitationId"] in self.urls):
                return False
        del self.actions[identifier]
        self.client.client_action_closed.emit(identifier)
        try:
            if method == "elicitation/create":
                result = {"action": action}
                if action == "accept":
                    if params["mode"] == "form":
                        result["content"] = content
                    else:
                        self.urls[params["elicitationId"]] = params
                self.client.answer(identifier, result)
            elif action != "accept":
                self.client.answer(identifier, error=CallError(-32800, "User declined the request"))
            elif method == "fs/write_text_file":
                self.client.answer(identifier, self._write_file(params["sessionId"], params))
            else:
                if len(self.terminals) >= _TERMINAL_LIMIT:
                    raise CallError(-32800, "Too many active terminals")
                terminal = Terminal(self, identifier, params["sessionId"],
                                    *self._terminal_spec(params["sessionId"], params))
                self.terminals[terminal.identifier] = terminal
                terminal.process.start()
        except (CallError, OSError, ValueError) as error:
            self.client.answer(identifier, error=self._error(error))
        return True

    def complete(self, params):
        elicitation = params.get("elicitationId")
        if not _id(elicitation):
            return
        request = self.urls.pop(elicitation, None)
        if request is not None:
            scope = {key: request[key] for key in ("sessionId", "requestId", "toolCallId") if key in request}
            self.client.elicitation_completed.emit({**scope, **params})

    def cancel_scope(self, request):
        for identifier, (_, params) in tuple(self.actions.items()):
            if params.get("requestId") == request:
                self.cancel(identifier)

    def cancel(self, identifier):
        if self.actions.pop(identifier, None) is not None:
            self.client.client_action_closed.emit(identifier)
        for terminal in tuple(self.terminals.values()):
            terminal.waiters.discard(identifier)
            if terminal.creating and terminal.create_request == identifier:
                terminal.release()
        self.client.answer(identifier, error=CallError(-32800, "Request cancelled"))

    def close(self, *, wait=False):
        for identifier in tuple(self.actions):
            self.cancel(identifier)
        for terminal in tuple(self.terminals.values()):
            terminal.release(wait=wait)
        self.urls.clear()
        for session in tuple(self.roots):
            self.clear_session(session)
