import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path

from . import __version__
from .core import ConfigStore

SERVICE = "io.github.zhubby.uDeck"
OBJECT = "/io/github/zhubby/uDeck"
INTERFACE = SERVICE + ".Control"


def doctor():
    libraries = {name: importlib.util.find_spec(name) is not None for name in ("PySide6", "dbus_next", "evdev")}
    runtime = Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}"))
    display = os.environ.get("WAYLAND_DISPLAY", "wayland-0")
    socket = Path(display) if display.startswith("/") else runtime / display
    profile = ConfigStore().data["input"]
    result = {"version": __version__, "platform": sys.platform, "libraries": libraries,
              "waylandSocket": str(socket), "waylandSocketAvailable": socket.exists(),
              "inputProfileConfigured": bool(profile.get("buttons")),
              "physicalAcceptance": "需要人手验证；设备枚举、映射文件和模拟事件不代表物理验收通过",
              "inputDevices": [], "windowProtocol": False, "runningShell": None}
    if sys.platform == "linux" and libraries["evdev"]:
        from evdev import InputDevice, list_devices

        for path in list_devices():
            device = None
            try:
                device = InputDevice(path)
                if (device.info.vendor, device.info.product) == (0x1EAF, 0x0024):
                    result["inputDevices"].append({"name": device.name, "path": path, "readable": os.access(path, os.R_OK)})
            except OSError:
                continue
            finally:
                if device is not None:
                    device.close()
    if libraries["PySide6"]:
        from PySide6.QtCore import QCoreApplication
        from PySide6.QtDBus import QDBusConnection, QDBusInterface, QDBusMessage

        application = QCoreApplication.instance() or QCoreApplication([])
        interface = QDBusInterface(SERVICE, OBJECT, INTERFACE, QDBusConnection.sessionBus())
        if interface.isValid():
            response = interface.call("Diagnose")
            if response.type() != QDBusMessage.MessageType.ErrorMessage:
                result["runningShell"] = json.loads(response.arguments()[0])
        if sys.platform == "linux" and socket.exists():
            from .windows import WindowService

            windows = WindowService()
            windows.start()
            result["windowProtocol"] = windows.available
            result["protocols"] = windows.globals
            windows.close()
        del application
    result["ready"] = sys.platform == "linux" and all(libraries.values()) and result["windowProtocol"]
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description="uDeck 本机会话控制与只读诊断")
    parser.add_argument("command", choices=("home", "switcher", "quick-settings", "doctor"))
    parser.add_argument("--json", action="store_true", help="输出 JSON 诊断报告")
    options = parser.parse_args(argv)
    if options.command == "doctor":
        report = doctor()
        print(json.dumps(report, ensure_ascii=False, indent=2) if options.json else "\n".join(f"{key}: {value}" for key, value in report.items()))
        return 0 if report["ready"] else 1
    try:
        from PySide6.QtCore import QCoreApplication
        from PySide6.QtDBus import QDBusConnection, QDBusInterface, QDBusMessage

        application = QCoreApplication.instance() or QCoreApplication([])
        interface = QDBusInterface(SERVICE, OBJECT, INTERFACE, QDBusConnection.sessionBus())
        if not interface.isValid():
            raise RuntimeError("当前会话没有运行 uDeck")
        method_name = {"home": "Home", "switcher": "Switcher", "quick-settings": "QuickSettings"}[options.command]
        response = interface.call(method_name)
        if response.type() == QDBusMessage.MessageType.ErrorMessage:
            raise RuntimeError(response.errorMessage())
        del application
        return 0
    except (ImportError, RuntimeError) as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
