#!/usr/bin/env python3
"""Exercise real packages in a disposable Debian arm64 container (run as root)."""

import argparse
import hashlib
import io
import json
import os
import subprocess
import tarfile
import tempfile
from pathlib import Path


def run(arguments, **options):
    return subprocess.run(arguments, check=True, text=True, **options)


def verify_packages(packages):
    result = run(["dpkg", "--verify", *packages], capture_output=True)
    assert not result.stdout.strip(), result.stdout


def obsolete_installation(destination):
    """Disposable old-name sentinels; exercise removal, not payload migration."""
    archives = []
    for name in ("udeck", "udeck-shell", "udeck-terminal", "udeck-apps"):
        stage = destination / name
        (stage / "DEBIAN").mkdir(parents=True, mode=0o755)
        (stage / "DEBIAN/control").write_text(
            f"Package: {name}\nVersion: 0.0.1\nArchitecture: all\n"
            "Maintainer: uDeck test <test@example.invalid>\nDescription: Disposable old-package sentinel\n")
        payload = stage / "usr/share/udeck-obsolete" / name
        payload.parent.mkdir(parents=True)
        payload.write_text("must be removed before installing udeck\n")
        archive = destination / (name + ".deb")
        run(["dpkg-deb", "--root-owner-group", "--build", str(stage), str(archive)])
        archives.append(str(archive))
    return archives


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
    assert set(packages) == {"udeck"}
    assert "qt6-svg-plugins" in subprocess.check_output(
        ["dpkg-deb", "--field", str(packages["udeck"]), "Depends"], text=True)
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
    system_list = Path("/etc/xdg/xdg-terminals.list")
    system_list.parent.mkdir(parents=True, exist_ok=True)
    system_list.write_text("# keep system preferences\noriginal-terminal.desktop\n")
    original_list = system_list.read_bytes()

    def unchanged():
        assert all(path.read_bytes() == data for path, data in preserved.items())

    def defaults_enabled():
        assert terminal_selection() == ["Status: manual", "Value: /usr/bin/udeck-terminal"]
        assert system_list.read_text().splitlines()[0] == "io.github.zhubby.uDeck.Terminal.desktop"
        assert not Path("/usr/bin/udeck-games").exists()

    def defaults_removed():
        assert terminal_selection() == terminal_default
        assert system_list.read_bytes() == original_list
        assert not Path("/etc/xdg/udeck-xdg-terminals.list").exists()
        assert not Path("/var/lib/udeck-terminal/system-defaults.json").exists()

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
        # Ask for only udeck, with no recommendations masking required dependencies.
        run(["apt-get", "install", "-y", "--no-install-recommends", "udeck=" + version])
        unchanged()
        defaults_enabled()
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
        for app in ("music", "video", "browser", "reader", "emulator"):
            run(["udeck-" + app, "--isolated", "--smoke-test"], env=env)
            run(["dbus-run-session", "--", "python3", "-I", str(Path(__file__).with_name("apps_ipc_probe.py")),
                 app, str(temporary / "ipc" / app)], env=env, timeout=45)
        marker = temporary / "installed-terminal.txt"
        run(["dbus-run-session", "--", "udeck-terminal", "--no-input", "--windowed", "--quit-after", "3",
             "-e", "/usr/bin/python3", "-c",
             "import sys,time; from pathlib import Path; Path(sys.argv[1]).write_text('installed PTY'); time.sleep(30)",
             str(marker)], env={**env, "XDG_CONFIG_HOME": str(temporary / "terminal-config")}, timeout=30)
        assert marker.read_text() == "installed PTY"
        for command, desktop in (("x-terminal-emulator", ""), ("xdg-terminal-exec", ""),
                                 ("xdg-terminal-exec", "uDeck")):
            marker = temporary / (command + ("-" + desktop if desktop else "") + ".json")
            child = ["/usr/bin/python3", "-c",
                     "import json,os,sys; from pathlib import Path; "
                     "maps=Path('/proc/%s/maps' % os.getppid()).read_text(); "
                     "Path(sys.argv[1]).write_text(json.dumps({'stdinIsTty':os.isatty(0), "
                     "'stdoutIsTty':os.isatty(1), 'udeckPlugin': "
                     "'/usr/lib/udeck-terminal/qml/QMLTermWidget/libqmltermwidget.so' in maps}))",
                     str(marker)]
            arguments = ([command, "--no-input", "--windowed", "--quit-after", "3", "-e", *child]
                         if command == "x-terminal-emulator" else [command, *child])
            run(["dbus-run-session", "--", *arguments], env={**env, "XDG_CURRENT_DESKTOP": desktop}, timeout=30)
            assert json.loads(marker.read_text()) == {
                "stdinIsTty": True, "stdoutIsTty": True, "udeckPlugin": True}, (command, desktop)
        probe = Path(__file__).with_name("native_terminal_probe.py")
        (temporary / "native").mkdir()
        run(["python3", "-I", str(probe), "/usr/lib/udeck-terminal/qml", str(temporary / "native")], env=env)
        # Check the source archive corresponds to installed Python/QML/resources, not just filenames.
        source = temporary / "source"
        run(["dpkg-source", "--extract", str(next(release.glob("*.dsc"))), str(source)])
        for name in ("uv.lock", ".python-version"):
            assert (source / name).read_bytes() == (Path(__file__).resolve().parents[1] / name).read_bytes(), name
        checked = 0
        package = Path("/usr/lib/python3/dist-packages/udeck")
        for path in package.rglob("*"):
            if path.is_file() and "__pycache__" not in path.parts:
                original = source / "src/udeck" / path.relative_to(package)
                assert original.read_bytes() == path.read_bytes(), path
                checked += 1
        for name, template in (("udeck", "terminal.colorscheme"), ("udeck-dark", "terminal-dark.colorscheme")):
            palette = plugin.parent / "color-schemes" / (name + ".colorscheme")
            assert palette.read_bytes() == (source / "packaging" / template).read_bytes()
        # An automatic preference should follow newly installed alternatives.
        newer_terminal = Path("/usr/local/bin/udeck-test-new-terminal")
        newer_terminal.write_text("#!/bin/sh\nexit 0\n")
        newer_terminal.chmod(0o755)
        run(["update-alternatives", "--install", "/usr/bin/x-terminal-emulator", "x-terminal-emulator",
             str(newer_terminal), "100"])
        terminal_default = ["Status: auto", "Value: " + str(newer_terminal)]
        run(["apt-get", "remove", "-y", *packages])
        unchanged()
        defaults_removed()
        obsolete = temporary / "obsolete"
        obsolete.mkdir()
        run(["apt-get", "install", "-y", "--no-install-recommends", *obsolete_installation(obsolete)])
        unchanged()
        # The real installer explicitly removes old packages before installing.
        apt_config = temporary / "apt-unattended.conf"
        apt_config.write_text('APT::Get::Assume-Yes "true";\n')
        run(["sh", str(release / "install.sh")], env={**os.environ, "APT_CONFIG": str(apt_config)})
        assert not Path("/usr/share/udeck-obsolete").exists()
        for name in ("udeck-shell", "udeck-terminal", "udeck-apps"):
            result = subprocess.run(["dpkg-query", "-W", "-f=${db:Status-Status}", name],
                                    text=True, capture_output=True)
            assert result.stdout != "installed", name
        verify_packages(packages)
        unchanged()
        defaults_enabled()
        run(["dpkg-reconfigure", "-f", "noninteractive", "udeck"])
        defaults_enabled()
        run(["apt-get", "install", "-y", "--reinstall", "--no-install-recommends",
             *(name + "=" + version for name in packages)])
        unchanged()
        defaults_enabled()
        run(["apt-get", "remove", "-y", *packages])
        unchanged()
        defaults_removed()
        run(["apt-get", "install", "-y", "--no-install-recommends", "udeck=" + version])
        unchanged()
        defaults_enabled()
    print(json.dumps({"packageLifecycle": "passed", "installedSourceFilesChecked": checked,
                      "physicalAcceptance": "not checked"}))


if __name__ == "__main__":
    main()
