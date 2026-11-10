import time
import uuid
from dataclasses import dataclass

from .i18n import error_text, tr


def application_identity(identifier):
    return identifier.casefold().removesuffix(".desktop")


@dataclass
class LaunchRequest:
    application: dict
    identities: set
    started: float
    observable: bool
    submitted: float | None = None


class LaunchTracker:
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.requests = {}
        self.current = ""

    def begin(self, application, *, observable):
        for token, request in self.requests.items():
            if request.application["id"] == application["id"]:
                self.current = token
                return token, False
        token = uuid.uuid4().hex
        identities = {application_identity(application["id"])}
        if application.get("startupWMClass"):
            identities.add(application_identity(application["startupWMClass"]))
        self.requests[token] = LaunchRequest(dict(application), identities, self.clock(), observable)
        self.current = token
        return token, True

    def snapshot(self):
        request = self.requests.get(self.current)
        if request is None:
            return {"pending": False, "visible": False}
        elapsed = self.clock() - request.started
        application = request.application
        return {
            "pending": True, "visible": elapsed >= 0.18, "requestId": self.current,
            "name": application["name"], "icon": application.get("icon") or "application-x-executable",
            "homeKind": application.get("homeKind", ""),
            "message": tr("Still waiting for the application window…") if elapsed >= 8 else tr("Opening application…"),
        }

    def submitted(self, token):
        request = self.requests.get(token)
        if request is not None:
            request.submitted = self.clock()

    def finish(self, token):
        request = self.requests.pop(token, None)
        if self.current == token:
            self.current = ""
        return request

    def fail(self, token, error):
        request = self.finish(token)
        if request is not None:
            return tr("Could not start {name}: {error}", name=request.application["name"], error=error_text(error))
        return None

    def dismiss(self):
        self.current = ""

    def foreground_changed(self, active):
        if not active:
            self.dismiss()

    def windows_changed(self, windows):
        active = {application_identity(window.get("appId", "")) for window in windows
                  if window.get("active") and not window.get("parent") and not window.get("minimized")}
        for token, request in list(self.requests.items()):
            if request.identities & active:
                self.finish(token)

    def advance(self, *, observable):
        notices = []
        now = self.clock()
        for token, request in list(self.requests.items()):
            request.observable = request.observable and observable
            if not request.observable and request.submitted is not None and now - request.submitted >= 2.5:
                self.finish(token)
                notices.append(tr("{name}: Launch request sent.", name=request.application["name"]))
            elif now - request.started >= 20:
                self.finish(token)
                notices.append(tr("{name}: No application window detected; the application may still be starting.",
                                  name=request.application["name"]))
        return notices
