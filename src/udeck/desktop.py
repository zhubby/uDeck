"""
[INPUT]: 依赖桌面元数据、内置应用身份与 Python 模块入口。
[OUTPUT]: 提供应用索引、Exec 解析和固定内置应用启动。
[POS]: 桌面启动底层；元数据不能替换内置启动命令。
[PROTOCOL]: Update this header on change, then check AGENTS.md
"""

import configparser
import locale as system_locale
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

from .app_routing import APP_IDS, native_app_id
from .i18n import Msg, tr


def open_terminal(directory):
    directory = Path(directory).absolute()
    if not directory.is_dir():
        raise ValueError(tr(Msg.THE_TERMINAL_WORKING_DIRECTORY_DOES_NOT_EXIST))
    # 显式目录强制新建原生终端窗口，绕过系统默认终端。
    arguments = [sys.executable, "-m", "udeck.terminal.main", "--working-directory", str(directory)]
    return subprocess.Popen(arguments, cwd=str(directory), start_new_session=True)


def parse_exec(command, name="", icon="", desktop_path="", files=()):
    result = []
    paths = [str(Path(path).absolute()) for path in files]
    substitutions = {"%": "%", "c": name, "k": desktop_path,
                     "f": paths[0] if paths else "", "F": paths[0] if paths else "",
                     "u": Path(paths[0]).as_uri() if paths else "", "U": Path(paths[0]).as_uri() if paths else ""}
    for token in shlex.split(command):
        if token in ("%f", "%F", "%u", "%U"):
            values = [Path(path).as_uri() for path in paths] if token in ("%u", "%U") else paths
            result.extend(values[:1] if token in ("%f", "%u") else values)
            continue
        if token in ("%f", "%F", "%u", "%U", "%d", "%D", "%n", "%N", "%v", "%m"):
            continue
        if token == "%i":
            if icon:
                result.extend(("--icon", icon))
            continue
        result.append(re.sub(r"%([%ckfFuU])", lambda match: substitutions[match[1]], token))
    if not result:
        raise ValueError(tr(Msg.THE_APP_HAS_NO_EXECUTABLE_COMMAND))
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
                    comment = next((section[f"Comment[{key}]"] for key in locale_keys if f"Comment[{key}]" in section), section.get("Comment", ""))
                    categories = section.get("Categories", "").split(";")
                    category = next((value for value in categories if value in ("Development", "Game", "Graphics", "Network", "Office", "AudioVideo", "System", "Utility")), "Other")
                    entries.append({
                        "id": identifier, "name": name, "subtitle": comment,
                        "icon": section.get("Icon", "application-x-executable"),
                        "startupWMClass": section.get("StartupWMClass", ""),
                        "category": category, "desktop": str(path), "exec": section.get("Exec", ""),
                        "terminal": section.get("Terminal", "false").lower() == "true",
                        "workingDirectory": section.get("Path", ""),
                        "mimeTypes": list(filter(None, section.get("MimeType", "").split(";"))),
                    })
                except (OSError, KeyError, ValueError, configparser.Error):
                    continue
        self.by_id = {entry["id"]: entry for entry in entries}
        return sorted(entries, key=lambda entry: entry["name"].casefold())

    def handlers(self, mime):
        aliases = {"audio/wav": "audio/x-wav", "audio/flac": "audio/x-flac"}
        accepted = {mime, aliases.get(mime, mime), mime.split("/")[0] + "/*"}
        if mime.startswith("text/"):
            accepted.add("text/plain")
        return sorted((entry for entry in self.by_id.values() if accepted.intersection(entry.get("mimeTypes", []))),
                      key=lambda entry: entry["name"].casefold())

    def launch(self, identifier, files=()):
        app_id = native_app_id(identifier)
        if app_id is None:
            raise ValueError(tr(Msg.EXTERNAL_APPLICATIONS_DISABLED))
        if app_id.endswith(".Terminal"):
            if files:
                raise ValueError(tr(Msg.EXTERNAL_APPLICATIONS_DISABLED))
            arguments = [sys.executable, "-m", "udeck.terminal.main"]
        else:
            name = next(name for name, value in APP_IDS.items() if value == app_id)
            arguments = [sys.executable, "-m", "udeck.apps.main", name,
                         *(str(Path(path).absolute()) for path in files)]
        subprocess.Popen(arguments, start_new_session=True)
