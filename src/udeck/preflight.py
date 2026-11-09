#!/usr/bin/env python3
"""Read-only CM4 compatibility check; also runs standalone on the old Python 3.9 image."""

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit

# Package availability is separate from image compatibility: APT installs missing dependencies.
REQUIRED_PACKAGES = (
    "python3-dbus-next", "python3-evdev", "python3-gi", "python3-pyside6.qtquick",
    "python3-pyside6.qtqml", "python3-pyside6.qtdbus", "python3-pyside6.qtmultimedia",
    "python3-pyside6.qtquickcontrols2", "qml6-module-qtquick", "qml6-module-qtquick-controls",
    "qml6-module-qtquick-layouts", "qml6-module-qtquick-window", "qml6-module-qtqml-workerscript",
    "qml6-module-qtquick-templates", "qt6-svg-plugins", "qt6-wayland", "labwc", "xwayland",
    "wlr-randr", "libwayland-client0", "libxkbcommon0", "xkb-data", "procps", "network-manager", "wpasupplicant",
    "dnsmasq-base", "nftables", "bluez", "systemd", "libpam-systemd", "tzdata", "pipewire-audio",
    "pulseaudio-utils", "libglib2.0-bin", "gvfs", "udisks2", "swayidle", "swaylock", "wlopm",
    "fcitx5", "fcitx5-frontend-qt6", "fcitx5-pinyin", "lxpolkit", "dbus-user-session",
    "xdg-desktop-portal-wlr", "xdg-desktop-portal-gtk", "fonts-noto-cjk", "xdg-terminal-exec",
    "xdg-utils", "shared-mime-info", "hicolor-icon-theme", "python3-pyside6.qtwidgets",
    "python3-pyside6.qttest", "python3-pyside6.qtwebenginequick", "python3-pyside6.qtwebenginecore",
    "python3-pyside6.qtpdf", "qml6-module-qtmultimedia", "qml6-module-qtwebengine",
    "ffmpeg", "ca-certificates", "libutempter0",
)


def command(arguments):
    try:
        result = subprocess.run(arguments, capture_output=True, text=True, timeout=8, check=False)
        return result.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""


def assess_system(os_release, architecture, python_version):
    fields = {}
    for line in os_release.splitlines():
        key, separator, value = line.partition("=")
        if separator:
            fields[key] = value.strip().strip('\"\'')
    errors = []
    if fields.get("ID") not in ("debian", "raspbian"):
        errors.append("Use the Debian / Raspberry Pi OS based official CM4 v3.1 image.")
    if fields.get("VERSION_CODENAME") != "trixie":
        errors.append("Debian 13 (trixie) is required. Back up the old XFCE image and migrate to CM4 v3.1.")
    if architecture != "arm64":
        errors.append("The release supports arm64 userspace; a 64-bit kernel alone is insufficient.")
    if not (3, 11) <= tuple(python_version[:2]) < (3, 14):
        errors.append("Python 3.11 through 3.13 is required; do not replace the system Python in place.")
    return {"supported": not errors, "distribution": fields, "architecture": architecture,
            "python": ".".join(map(str, python_version)), "errors": errors}


def assess_packages(versions):
    missing = sorted(set(REQUIRED_PACKAGES) - versions.keys())
    incompatible = {}
    for name, value in versions.items():
        match = re.match(r"(?:\d+:)?(\d+)\.(\d+)", value)
        version = tuple(map(int, match.groups())) if match else ()
        if name.startswith("python3-pyside6.") and version != (6, 8):
            incompatible[name] = value
        if name == "labwc" and version < (0, 9):
            incompatible[name] = value
    return {"versions": versions, "missing": missing, "incompatible": incompatible,
            "ready": not missing and not incompatible}


def collect_report():
    try:
        os_release = Path("/etc/os-release").read_text()
    except OSError:
        os_release = ""
    architecture = command(["dpkg", "--print-architecture"]) or platform.machine()
    report = assess_system(os_release, architecture, sys.version_info[:3])
    packages = command(["dpkg-query", "-W", "-f=${Package}\t${Version}\t${db:Status-Status}\n"])
    versions = {}
    observed = set(REQUIRED_PACKAGES) | {"udeck", "udeck-shell", "udeck-terminal", "udeck-apps",
                                       "libspa-0.2-bluetooth", "wireplumber", "pipewire-pulse"}
    for line in packages.splitlines():
        fields = line.split("\t")
        if len(fields) == 3 and fields[2] == "installed" and fields[0] in observed:
            versions[fields[0]] = fields[1]
    report["packages"] = assess_packages(versions)
    report["rpiBacklightCommand"] = shutil.which("rpi-backlight")
    report["backlights"] = [{"path": str(path), "writable": os.access(path / "brightness", os.W_OK)}
                            for path in sorted(Path("/sys/class/backlight").glob("*"))]
    sources = [Path("/etc/apt/sources.list"), *sorted(Path("/etc/apt/sources.list.d").glob("*.list")),
               *sorted(Path("/etc/apt/sources.list.d").glob("*.sources"))]
    # Only source hosts/codenames are reported: no embedded credentials or query strings.
    hosts = set()
    suites = set()
    for source in sources:
        try:
            text = source.read_text()
        except OSError:
            continue
        for url in re.findall(r"https?://[^\s]+", text):
            try:
                hosts.add(urlsplit(url).hostname)
            except ValueError:
                continue
        suites.update(re.findall(r"\b(?:bullseye|bookworm|trixie)(?:-[a-z]+)?\b", text))
    report["aptSources"] = {"hosts": sorted(host for host in hosts if host), "suites": sorted(suites)}
    report["physicalAcceptance"] = "Not checked: physical keys, display, IME, audio, power and original-session recovery."
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--check-installed", action="store_true", help="Also require desktop runtime packages")
    options = parser.parse_args(argv)
    report = collect_report()
    ready = report["supported"] and (not options.check_installed or report["packages"]["ready"])
    if options.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print("Supported system: " + ("yes" if report["supported"] else "no"))
        for error in report["errors"]:
            print(error)
        print("Missing desktop packages: " + (", ".join(report["packages"]["missing"]) or "none"))
        print("Incompatible versions: " + (json.dumps(report["packages"]["incompatible"]) if report["packages"]["incompatible"] else "none"))
        print("APT must provide Qt 6.8 and labwc >= 0.9; use the CM4 v3.1 image's Raspberry Pi sources.")
    return 0 if ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
