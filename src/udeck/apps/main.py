"""Independent, single-instance application launchers and session D-Bus control."""

import argparse
import json
import os
import sys
import tempfile
import time
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, QUrl, Slot
from PySide6.QtDBus import QDBusConnection, QDBusInterface, QDBusMessage
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow  # noqa: F401
from PySide6.QtWidgets import QApplication
from shiboken6 import delete

from ..app_routing import APP_IDS, object_path, service_name
from ..core import ConfigStore
from ..i18n import tr
from . import __version__
from .library import EXTENSIONS


def make_controller(app, directory=None, language_path=None):
    if app in ("music", "video"):
        from .media import MediaController

        return MediaController(app, directory, language_path)
    if app == "browser":
        from .web import BrowserController

        return BrowserController(directory, language_path)
    if app == "reader":
        from .reader import ReaderController

        return ReaderController(directory, language_path)
    from .games import GamesController

    return GamesController(directory, language_path)


class AppControl(QObject):
    def __init__(self, controller, show, errors, started):
        super().__init__()
        self.controller, self.show = controller, show
        self.errors, self.started = errors, started
        self.open_generation = 0

    @Slot(str, result=str)
    def Open(self, payload):
        try:
            request = json.loads(payload)
            if (not isinstance(request, dict) or not isinstance(request.get("command", ""), str)
                    or not isinstance(request.get("files", []), list)
                    or not all(isinstance(value, str) for value in request.get("files", []))):
                raise ValueError("Expected an object with a command string and a list of file paths")
            if request.get("command"):
                self.controller.command(request["command"])
            if request.get("files"):
                self.open_files(request["files"])
            self.show()
            return ""
        except (ValueError, OSError, RuntimeError) as error:
            return str(error)

    def open_files(self, files):
        controller = self.controller
        if controller.app == "browser":
            for url in files:
                controller.openLink(url)
            return
        if not files:
            return
        paths = []
        for value in files:
            url = QUrl(value)
            if url.scheme() and not url.isLocalFile():
                raise ValueError(tr("Choose a local file"))
            paths.append(Path(url.toLocalFile() if url.isLocalFile() else value).expanduser().resolve(strict=True))
        for path in paths:
            if not path.is_file():
                raise ValueError(tr("Choose a file"))
            if path.suffix.lower() not in EXTENSIONS[controller.app]:
                raise ValueError(tr("Unsupported file format: {name}", name=path.name))
        self.open_generation += 1
        generation = self.open_generation
        for path in paths:
            if not any(Path(s.path) in path.parents for s in controller.library.sources):
                controller.library.add(path.parent)
        wanted = str(paths[0])
        def ready():
            if generation != self.open_generation:
                controller.library.changed.disconnect(ready)
                return
            item = next((item for item in controller.library.items if item["path"] == wanted), None)
            if item:
                controller.library.changed.disconnect(ready)
                controller.attempt(lambda: controller.open_item(item["id"]))
                controller.publish()
        controller.library.changed.connect(ready)
        ready()

    @Slot(result=str)
    def Diagnose(self):
        return json.dumps({"app": self.controller.app, "version": __version__,
                           "uptime": round(time.monotonic() - self.started, 2),
                           "qmlErrors": self.errors,
                           "state": json.loads(self.controller.snapshotJson)}, ensure_ascii=False)

    @Slot(int, bool)
    def Route(self, generation, enabled):
        if self.controller.inputs:
            self.controller.inputs.route(generation, enabled)

    @Slot(int, str)
    def Shoulder(self, generation, action):
        if self.controller.inputs:
            self.controller.inputs.shoulder(generation, action)

    @Slot(str, result=str)
    def Action(self, action):
        self.controller.command(action)
        return ""

    @Slot(result=bool)
    def IsPlaying(self):
        return bool(self.controller.app == "music" and self.controller.media.snapshot()["playing"])

    @Slot(str, result=bool)
    def PauseForVideo(self, token):
        if not self.IsPlaying():
            return True
        self.controller.media.player.pause()
        self.controller.paused_by_video = token
        return not self.controller.media.snapshot()["playing"]

    @Slot(str)
    def ResumeAfterVideo(self, token):
        if self.controller.app == "music" and self.controller.paused_by_video == token:
            self.controller.paused_by_video = ""
            self.controller.media.player.play()

    @Slot(str)
    def ReleaseVideo(self, token):
        if self.controller.app == "music" and self.controller.paused_by_video == token:
            self.controller.paused_by_video = ""


def main(argv=None):
    parser = argparse.ArgumentParser(description="uDeck native applications")
    parser.add_argument("app", choices=list(APP_IDS))
    parser.add_argument("files", nargs="*")
    parser.add_argument("--source", type=Path, action="append", default=[])
    parser.add_argument("--windowed", action="store_true")
    parser.add_argument("--no-input", action="store_true")
    parser.add_argument("--isolated", action="store_true", help="Use temporary state, without desktop IPC or hardware input")
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--language", choices=("en", "zh_CN"))
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--command", choices=("pause-game", "now-playing", "settings", "sources"))
    parser.add_argument("--doctor", action="store_true")
    parser.add_argument("--screenshot", type=Path)
    parser.add_argument("--smoke-test", action="store_true")
    parser.add_argument("--quit-after", type=float, default=0)
    options = parser.parse_args(argv)
    if options.app == "browser" and options.source:
        parser.error("--source is only available for local content apps")
    if options.smoke_test and not options.isolated:
        parser.error("--smoke-test requires --isolated")
    os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")
    if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
        os.environ.setdefault("QT_QUICK_BACKEND", "software")
    if options.app in ("browser", "reader"):
        from PySide6.QtWebEngineQuick import QtWebEngineQuick

        QtWebEngineQuick.initialize()
    application = QApplication(["udeck-" + options.app])
    application.setApplicationName(APP_IDS[options.app])
    application.setDesktopFileName(APP_IDS[options.app])
    application.setOrganizationName("uDeck")
    application.setQuitOnLastWindowClosed(False)
    bus = QDBusConnection.sessionBus()
    app_id = APP_IDS[options.app]
    service, path, interface = service_name(app_id), object_path(app_id), app_id + ".Control"
    remote = QDBusInterface(service, path, interface, bus)
    if not options.isolated and remote.isValid():
        result = remote.call("Diagnose" if options.doctor else "Open", *([] if options.doctor else [
            json.dumps({"files": options.files, "command": options.command})]))
        if result.type() == QDBusMessage.MessageType.ErrorMessage:
            print(result.errorMessage(), file=sys.stderr)
            return 1
        response = result.arguments()[0] if result.arguments() else ""
        if response:
            print(response, file=sys.stdout if options.doctor else sys.stderr)
        return 0 if options.doctor or not response else 1
    if options.doctor:
        print(json.dumps({"app": options.app, "running": False}))
        return 0
    if options.command == "pause-game":
        print("No uDeck game session is running", file=sys.stderr)
        return 1
    registered = not options.isolated and bus.isConnected() and bus.registerService(service)
    if not options.isolated and not registered:
        print("Cannot register the graphical session service; launch from the desktop", file=sys.stderr)
        return 1
    temporary = tempfile.TemporaryDirectory(prefix="udeck-app-preview-") if options.isolated and not options.data_dir else None
    directory = options.data_dir or (Path(temporary.name) if temporary else None)
    language_path = Path(directory) / "settings.json" if options.isolated else None
    if options.language and language_path:
        config = ConfigStore(language_path)
        config.data["preferences"]["language"] = options.language
        config.save()
    controller = make_controller(options.app, directory, language_path)
    controller.isolated = options.isolated
    if options.language:
        controller.language = options.language
    engine = QQmlApplicationEngine()
    if options.app in ("music", "video"):
        from .media import FrameImages

        engine.addImageProvider("video", FrameImages(controller))
    if options.app == "reader":
        from .reader import PdfImages

        engine.addImageProvider("pdf", PdfImages(controller))
    errors = []
    engine.warnings.connect(lambda warnings: errors.extend(w.toString() for w in warnings))
    engine.rootContext().setContextProperty("controller", controller)
    engine.rootContext().setContextProperty("windowed", options.windowed or options.isolated)
    engine.load(QUrl.fromLocalFile(str(Path(__file__).with_name("qml") / "Main.qml")))
    if not engine.rootObjects():
        controller.close()
        return 2
    window = engine.rootObjects()[0]
    window.setWidth(max(800, options.width))
    window.setHeight(max(500, options.height))
    controller.window = window
    def show():
        window.showNormal() if options.windowed or options.isolated else window.showFullScreen()
        window.raise_()
        window.requestActivate()
        message = QDBusMessage.createMethodCall("io.github.zhubby.uDeck", "/io/github/zhubby/uDeck",
                                                "io.github.zhubby.uDeck.Control", "ActivateNativeApp")
        message.setArguments([app_id])
        if not options.isolated:
            bus.asyncCall(message)
    controller.present.connect(show)
    controller.closed.connect(application.quit)
    if not options.isolated and not options.no_input and sys.platform == "linux":
        from .input import AppInput

        controller.inputs = AppInput(controller, app_id, ConfigStore().data["input"])
        window.activeChanged.connect(lambda: controller.inputs.set_foreground(window.isActive()))
        controller.inputs.set_foreground(window.isActive())
    control = AppControl(controller, show, errors, time.monotonic())
    if registered:
        bus.registerObject(path, interface, control, QDBusConnection.RegisterOption.ExportAllSlots)
    for source in options.source:
        controller.attempt(lambda source=source: controller.library.add(source))
    controller.start()
    if options.files:
        controller.attempt(lambda: control.open_files(options.files))
    if options.command:
        controller.command(options.command)
    show()
    def smoke():
        for index in range(len(controller.tabs())):
            controller.setTab(index)
            for action in ("down", "right", "up", "left", "context", "back", "quick-settings", "back"):
                controller.dispatch(action)
        controller.setTab(0)
        print(json.dumps({"smoke": "failed" if errors else "passed", "qmlErrors": errors,
                           "app": options.app}, ensure_ascii=False), flush=True)
    if options.smoke_test:
        QTimer.singleShot(1200, smoke)
    if options.screenshot:
        def capture():
            options.screenshot.parent.mkdir(parents=True, exist_ok=True)
            if not window.grabWindow().save(str(options.screenshot)):
                errors.append("Screenshot failed")
        QTimer.singleShot(1700, capture)
    if options.quit_after or options.smoke_test:
        QTimer.singleShot(int((options.quit_after or 2.5) * 1000), application.quit)
    result = application.exec()
    # Destroy engine views before their Python controllers and media/PDF objects.
    controller.close()
    window.setProperty("allowClose", True)
    window.close()
    # Delete the QObject tree even while Python closures retain window wrappers.
    # WebEngine's profile must finish shutdown before isolated state is removed.
    delete(engine)
    if registered:
        bus.unregisterObject(path)
        bus.unregisterService(service)
    if temporary:
        temporary.cleanup()
    return 2 if errors else result


def music():
    return main(["music", *sys.argv[1:]])


def video():
    return main(["video", *sys.argv[1:]])


def browser():
    return main(["browser", *sys.argv[1:]])


def reader():
    return main(["reader", *sys.argv[1:]])


def games():
    return main(["games", *sys.argv[1:]])


if __name__ == "__main__":
    raise SystemExit(main())
