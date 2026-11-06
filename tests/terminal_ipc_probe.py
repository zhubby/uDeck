"""Installed CLI/D-Bus acceptance; requires an idle graphical terminal service."""

import argparse
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from udeck.desktop import open_terminal

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--output", type=Path, required=True)
options = parser.parse_args()


def doctor():
    result = subprocess.run(["/usr/bin/udeck-terminal", "--doctor"], capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


def wait(condition, timeout=12):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return
        time.sleep(0.1)
    raise AssertionError("Installed CLI/IPC probe timed out")


assert doctor().get("running") is False, "Close existing terminal windows before this probe"
with tempfile.TemporaryDirectory(prefix="udeck-terminal-ipc-") as temporary:
    directory = Path(temporary)
    cwd = directory / '中文 空格 "引号"'
    cwd.mkdir()
    config = directory / "config"
    config.mkdir()
    (config / "xdg-terminals.list").write_text("io.github.zhubby.uDeck.Terminal.desktop\n")
    os.environ.update(XDG_CONFIG_HOME=str(config), XDG_CONFIG_DIRS=str(directory / "system-config"))
    holder = directory / "holder.py"
    holder.write_text("import time\nfrom pathlib import Path\nPath('ready').touch()\nwhile not Path('finish').exists(): time.sleep(0.1)\n")
    child = directory / "argv.py"
    child.write_text("import json,os,sys,time\nfrom pathlib import Path\nPath('argv.json').write_text(json.dumps({'argv':sys.argv[1:],'cwd':os.getcwd(),'value':os.environ.get('UDECK_PROBE_CALLER')},ensure_ascii=False))\ntime.sleep(2)\n")
    primary = subprocess.Popen(["/usr/bin/udeck-terminal", "--windowed", "--no-input", "--",
                                sys.executable, str(holder)], cwd=directory,
                               stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    try:
        wait(lambda: (directory / "ready").exists())
        assert doctor()["windows"] == 1
        subprocess.run(["/usr/bin/udeck-terminal"], cwd=cwd, check=True, capture_output=True)
        assert doctor()["windows"] == 1, "Plain invocation should activate the recent window"
        arguments = ["", "  ", "中文 空格", 'single\'double"', "$HOME", "$(literal)"]
        subprocess.run(["/usr/bin/udeck-terminal", "--working-directory", str(cwd), "-T", "中文 标题",
                        "-e", sys.executable, str(child), *arguments], cwd=directory,
                       env={**os.environ, "UDECK_PROBE_CALLER": "secondary-中文"}, check=True, capture_output=True)
        wait(lambda: (cwd / "argv.json").exists())
        payload = json.loads((cwd / "argv.json").read_text())
        assert payload == {"argv": arguments, "cwd": str(cwd), "value": "secondary-中文"}, payload
        assert doctor()["windows"] == 2
        wait(lambda: doctor()["windows"] == 1)
        children_path = Path(f"/proc/{primary.pid}/task/{primary.pid}/children")
        children_before = set(map(int, children_path.read_text().split()))
        assert open_terminal(cwd).wait(timeout=8) == 0
        wait(lambda: doctor()["windows"] == 2 and doctor()["localShells"] == 1)
        children = set(map(int, children_path.read_text().split())) - children_before
        assert len(children) == 1, children
        shell = children.pop()
        assert Path(f"/proc/{shell}/cwd").resolve() == cwd
        os.kill(shell, signal.SIGHUP)
        wait(lambda: doctor()["windows"] == 1)
        for arguments, message in ((["--working-directory", str(directory / "missing")], "工作目录"),
                                    (["-e", "no-such-udeck-program"], "无法运行程序")):
            result = subprocess.run(["/usr/bin/udeck-terminal", *arguments],
                                    env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
                                    text=True, capture_output=True, timeout=5)
            assert result.returncode == 2 and message in result.stderr, result.stderr
        (directory / "finish").touch()
        assert primary.wait(timeout=10) == 0, primary.stderr.read()
        assert doctor().get("running") is False
        report = {"result": "passed", "activation": True, "secondaryWindow": True,
                  "fileDirectoryCreatesWindowWhilePrimaryExists": True,
                  "unicodeSpaceQuoteEmptyArgv": True, "callerCwdEnvironment": True,
                  "invalidCwdProgramErrors": True,
                  "buildId": json.loads(Path("/usr/share/udeck-terminal/build-info.json").read_text())["buildId"]}
        options.output.parent.mkdir(parents=True, exist_ok=True)
        options.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps(report))
    finally:
        (directory / "finish").touch()
        if primary.poll() is None:
            primary.terminate()
            primary.wait(timeout=5)
