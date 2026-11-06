import configparser
import locale as system_locale
import os
import pwd
import shlex
import shutil
import subprocess
from pathlib import Path


def terminal_command(arguments=None):
    resolver = shutil.which("xdg-terminal-exec")
    if resolver:
        return [resolver, "--", *arguments] if arguments else [resolver]
    terminal = shutil.which("x-terminal-emulator")
    if not terminal:
        raise RuntimeError("没有可用的默认终端，请安装 xdg-terminal-exec 或终端模拟器")
    return [terminal, "-e", *arguments] if arguments else [terminal]


def open_terminal(directory):
    directory = Path(directory).absolute()
    if not directory.is_dir():
        raise ValueError("终端工作目录不存在")
    # An explicit directory/command must create a window even when the terminal
    # primary already exists; a plain launch only activates its recent window.
    resolver = shutil.which("xdg-terminal-exec")
    arguments = [resolver, "--dir=" + str(directory)] if resolver else terminal_command([pwd.getpwuid(os.getuid()).pw_shell or "/bin/sh"])
    return subprocess.Popen(arguments, cwd=str(directory), start_new_session=True)


def parse_exec(command, name="", icon="", desktop_path=""):
    result = []
    for token in shlex.split(command):
        if token in ("%f", "%F", "%u", "%U", "%d", "%D", "%n", "%N", "%v", "%m"):
            continue
        if token == "%i":
            if icon:
                result.extend(("--icon", icon))
            continue
        token = token.replace("%%", "\x00").replace("%c", name).replace("%k", desktop_path)
        for field in ("%f", "%F", "%u", "%U"):
            token = token.replace(field, "")
        result.append(token.replace("\x00", "%"))
    if not result:
        raise ValueError("应用没有可执行命令")
    return result


class DesktopCatalog:
    def __init__(self, directories=None, locale=None):
        data_home = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share")))
        data_directories = os.environ.get("XDG_DATA_DIRS", "/usr/local/share:/usr/share").split(":")
        self.directories = directories or [data_home / "applications"] + [
            Path(directory) / "applications" for directory in data_directories
        ]
        self.locale = locale or (system_locale.getlocale()[0] or "en_US")
        self.by_id = {}

    def entries(self):
        entries = []
        seen = set()
        current_desktops = set(os.environ.get("XDG_CURRENT_DESKTOP", "uDeck:labwc").split(":"))
        for directory in self.directories:
            directory = Path(directory)
            for path in sorted(directory.rglob("*.desktop")):
                identifier = str(path.relative_to(directory)).replace(os.sep, "-")
                if identifier in seen or identifier == "io.github.zhubby.uDeck.desktop":
                    continue
                seen.add(identifier)
                parser = configparser.ConfigParser(interpolation=None, strict=False)
                parser.optionxform = str
                try:
                    parser.read(path, encoding="utf-8")
                    section = parser["Desktop Entry"]
                    if any(section.get(field, "false").lower() == "true" for field in ("Hidden", "NoDisplay")):
                        continue
                    if section.get("Type") != "Application" or (not section.get("Exec") and section.get("DBusActivatable", "false").lower() != "true"):
                        continue
                    only = set(filter(None, section.get("OnlyShowIn", "").split(";")))
                    excluded = set(filter(None, section.get("NotShowIn", "").split(";")))
                    if (only and not only & current_desktops) or excluded & current_desktops:
                        continue
                    if section.get("TryExec") and not shutil.which(section["TryExec"]):
                        continue
                    locale_keys = [self.locale, self.locale.split("_")[0]]
                    name = next((section[f"Name[{key}]"] for key in locale_keys if f"Name[{key}]" in section), section.get("Name", path.stem))
                    categories = section.get("Categories", "").split(";")
                    category = next((value for value in categories if value in ("Development", "Game", "Graphics", "Network", "Office", "AudioVideo", "System", "Utility")), "Other")
                    entries.append({
                        "id": identifier, "name": name, "subtitle": section.get("Comment", ""),
                        "icon": section.get("Icon", "application-x-executable"),
                        "category": category, "desktop": str(path), "exec": section.get("Exec", ""),
                        "terminal": section.get("Terminal", "false").lower() == "true",
                        "workingDirectory": section.get("Path", ""),
                    })
                except (OSError, KeyError, ValueError, configparser.Error):
                    continue
        self.by_id = {entry["id"]: entry for entry in entries}
        return sorted(entries, key=lambda entry: entry["name"].casefold())

    def launch(self, identifier):
        entry = self.by_id[identifier]
        try:
            import gi

            gi.require_version("Gio", "2.0")
            from gi.repository import Gio

            application = Gio.DesktopAppInfo.new_from_filename(entry["desktop"])
            if application is None or not application.launch([], None):
                raise RuntimeError("系统拒绝启动应用")
        except ImportError:
            arguments = parse_exec(entry["exec"], entry["name"], entry["icon"], entry["desktop"])
            if entry["terminal"]:
                arguments = terminal_command(arguments)
            subprocess.Popen(arguments, cwd=entry["workingDirectory"] or None, start_new_session=True)
