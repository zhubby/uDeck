#!/usr/bin/env python3
"""Exercise real packages in a disposable Debian arm64 container (run as root)."""

import argparse
import hashlib
import io
import json
import os
import re
import subprocess
import tarfile
import tempfile
from pathlib import Path


def run(arguments, **options):
    return subprocess.run(arguments, check=True, text=True, **options)


def verify_packages(packages):
    result = run(["dpkg", "--verify", *packages], capture_output=True)
    assert not result.stdout.strip(), result.stdout


def legacy_packages(packages, destination):
    """Model the previous udeck payload owner to exercise Breaks/Replaces migration."""
    legacy = []
    for name in ("udeck-shell", "udeck-terminal", "udeck-apps"):
        archive = packages[name]
        stage = destination / name
        run(["dpkg-deb", "--raw-extract", str(archive), str(stage)])
        control = stage / "DEBIAN/control"
        text = control.read_text()
        text = re.sub(r"^Version: .*", "Version: 0.2.1", text, flags=re.M)
        text = re.sub(r"^Breaks: .*\n|^Replaces: .*\n", "", text, flags=re.M)
        text = re.sub(r"udeck-shell \(= [^)]+\)", "udeck (= 0.2.1)", text)
        if name == "udeck-shell":
            text = text.replace("Package: udeck-shell\n", "Package: udeck\n")
        control.write_text(text)
        # The former hand-built shell/apps had no debhelper maintainer scripts.
        # New scripts refer to the new package name and cannot be reused as old ones.
        for script in ("postinst", "prerm", "postrm"):
            (stage / "DEBIAN" / script).unlink(missing_ok=True)
        output = destination / (name + "-legacy.deb")
        run(["dpkg-deb", "--root-owner-group", "--build", str(stage), str(output)])
        legacy.append(output)
    return legacy


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("release", type=Path)
    options = parser.parse_args()
    release = options.release.resolve()
    if os.geteuid() != 0 or not Path("/.dockerenv").exists():
        raise SystemExit("Run only inside a disposable root-owned Docker container")
    run(["sha256sum", "--check", "SHA256SUMS"], cwd=release)
    packages = {}
    owned = set()
    for archive in sorted(release.glob("*.deb")):
        name = subprocess.check_output(["dpkg-deb", "--field", str(archive), "Package"], text=True).strip()
        packages[name] = archive
        data = subprocess.check_output(["dpkg-deb", "--fsys-tarfile", str(archive)])
        with tarfile.open(fileobj=io.BytesIO(data)) as stream:
            members = {entry.name for entry in stream.getmembers() if not entry.isdir()}
        assert not owned & members, f"Duplicate package file ownership: {owned & members}"
        assert not any(path.startswith(("./etc/", "./home/", "./root/", "./boot/")) for path in members)
        owned.update(members)
    assert set(packages) == {"udeck", "udeck-shell", "udeck-terminal", "udeck-apps"}
    assert "qt6-svg-plugins" in subprocess.check_output(
        ["dpkg-deb", "--field", str(packages["udeck-shell"]), "Depends"], text=True)
    # Existing login, desktop and application data must survive every lifecycle operation.
    preserved = {
        Path("/etc/lightdm/lightdm.conf"): b"[Seat:*]\nuser-session=original-desktop\n",
        Path("/root/.config/labwc/rc.xml"): b"<labwc_config/>\n",
        Path("/root/.config/udeck/settings.json"): b'{"testSentinel":"preserve-user-data"}\n',
    }
    for path, data in preserved.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    original_terminal = Path("/usr/local/bin/udeck-test-original-terminal")
    original_terminal.write_text("#!/bin/sh\nexit 0\n")
    original_terminal.chmod(0o755)
    run(["update-alternatives", "--install", "/usr/bin/x-terminal-emulator", "x-terminal-emulator",
         str(original_terminal), "50"])
    def terminal_selection():
        query = subprocess.check_output(["update-alternatives", "--query", "x-terminal-emulator"], text=True)
        return [line for line in query.splitlines() if line.startswith(("Status:", "Value:"))]

    terminal_default = terminal_selection()

    def unchanged():
        assert all(path.read_bytes() == data for path, data in preserved.items())
        assert terminal_selection() == terminal_default

    with tempfile.TemporaryDirectory(prefix="udeck-package-test-") as temporary:
        temporary = Path(temporary)
        temporary.chmod(0o755)
        repository = temporary / "repository"
        repository.mkdir(mode=0o755)
        for archive in packages.values():
            (repository / archive.name).write_bytes(archive.read_bytes())
        index = subprocess.check_output(["dpkg-scanpackages", ".", "/dev/null"], cwd=repository)
        (repository / "Packages").write_bytes(index)
        Path("/etc/apt/sources.list.d/udeck-local-test.list").write_text(
            f"deb [trusted=yes] file:{repository} ./\n")
        version = subprocess.check_output(["dpkg-deb", "--field", str(packages["udeck"]), "Version"], text=True).strip()
        run(["apt-get", "update"])
        # Ask for only udeck: its Depends must pull in the whole suite.
        run(["apt-get", "install", "-y", "--no-install-recommends", "udeck=" + version])
        unchanged()
        for name in packages:
            installed = subprocess.check_output(["dpkg-query", "-W", "-f=${Version}", name], text=True)
            assert installed == version
        run(["udeck-preflight", "--check-installed", "--json"])
        verify_packages(packages)
        info = json.loads(Path("/usr/share/udeck-terminal/build-info.json").read_text())
        plugin = Path("/usr/lib/udeck-terminal/qml/QMLTermWidget/libqmltermwidget.so")
        assert hashlib.sha256(plugin.read_bytes()).hexdigest() == info["pluginSha256"]
        env = {**os.environ, "QT_QPA_PLATFORM": "offscreen", "QT_QUICK_BACKEND": "software",
               "QT_QUICK_CONTROLS_STYLE": "Basic", "QTWEBENGINE_DISABLE_SANDBOX": "1"}
        env.pop("PYTHONPATH", None)
        run(["udeck", "--mock", "--windowed", "--smoke-test"], env=env)
        for app in ("music", "video", "browser", "reader", "games"):
            run(["udeck-app", app, "--isolated", "--smoke-test"], env=env)
        marker = temporary / "installed-terminal.txt"
        run(["dbus-run-session", "--", "udeck-terminal", "--no-input", "--windowed", "--quit-after", "3",
             "-e", "/usr/bin/python3", "-c",
             "import sys,time; from pathlib import Path; Path(sys.argv[1]).write_text('installed PTY'); time.sleep(30)",
             str(marker)], env={**env, "XDG_CONFIG_HOME": str(temporary / "terminal-config")}, timeout=30)
        assert marker.read_text() == "installed PTY"
        probe = Path(__file__).with_name("native_terminal_probe.py")
        (temporary / "native").mkdir()
        run(["python3", "-I", str(probe), "/usr/lib/udeck-terminal/qml", str(temporary / "native")], env=env)
        # Check the source archive corresponds to installed Python/QML/resources, not just filenames.
        source = temporary / "source"
        run(["dpkg-source", "--extract", str(next(release.glob("*.dsc"))), str(source)])
        checked = 0
        package = Path("/usr/lib/python3/dist-packages/udeck")
        for path in package.rglob("*"):
            if path.is_file() and "__pycache__" not in path.parts:
                original = source / "src/udeck" / path.relative_to(package)
                assert original.read_bytes() == path.read_bytes(), path
                checked += 1
        run(["apt-get", "remove", "-y", *packages])
        unchanged()
        old = legacy_packages(packages, temporary)
        run(["apt-get", "install", "-y", "--no-install-recommends", *map(str, old)])
        unchanged()
        run(["apt-get", "install", "-y", "--no-install-recommends", "udeck=" + version])
        verify_packages(packages)
        unchanged()
        run(["apt-get", "install", "-y", "--reinstall", "--no-install-recommends",
             *(name + "=" + version for name in packages)])
        unchanged()
        run(["apt-get", "remove", "-y", *packages])
        unchanged()
        run(["apt-get", "install", "-y", "--no-install-recommends", "udeck=" + version])
        unchanged()
    print(json.dumps({"packageLifecycle": "passed", "installedSourceFilesChecked": checked,
                      "physicalAcceptance": "not checked"}))


if __name__ == "__main__":
    main()
