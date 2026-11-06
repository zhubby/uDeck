"""Real Debian alternatives/XDG/Gio rehearsal isolated from live defaults."""

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from udeck.terminal.defaults import DebianAlternatives, DefaultManager

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--output", type=Path, required=True)
options = parser.parse_args()
live = DebianAlternatives().query()
report = {"liveDefaultsBefore": live, "checks": {},
          "buildId": json.loads(Path("/usr/share/udeck-terminal/build-info.json").read_text())["buildId"]}
with tempfile.TemporaryDirectory(prefix="udeck-default-rehearsal-") as temporary:
    directory = Path(temporary)
    links, admin, generic = directory / "links", directory / "admin", directory / "bin"
    links.mkdir()
    admin.mkdir()
    generic.mkdir()

    class IsolatedAlternatives(DebianAlternatives):
        @staticmethod
        def _run(*arguments):
            replacements = {"/usr/bin/x-terminal-emulator": str(generic / "x-terminal-emulator"),
                            "/usr/share/man/man1/x-terminal-emulator.1.gz": str(generic / "x-terminal-emulator.1.gz")}
            arguments = [replacements.get(value, value) for value in arguments]
            return subprocess.check_output(["update-alternatives", "--altdir", str(links),
                                            "--admindir", str(admin), "--log", str(directory / "alternatives.log"),
                                            *arguments], text=True)

    alternatives = IsolatedAlternatives()
    alternatives._run("--install", str(generic / "x-terminal-emulator"), "x-terminal-emulator", "/usr/bin/lxterminal", "20",
                      "--slave", str(generic / "x-terminal-emulator.1.gz"), "x-terminal-emulator.1.gz", "/usr/share/man/man1/lxterminal.1.gz")
    root = directory / "root"
    manager = DefaultManager(root, Path("/home/probe"), alternatives, uid=os.getuid(), gid=os.getgid())
    config = root / "home/probe/.config"
    binding = config / "labwc/rc.xml"
    binding.parent.mkdir(parents=True)
    original = b'<labwc_config><keybind key="C-A-t"><action name="Execute" command="lxterminal"/></keybind></labwc_config>\n'
    binding.write_bytes(original)
    before = alternatives.query()
    backup = manager.apply()
    assert alternatives.query() == {"status": "manual", "value": "/usr/bin/udeck-terminal", "registered": True}
    assert 'command="x-terminal-emulator"' in binding.read_text()
    report["checks"]["isolated-debian-and-binding-apply"] = "passed"

    launch_env = {**os.environ, "XDG_CONFIG_HOME": str(config), "XDG_CONFIG_DIRS": str(root / "etc/xdg"),
                  "XDG_CACHE_HOME": str(directory / "cache"), "MESA_SHADER_CACHE_DISABLE": "true",
                  "PATH": str(generic) + os.pathsep + os.environ.get("PATH", os.defpath)}
    capture = directory / "capture.py"
    capture.write_text("import json,os,sys\nfrom pathlib import Path\np=Path(f'/proc/{os.getppid()}/cmdline').read_bytes().decode().split(chr(0))\nPath(sys.argv[1]).write_text(json.dumps({'argv':sys.argv[2:],'cwd':os.getcwd(),'parentScript':str(Path(p[1]).resolve())}))\n")
    cwd = directory / '中文 空格 "引号"'
    cwd.mkdir()

    def verify(marker, process=None):
        deadline = time.monotonic() + 15
        while not marker.exists() and time.monotonic() < deadline:
            time.sleep(0.1)
        assert marker.exists(), f"Launch did not execute: {marker}"
        result = json.loads(marker.read_text())
        if process:
            assert process.wait(timeout=10) == 0
        assert result["parentScript"] == "/usr/bin/udeck-terminal", result
        assert result["cwd"] == str(cwd) and result["argv"] == ["中文 空格"], result
        # Give the native shell-exit notification time to close its window.
        time.sleep(0.5)

    for name, prefix in (("alternative", [str(generic / "x-terminal-emulator"), "-e"]),
                          ("xdg-terminal-exec", ["/usr/bin/xdg-terminal-exec", "--"])):
        marker = directory / (name + ".json")
        process = subprocess.Popen([*prefix, sys.executable, str(capture), str(marker), "中文 空格"],
                                   cwd=cwd, env=launch_env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        verify(marker, process)
        report["checks"][name + "-real-launch"] = "passed"

    # Gio has its own Terminal=true resolution; exercise the installed GLib.
    gio_script = directory / "gio.py"
    gio_script.write_text("import gi,sys\ngi.require_version('Gio','2.0')\nfrom gi.repository import Gio\na=Gio.DesktopAppInfo.new_from_filename(sys.argv[1])\nassert a.launch([],None)\n")
    marker = directory / "gio-result.json"
    desktop = directory / "gio.desktop"
    desktop.write_text(f'[Desktop Entry]\nType=Application\nName=uDeck acceptance\nTerminal=true\nPath={cwd}\nExec={sys.executable} {capture} {marker} "中文 空格"\n')
    subprocess.run([sys.executable, str(gio_script), str(desktop)], env=launch_env, check=True)
    verify(marker)
    report["checks"]["gio-terminal-true-real-launch"] = "passed"
    fallback = directory / "fallback.py"
    fallback.write_text("import sys\nfrom pathlib import Path\nsys.modules['gi']=None\nfrom udeck.desktop import DesktopCatalog\nc=DesktopCatalog([Path(sys.argv[1]).parent]);c.entries();c.launch(Path(sys.argv[1]).name)\n")
    marker = directory / "fallback-result.json"
    desktop.write_text(f'[Desktop Entry]\nType=Application\nName=uDeck acceptance\nTerminal=true\nPath={cwd}\nExec={sys.executable} {capture} {marker} "中文 空格"\n')
    subprocess.run([sys.executable, str(fallback), str(desktop)], env=launch_env, check=True)
    verify(marker)
    report["checks"]["missing-gi-fallback-real-launch"] = "passed"
    manager.restore(backup)
    assert alternatives.query() == before
    assert binding.read_bytes() == original
    assert not (config / "xdg-terminals.list").exists()
    report["checks"]["isolated-exact-restore"] = "passed"
assert DebianAlternatives().query() == live
report["liveDefaultsAfter"] = DebianAlternatives().query()
report["result"] = "passed"
options.output.parent.mkdir(parents=True, exist_ok=True)
options.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
print(json.dumps(report, ensure_ascii=False))
