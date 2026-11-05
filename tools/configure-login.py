#!/usr/bin/env python3
import argparse
import configparser
import json
import os
import pwd
import re
import shutil
import stat
import tempfile
import uuid
from pathlib import Path


def _append_settings(lines, settings):
    if lines and not lines[-1].endswith("\n"):
        lines[-1] += "\n"
    lines.extend(f"{key}={value}\n" for key, value in settings.items())
    settings.clear()


def render_config(contents, username):
    if not re.fullmatch(r"[a-z_][a-z0-9_-]*\$?", username):
        raise ValueError("Invalid login username")
    settings = {"user-session": "udeck", "autologin-user": username,
                "autologin-session": "udeck", "autologin-user-timeout": "0"}
    parser = configparser.ConfigParser(interpolation=None)
    parser.read_string(contents)
    for section in parser.sections():
        if section.startswith("Seat:") and section != "Seat:*" and settings.keys() & parser[section].keys():
            raise ValueError(f"Explicit {section} login overrides must be reviewed first")
    section = ""
    found = False
    lines = []
    for line in contents.splitlines(keepends=True):
        header = re.fullmatch(r"\s*\[([^]]+)\]\s*(?:[#;].*)?", line.strip())
        if header:
            if section == "Seat:*":
                _append_settings(lines, settings)
            section = header.group(1)
            found = found or section == "Seat:*"
        assignment = re.match(r"\s*([A-Za-z-]+)\s*=", line)
        key = assignment.group(1).lower() if assignment else ""
        if section == "Seat:*" and key in settings:
            lines.append(f"{key}={settings.pop(key)}\n")
        else:
            lines.append(line)
    if not found:
        _append_settings(lines, {})
        lines.append("[Seat:*]\n")
    _append_settings(lines, settings)
    return "".join(lines)


def configure_login(config, backups, username):
    if config.is_symlink() or not config.is_file():
        raise ValueError("LightDM configuration must be a regular file, not a symbolic link")
    original = config.read_bytes()
    updated = render_config(original.decode(), username).encode()
    if updated == original:
        return {"changed": False, "session": "udeck", "user": username}
    metadata = config.stat()
    backups.mkdir(parents=True, exist_ok=True, mode=0o700)
    backup = backups / f"lightdm-before-udeck-{uuid.uuid4().hex}.conf"
    shutil.copy2(config, backup)
    descriptor, temporary = tempfile.mkstemp(prefix=".udeck-login-", dir=config.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(updated)
            stream.flush()
            if os.geteuid() == 0:
                os.fchown(stream.fileno(), metadata.st_uid, metadata.st_gid)
            os.fchmod(stream.fileno(), stat.S_IMODE(metadata.st_mode))
            os.fsync(stream.fileno())
        os.replace(temporary, config)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return {"changed": True, "session": "udeck", "user": username, "backup": str(backup),
            "activation": "next graphical login; no logout or reboot performed"}


def main():
    parser = argparse.ArgumentParser(description="Explicitly enable uDeck automatic login after backing up LightDM configuration")
    parser.add_argument("--user", required=True)
    options = parser.parse_args()
    if os.geteuid() != 0:
        parser.error("Run this opt-in configuration tool with sudo")
    try:
        account = pwd.getpwnam(options.user)
        if account.pw_uid == 0:
            raise ValueError("The desktop must not run as root")
        if not Path("/usr/share/wayland-sessions/udeck.desktop").is_file() or not os.access("/usr/bin/udeck-session", os.X_OK):
            raise ValueError("Install the uDeck session before changing login defaults")
        result = configure_login(Path("/etc/lightdm/lightdm.conf"), Path("/var/backups/udeck"), options.user)
    except (KeyError, OSError, ValueError, configparser.Error) as error:
        parser.error(str(error))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
