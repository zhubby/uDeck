"""[INPUT]: 依赖共享窗口、ACP 会话和用户级安装事务。
[OUTPUT]: 路由会话操作、权限请求和设置中的 Agent 管理。
[POS]: Agent 的 QML 与桌面入口。
[PROTOCOL]: Update this header on change, then check AGENTS.md
"""

import base64
import sqlite3
from pathlib import Path

from PySide6.QtCore import Property, QBuffer, QIODevice, QObject, QUrl, Signal, Slot

from udeck.apps.common.controller import AppController
from udeck.i18n import Msg, tr
from udeck.text_input import composing_action_blocked

from .catalog import AGENTS, version
from .content import AUDIO_FORMATS, MAX_TEXT, media_data
from .conversation import Conversation
from .install import Installer, command, installed, state, supported_platform
from .session_actions import SessionActions
from .sessions import SessionStore

_CONNECTION = {
    "idle": Msg.AGENT_IDLE, "starting": Msg.AGENT_CONNECTING,
    "ready": Msg.CONNECTED, "sending": Msg.AGENT_RUNNING,
    "stopping": Msg.AGENT_STOPPING, "auth": Msg.AGENT_AUTH_REQUIRED,
}
_ERRORS = {
    "protocol": Msg.AGENT_PROTOCOL_ERROR, "resume": Msg.AGENT_RESUME_ERROR,
    "login": Msg.AGENT_AUTH_REQUIRED, "connection": Msg.AGENT_CONNECTION_ERROR,
    "disconnected": Msg.AGENT_DISCONNECTED, "stopped": Msg.AGENT_STOPPED,
    "prompt": Msg.AGENT_PROMPT_ERROR, "storage": Msg.AGENT_STORAGE_ERROR,
    "launch": Msg.AGENT_CONNECTION_ERROR, "missing": Msg.AGENT_MISSING,
    "platform": Msg.AGENT_PLATFORM, "cancelled": Msg.AGENT_CANCELLED,
    "install": Msg.AGENT_INSTALL_ERROR, "package": Msg.AGENT_INSTALL_ERROR,
    "timeout": Msg.AGENT_INSTALL_ERROR, "checksum": Msg.AGENT_CHECKSUM,
    "archive": Msg.AGENT_CHECKSUM, "busy": Msg.AGENT_BUSY, "space": Msg.AGENT_SPACE,
}


class AgentController(AppController, SessionActions):
    editPrompt = Signal()
    submitPrompt = Signal()
    leavePrompt = Signal()
    acceptTranscript = Signal()
    insertPrompt = Signal(str)
    scrollTranscript = Signal(int)
    replyAudioChanged = Signal()

    def __init__(self, directory=None, language_path=None):
        super().__init__("agent", directory, language_path)
        self.page = "agent"
        self.root = self.store.path.parent / "agent"
        self.installer = Installer(self.root, self)
        self.installer.completed.connect(self._install_done)
        self.installer.progress.connect(self._progress)
        self.chat = Conversation(SessionStore(self.root), self)
        self.chat.changed.connect(self._chat_changed)
        self.chat.model.modelAboutToBeReset.connect(self._stop_reply_audio)
        self._audio_player = None
        self._audio_buffer = None
        self._audio_clip = ""
        self._audio_failure = ""
        self.installed = {}
        self.releases = {}
        self.verified = set()
        self.auth_required = set()
        self.job = ""
        self.task = ""
        self.stage = ""
        self.provider_index = 0
        self.permission_id = None
        self.pending_workspace = None
        self.attachments = []
        self._load_versions()
        recent = self.chat.store.list()
        if recent:
            self.chat.select(recent[0])

    def create_library(self, app):
        return None

    def start(self):
        if self.window:
            self.window.activeChanged.connect(self._sync_permission)
        super().start()

    def tabs(self):
        return []

    @Property(QObject, constant=True)
    def messages(self):
        return self.chat.model

    @Property(str, notify=replyAudioChanged)
    def replyAudioClip(self):
        return self._audio_clip

    @Property(str, notify=replyAudioChanged)
    def replyAudioFailure(self):
        return self._audio_failure

    @Slot(str, str, str)
    def toggleReplyAudio(self, clip, mime_type, encoded):
        was_active = self._audio_clip == clip
        self._stop_reply_audio()
        if was_active or not clip or self.page != "agent":
            return
        encoded = media_data(encoded, mime_type in AUDIO_FORMATS)
        if not encoded:
            return
        from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer

        if self._audio_player is None:
            self._audio_player = QMediaPlayer(self)
            self._audio_player.setAudioOutput(QAudioOutput(self._audio_player))
            self._audio_player.mediaStatusChanged.connect(self._reply_audio_status)
        self._audio_buffer = QBuffer(self._audio_player)
        self._audio_buffer.setData(base64.b64decode(encoded))
        self._audio_buffer.open(QIODevice.OpenModeFlag.ReadOnly)
        self._audio_clip = clip
        self._audio_player.setSourceDevice(self._audio_buffer, QUrl("inline." + AUDIO_FORMATS[mime_type]))
        if self._audio_clip:
            self._audio_player.play()
        self.replyAudioChanged.emit()

    def _reply_audio_status(self, status):
        from PySide6.QtMultimedia import QMediaPlayer

        if status == QMediaPlayer.MediaStatus.InvalidMedia:
            self._stop_reply_audio(self._audio_clip)
        elif status == QMediaPlayer.MediaStatus.EndOfMedia:
            self._stop_reply_audio()

    def _stop_reply_audio(self, failed=""):
        if self._audio_clip or self._audio_failure:
            self._audio_clip = ""
            self._audio_failure = failed
            if self._audio_buffer is not None:
                buffer, self._audio_buffer = self._audio_buffer, None
                self._audio_player.stop()
                self._audio_player.setSource(QUrl())
                buffer.deleteLater()
            self.replyAudioChanged.emit()

    def _load_versions(self):
        self.installed = {key: installed(self.root, key) for key in AGENTS}

    def _update_available(self, key):
        active, release = self.installed[key], self.releases.get(key)
        if not active or not release:
            return False
        if version(release["version"]) > version(active):
            return True
        if active == release["version"] and "packages" in release:
            current = state(self.root, key).get("active", {}).get("packages", {})
            return any(name in current and version(target) > version(current[name])
                       for name, target in release["packages"].items())
        return False

    def extra_state(self):
        primary = (self._provider_options(list(AGENTS)[self.provider_index])[0]
                   if self.page == "agent-settings" else None)
        return {
            "providers": [{"id": key, "name": agent.name, "installed": self.installed[key],
                           "available": self.releases.get(key, {}).get("version", ""),
                           "upgrade": self._update_available(key),
                           "needsLogin": key in self.auth_required,
                           "verified": key in self.verified}
                          for key, agent in AGENTS.items()],
            "providerIndex": self.provider_index,
            "providerPrimary": tr(primary[0]) if primary else "",
            "providerGlyph": primary[2] if primary else "",
            "agentId": self.chat.agent,
            "agentName": AGENTS[self.chat.agent].name if self.chat.agent else "",
            "workspace": self.chat.cwd,
            "connection": tr(_CONNECTION[self.chat.state]),
            "connectionState": self.chat.state,
            "turn": self.chat.state in {"sending", "stopping"},
            "canSend": self.chat.state == "ready" and not self.chat.control_busy,
            "busy": self.chat.busy or bool(self.job),
            "session": self.chat.key,
            "attachments": [name for name, _block in self.attachments],
            "hasInstalledAgent": any(self.installed.values()),
            "job": self.job,
            "stage": tr(Msg.AGENT_VERIFYING if self.stage == "verify" or self.task == "probe" else
                        Msg.AGENT_CHECKING if self.task == "check" else Msg.AGENT_INSTALLING),
        }

    def publish(self):
        super().publish()
        if hasattr(self, "chat"):
            self.chat.model.retranslate(self.language)

    def settings_options(self):
        return [self.setting_option(tr(Msg.AGENT_MANAGE), self._show_provider_settings, "preferences-system")]

    def _show_provider_settings(self, key=None):
        self.clear_menus()
        self._stop_reply_audio()
        if key is not None:
            self.provider_index = list(AGENTS).index(key)
        self.page = "agent-settings"
        self.feedback("navigate")
        self.publish()

    @Slot(str)
    def dispatch(self, action):
        if action in {"previous-tab", "next-tab"} or composing_action_blocked(self, action):
            return
        if self.permission_id is not None:
            if action == "back":
                self._answer(None)
            elif self.window and self.window.isActive():
                super().dispatch(action)
            return
        if self.menus:
            super().dispatch(action)
            return
        if self.page == "agent-settings":
            if action in {"back", "left"}:
                self.page = "agent"
                self.feedback("back")
                self.publish()
            elif action in {"up", "down"}:
                delta = 1 if action == "down" else -1
                index = min(len(AGENTS) - 1, max(0, self.provider_index + delta))
                self.selectProvider(list(AGENTS)[index])
            elif action in {"accept", "context", "quick-settings"}:
                self.context()
            return
        focus = self.window.activeFocusItem() if self.window else None
        if focus and focus.property("inputController") is self:
            if action == "accept":
                self.submitPrompt.emit()
            elif action == "back":
                self.leavePrompt.emit()
            return
        if action == "accept":
            self.acceptTranscript.emit()
        elif action in {"up", "down"}:
            self.scrollTranscript.emit(1 if action == "down" else -1)
        elif action == "right":
            if self.chat.state == "ready":
                self.editPrompt.emit()
        elif action == "left":
            self.scrollTranscript.emit(0)
        elif action == "context":
            self._history()
        elif action == "quick-settings":
            if self.chat.state == "sending":
                self.stopTurn()
            elif self.chat.state != "stopping":
                self.context()
        else:
            super().dispatch(action)

    @Slot()
    def primarySessionAction(self):
        if self.page != "agent" or self.menus or self.job:
            return
        if self.chat.state == "ready":
            self.editPrompt.emit()
        elif self.chat.state == "sending":
            self.stopTurn()
        elif self.chat.state == "auth":
            self.chat.retry_auth()
        elif self.chat.key and self.chat.state == "idle":
            self._resume()
        elif not self.chat.busy:
            self.newSession()

    @Slot()
    def context(self):
        if self.page == "agent-settings":
            self.providerActions(list(AGENTS)[self.provider_index])
            return
        options = [(tr(Msg.AGENT_NEW), self.newSession), (tr(Msg.AGENT_HISTORY), self._history),
                   (tr(Msg.SETTINGS), self.settings)]
        if self.chat.state in {"sending", "stopping"}:
            options.insert(0, (tr(Msg.AGENT_STOP), self.stopTurn))
        elif self.chat.key and self.chat.state == "idle":
            options.insert(0, (tr(Msg.AGENT_RESUME), self._resume))
        if self.chat.rpc and self.chat.state == "ready":
            options.append((tr(Msg.AGENT_ATTACH), lambda: self._choose_action({
                "action": "attach", "arguments": {},
            })))
            if self.attachments:
                options.extend((name, lambda index=index: self._choose_action({
                    "action": "remove_attachment", "arguments": {"index": index},
                }), tr(Msg.REMOVE)) for index, (name, _) in enumerate(self.attachments))
            for method, label, operation in (
                ("list", Msg.AGENT_PROTOCOL_REMOTE_SESSIONS, "remote_list"),
                ("close", Msg.AGENT_CLOSE_SESSION, "close"),
                ("logout", Msg.AGENT_LOGOUT, "logout"),
            ):
                if self.chat.rpc.supported(method):
                    options.append((tr(label), lambda operation=operation: self._session_action(operation, {})))
        self.menu(tr(Msg.ACTIONS), options)

    @Slot(str, "QVariantMap")
    def runSessionAction(self, action, params):
        self.attempt(lambda: self._session_action(action, params))

    def command(self, action):
        if action == "settings" and (self.menus or self.permission_id is not None):
            return
        if action in {"settings", "context", "home"}:
            super().command(action)

    @Slot()
    def newSession(self):
        if self.chat.busy or self.job or self.permission_id is not None:
            return
        self.clear_menus()
        if not any(self.installed.values()):
            self._show_provider_settings()
            return
        self.menu(tr(Msg.AGENT_SELECT), [
            (agent.name, lambda key=key: self._choose_workspace(key) if self.installed[key]
             else self._show_provider_settings(key),
             tr(Msg.AGENT_INSTALLED if self.installed[key] else Msg.AGENT_MISSING))
            for key, agent in AGENTS.items()
        ])

    def _choose_workspace(self, key):
        self.clear_menus()
        default = self.chat.cwd or str(Path.home())
        self._workspace_menu(key, default)

    def _open(self, key, text, *, resume=None, options=None):
        if self.job or self.chat.busy:
            return
        try:
            directory = Path(text).expanduser().resolve(strict=True)
            if not directory.is_dir():
                raise ValueError()
            argv, env = command(self.root, key)
        except (OSError, ValueError, RuntimeError):
            self.error = tr(Msg.AGENT_WORKSPACE_ERROR)
            self.publish()
            return
        self.clear_menus()
        self.attachments.clear()
        self.error = ""
        self.page = "agent"
        self.pending_workspace = (key, str(directory), resume, options)
        self.chat.open(key, directory, argv, env, resume=resume, options=options)

    @Slot(str, result=bool)
    def sendPrompt(self, text):
        if self.menus or self.job:
            return False
        self.error = ""
        if not self.attachments:
            return self.chat.send(text)
        if len(text) > MAX_TEXT:
            return False
        prompt = ([{"type": "text", "text": text}] if text.strip() else [])
        prompt.extend(block for _name, block in self.attachments)
        if self.chat.send_blocks(prompt):
            self.attachments.clear()
            self.publish()
            return True
        return False

    @Slot()
    def stopTurn(self):
        if self.permission_id is None:
            self.clear_menus()
        self.chat.stop()
        self.publish()

    def _chat_changed(self):
        self.error = tr(_ERRORS[self.chat.error]) if self.chat.error else ""
        if self.chat.state == "ready":
            self.verified.add(self.chat.agent)
            self.auth_required.discard(self.chat.agent)
            self.pending_workspace = None
        elif self.chat.error == "login":
            self.auth_required.add(self.chat.agent)
        self._sync_permission()
        self.publish()

    def _sync_permission(self):
        first = next(iter(self.chat.permissions), None)
        if self.permission_id is not None and self.permission_id != first:
            self.permission_id = None
            self.clear_menus()
            self.publish()
        if first is None or first == self.permission_id or not self.window or not self.window.isActive():
            return
        self.clear_menus()
        self.permission_id = first
        title, options = self.chat.permissions[first]
        targets = [(tr(Msg.CANCEL), lambda: self._answer(None))]
        targets += [(item["name"][:200], lambda target=item["optionId"]: self._answer(target))
                    for item in options]
        self.menu(tr(Msg.AGENT_PERMISSION), targets, title, quiet=True)

    def _answer(self, option):
        if option is not None and (not self.window or not self.window.isActive()):
            return
        self.clear_menus()
        self.permission_id = None
        self.chat.respond(option)

    @Slot()
    def showHistory(self):
        self._history()

    @Slot()
    def resumeSession(self):
        if self.chat.state == "auth":
            self.chat.retry_auth()
        else:
            self._resume()

    def _history(self):
        if self.chat.busy or self.job or self.permission_id is not None:
            return
        self.clear_menus()
        entries = self.chat.store.list()
        self.menu(tr(Msg.AGENT_HISTORY), [
            (entry["title"], lambda entry=entry: self._history_actions(entry),
             f'{AGENTS[entry["agent"]].name} · {entry["directory"]}')
            for entry in entries if entry["agent"] in AGENTS
        ], body=tr(Msg.AGENT_EMPTY_HISTORY) if not entries else "")

    def _history_actions(self, entry):
        self.menu(entry["title"], [
            (tr(Msg.OPEN), lambda: self._view(entry)),
            (tr(Msg.AGENT_RESUME), lambda: self._resume(entry)),
            (tr(Msg.AGENT_RENAME), lambda: self.prompt(
                tr(Msg.AGENT_RENAME), lambda text: self._rename(entry, text), entry["title"])),
            (tr(Msg.AGENT_DELETE), lambda: self.menu(tr(Msg.AGENT_DELETE), [
                (tr(Msg.CANCEL), self.pop_menu), (tr(Msg.CONFIRM), lambda: self._delete(entry)),
            ], entry["title"])),
        ])

    def _view(self, entry):
        self.clear_menus()
        if self.chat.key != entry["id"]:
            self.chat.select(entry)
        self.page = "agent"
        self.publish()

    def _resume(self, entry=None):
        entry = entry or next((item for item in self.chat.store.list() if item["id"] == self.chat.key), None)
        if entry:
            self._view(entry)
            self._open(entry["agent"], entry["directory"], resume=entry)

    def _rename(self, entry, text):
        name = text.strip()[:100]
        if name:
            self.chat.store.rename(entry["id"], name)
        self.clear_menus()
        self.publish()

    def _delete(self, entry):
        if self.chat.key == entry["id"]:
            self.chat.stop_connection()
            self.chat.key = self.chat.cwd = self.chat.agent = ""
            self.chat.model.reset([])
        self.chat.store.delete(entry["id"])
        self._history()

    @Slot(str)
    def selectProvider(self, key):
        if key in AGENTS and self.page == "agent-settings" and not self.menus:
            index = list(AGENTS).index(key)
            if index != self.provider_index:
                self.provider_index = index
                self.feedback("navigate")
                self.publish()

    @Slot()
    def activateProvider(self):
        if self.page == "agent-settings" and not self.menus:
            key = list(AGENTS)[self.provider_index]
            if supported_platform() or self.job or self.installed[key]:
                self.attempt(self._provider_options(key)[0][1])
            else:
                self.providerActions(key)

    @Slot()
    def checkProviderUpdates(self):
        if self.page == "agent-settings" and not self.menus:
            self.attempt(lambda: self._install("check", list(AGENTS)[self.provider_index]))

    @Slot(str)
    def providerActions(self, key):
        if key not in AGENTS or self.permission_id is not None:
            return
        self.provider_index = list(AGENTS).index(key)
        self.clear_menus()
        options = [(tr(label), callback) for label, callback, _glyph in self._provider_options(key)]
        body = tr(Msg.AGENT_PLATFORM) if not supported_platform() else ""
        self.menu(AGENTS[key].name, options, body)

    def _provider_options(self, key):
        ready = bool(self.installed[key])
        if self.job:
            return [(Msg.CANCEL, self._cancel_install, "stop-fill")]
        check = (Msg.AGENT_CHECK_UPDATES, lambda: self._install("check", key), "arrow-repeat")
        if self.chat.busy:
            return [check]
        options = []
        if ready:
            options += [(Msg.AGENT_LOGIN, lambda: self._login(key), "box-arrow-in-right"),
                        (Msg.AGENT_TEST_CONNECTION, lambda: self._install("probe", key), "plug")]
            if key == "codex":
                options.insert(1, (Msg.AGENT_DEVICE_LOGIN, lambda: self._login(key, device=True),
                                   "box-arrow-in-right"))
            if self.chat.error == "login" and self.pending_workspace and self.pending_workspace[0] == key:
                options.append((Msg.AGENT_RETRY, self._retry_workspace, "arrow-repeat"))
            if self._update_available(key):
                options.insert(0, (Msg.AGENT_UPGRADE, lambda: self._install("install", key), "download"))
            if state(self.root, key).get("previous"):
                options.append((Msg.AGENT_ROLLBACK, lambda: self._install("rollback", key), "arrow-repeat"))
        else:
            options.append((Msg.AGENT_INSTALL, lambda: self._install("install", key), "download"))
        return [*options, check]

    def _retry_workspace(self):
        if self.pending_workspace:
            key, directory, resume, options = self.pending_workspace
            if self.chat.state == "auth":
                self.clear_menus()
                self.page = "agent"
                self.chat.retry_auth()
                self.publish()
            else:
                self._open(key, directory, resume=resume, options=options)

    def _login(self, key, *, device=False):
        argv, env = command(self.root, key, login=True)
        if device:
            argv.append("--device-auth")
        self._launch_login(argv, env, str(Path.home()))

    def _install(self, action, key):
        if self.job or (action != "check" and self.chat.busy):
            return
        if action in {"install", "rollback"} and self.chat.client and self.chat.agent == key:
            self.chat.stop_connection()
        if self.installer.start(action, key):
            self.clear_menus()
            self.error = self.notice = ""
            self.job, self.task, self.stage = key, action, ""
            self.publish()

    def _cancel_install(self):
        self.installer.cancel()
        self.clear_menus()
        self.publish()

    @Slot(str, str)
    def _progress(self, key, stage):
        if self.job == key:
            self.stage = stage
            self.publish()

    @Slot(str, str, object, str)
    def _install_done(self, action, key, result, error):
        self.installer.job = None
        self.job = self.task = self.stage = ""
        self._load_versions()
        if error:
            self.error = tr(_ERRORS.get(error, Msg.AGENT_INSTALL_ERROR))
        elif action == "check":
            self.releases[key] = result
            self.notice = tr(Msg.AGENT_VERSION_FOUND, version=result["version"])
        elif action == "probe":
            self.verified.add(key)
            self.notice = tr(Msg.AGENT_VERIFIED)
        else:
            self.verified.discard(key)
            self.notice = tr(Msg.AGENT_VERSION_READY, version=result["version"])
        self.publish()

    def diagnostic_state(self):
        return {"app": self.app, "page": self.page, "connection": self.chat.state,
                "installing": self.job, "versions": self.installed}

    def close(self):
        if self._closed:
            return
        self._stop_reply_audio()
        self.installer.close()
        try:
            self.chat.close()
        except sqlite3.Error:
            pass
        finally:
            super().close()
