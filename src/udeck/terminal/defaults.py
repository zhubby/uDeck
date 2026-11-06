"""Transactional Debian/XDG defaults with exact, conflict-aware restoration.

SPDX-License-Identifier: GPL-2.0-or-later
"""

import argparse
import base64
import hashlib
import html
import json
import os
import pwd
import re
import shlex
import shutil
import stat
import subprocess
import tempfile
import uuid
from pathlib import Path

DESKTOP_ID = "io.github.zhubby.uDeck.Terminal.desktop"
TERMINAL = "/usr/bin/udeck-terminal"
MANUAL_CHECKS = ("installed-core", "ime-cjk", "vim-less-tmux-codex", "keyboard-copy-search-paste",
                 "argv-cwd-environment", "background-and-close", "physical-udeck-input",
                 "physical-original-desktop-input", "focus-hotplug-dropped-events", "wayland", "xwayland")
OLD_TERMINALS = {"lxterminal", "xterm", "uxterm", "qterminal", "foot", "kitty", "alacritty",
                 "xfce4-terminal", "gnome-terminal", "konsole", "mate-terminal"}


def validate_acceptance(path, build_id):
    report = json.loads(Path(path).read_text())
    if not build_id or report.get("buildId") != build_id:
        raise ValueError("验收记录与已安装构建不一致")
    missing = [name for name in MANUAL_CHECKS if report.get("checks", {}).get(name) != "passed"]
    metrics = report.get("performance", {})
    try:
        performance_ok = (metrics["sampleSeconds"] >= 60 and 0 < metrics["firstFrameSeconds"] <= 5
                          and 0 < metrics["rssMiB"] <= 250 and 0 <= metrics["idleCpuPercentOneCore"] <= 3
                          and metrics["windowCount"] == 1 and metrics["localShellCount"] == 1)
    except (KeyError, TypeError):
        performance_ok = False
    if missing or not performance_ok:
        raise ValueError("关键验收尚未通过：" + ", ".join(missing + ([] if performance_ok else ["60 秒实机性能采样"])))
    return report


class DebianAlternatives:
    @staticmethod
    def _run(*arguments):
        return subprocess.check_output(["update-alternatives", *arguments], text=True)

    def query(self):
        output = self._run("--query", "x-terminal-emulator")
        fields = dict(line.split(": ", 1) for line in output.splitlines() if ": " in line)
        return {"status": fields["Status"], "value": fields["Value"],
                "registered": f"Alternative: {TERMINAL}\n" in output + "\n"}

    def install(self):
        # Registration is deliberately deferred until acceptance, since an
        # alternatives --install can itself change an auto-selected terminal.
        self._run("--install", "/usr/bin/x-terminal-emulator", "x-terminal-emulator", TERMINAL, "20",
                  "--slave", "/usr/share/man/man1/x-terminal-emulator.1.gz", "x-terminal-emulator.1.gz",
                  "/usr/share/man/man1/udeck-terminal.1.gz")

    def select(self):
        self._run("--set", "x-terminal-emulator", TERMINAL)

    def restore(self, state):
        if not state["registered"]:
            self._run("--remove", "x-terminal-emulator", TERMINAL)
        self._run("--set", "x-terminal-emulator", state["value"])
        if state["status"] == "auto":
            self._run("--auto", "x-terminal-emulator")
        current = self.query()
        if any(current[key] != state[key] for key in ("status", "value", "registered")):
            raise RuntimeError("alternative 无法恢复原状态；候选项已变化，请检查备份中的选择")


def _atomic(path, data, mode=0o644, uid=None, gid=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".udeck-default-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, mode)
        if uid is not None and os.geteuid() == 0:
            os.chown(temporary, uid, gid)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def migrate_command(command):
    try:
        argv = shlex.split(command)
    except ValueError:
        return command
    if not argv or Path(argv[0]).name not in OLD_TERMINALS:
        return command
    result = ["x-terminal-emulator"]
    aliases = {"-t": "-T", "--title": "-T", "--workdir": "--working-directory", "-D": "--working-directory"}
    index = 1
    while index < len(argv):
        token = argv[index]
        if token in ("-e", "--execute", "--"):
            result.extend(["-e", *argv[index + 1:]])
            break
        if token in ("-T", "--working-directory", *aliases) and index + 1 < len(argv):
            result.extend((aliases.get(token, token), argv[index + 1]))
            index += 2
        elif token == "%s":
            result.append(token)
            index += 1
        else:
            raise ValueError(f"旧终端绑定需要手动迁移：{command}")
    return shlex.join(result)


class DefaultManager:
    def __init__(self, root, home, alternatives, *, uid=None, gid=None, config_home=None):
        self.root, self.home, self.alternatives = Path(root), Path(home), alternatives
        self.uid, self.gid = uid, gid
        self.config = Path(config_home) if config_home else self.home / ".config"
        self.backups = self.root / "var/lib/udeck-terminal/defaults"

    def physical(self, path):
        return self.root / Path(path).relative_to("/")

    def plan(self):
        configs = [Path("/etc/xdg"), self.config]
        planned = {}
        for directory in configs:
            base = self.physical(directory)
            paths = {directory / "xdg-terminals.list", directory / "udeck-xdg-terminals.list",
                     directory / "labwc-xdg-terminals.list"}
            if base.is_dir():
                paths.update(directory / path.name for path in base.glob("*-xdg-terminals.list"))
            for logical in sorted(paths):
                path = self.physical(logical)
                self._check_path(path)
                text = path.read_text() if path.exists() else ""
                lines = [line for line in text.splitlines() if line.strip() != DESKTOP_ID]
                planned[str(logical)] = (DESKTOP_ID + "\n" + "\n".join(lines) + ("\n" if lines else "")).encode()
        bindings = ("labwc/rc.xml", "openbox/lxde-pi-rc.xml", "openbox/rc.xml", "libfm/libfm.conf",
                    "pcmanfm/LXDE-pi/pcmanfm.conf", "pcmanfm/default/pcmanfm.conf", "lxsession/LXDE-pi/desktop.conf")
        for directory in configs:
            for binding in bindings:
                logical = directory / binding
                path = self.physical(logical)
                self._check_path(path)
                if not path.exists():
                    continue
                text = path.read_text()
                # Preserve all unrelated bytes and formatting.
                updated = re.sub(r"(<command>)([^<]*)(</command>)", lambda m: m[1] + migrate_command(m[2]) + m[3], text)
                def migrate_attribute(match):
                    command = html.unescape(match[3])
                    migrated = migrate_command(command)
                    return match[0] if migrated == command else match[1] + match[2] + html.escape(migrated, quote=True) + match[2]

                updated = re.sub(r'''(<action\b[^>]*\bcommand=)(["'])(.*?)\2''', migrate_attribute, updated)
                updated = re.sub(r"(?m)^(\s*(?:terminal|terminal_command)\s*=\s*)([^\r\n]*)", lambda m: m[1] + migrate_command(m[2]), updated)
                if updated != text:
                    planned[str(logical)] = updated.encode()
        return planned

    @staticmethod
    def _check_path(path):
        if path.is_symlink() or any(parent.is_symlink() for parent in path.parents):
            raise ValueError(f"配置使用符号链接，请先手动迁移：{path}")
        if path.exists() and not path.is_file():
            raise ValueError(f"配置不是普通文件：{path}")

    def apply(self):
        planned = self.plan()  # Complete all validation before the first mutation.
        manifest = {"version": 1, "home": str(self.home), "alternative": self.alternatives.query(), "files": {}}
        for logical, contents in planned.items():
            path = self.physical(logical)
            metadata = path.stat() if path.exists() else None
            manifest["files"][logical] = {"before": base64.b64encode(path.read_bytes()).decode() if metadata else None,
                                          "mode": stat.S_IMODE(metadata.st_mode) if metadata else 0o644,
                                          "uid": metadata.st_uid if metadata else (self.uid if logical.startswith(str(self.home) + "/") else 0),
                                          "gid": metadata.st_gid if metadata else (self.gid if logical.startswith(str(self.home) + "/") else 0),
                                          "afterSha256": hashlib.sha256(contents).hexdigest()}
        self.backups.mkdir(parents=True, exist_ok=True, mode=0o700)
        backup = self.backups / (uuid.uuid4().hex + ".json")
        _atomic(backup, json.dumps(manifest, indent=2).encode(), 0o600)
        try:
            for logical, contents in planned.items():
                info = manifest["files"][logical]
                _atomic(self.physical(logical), contents, info["mode"], info["uid"], info["gid"])
            self.alternatives.install()
            self.alternatives.select()
        except BaseException:
            self._restore(manifest)
            raise
        return backup

    def restore(self, backup):
        backup = Path(backup)
        if backup.parent.resolve() != self.backups.resolve():
            raise ValueError("只允许恢复本工具保存的备份")
        manifest = json.loads(backup.read_text())
        if manifest["home"] != str(self.home):
            raise ValueError("备份所属用户不匹配")
        for logical, info in manifest["files"].items():
            path = self.physical(logical)
            self._check_path(path)
            if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest() != info["afterSha256"]:
                raise ValueError(f"应用后的配置已被修改，拒绝覆盖：{logical}")
        self._restore(manifest)

    def _restore(self, manifest):
        for logical, info in manifest["files"].items():
            path = self.physical(logical)
            if info["before"] is None:
                path.unlink(missing_ok=True)
            else:
                _atomic(path, base64.b64decode(info["before"]), info["mode"], info["uid"], info["gid"])
        self.alternatives.restore(manifest["alternative"])


def main(argv=None):
    parser = argparse.ArgumentParser(description="uDeck Terminal 默认终端配置与恢复")
    parser.add_argument("action", choices=("status", "apply", "restore"))
    parser.add_argument("--user", default=os.environ.get("SUDO_USER") or pwd.getpwuid(os.getuid()).pw_name)
    parser.add_argument("--config-home", type=Path)
    parser.add_argument("--acceptance", type=Path)
    parser.add_argument("--backup", type=Path)
    options = parser.parse_args(argv)
    try:
        user = pwd.getpwnam(options.user)
        manager = DefaultManager(Path("/"), Path(user.pw_dir), DebianAlternatives(), uid=user.pw_uid, gid=user.pw_gid, config_home=options.config_home)
        if options.action == "status":
            print(json.dumps({"alternative": manager.alternatives.query(), "plannedFiles": list(manager.plan()),
                              "launchVerification": "required-after-apply"}, ensure_ascii=False, indent=2))
            return 0
        if os.geteuid() != 0:
            raise ValueError("修改系统默认终端需要以 sudo 运行，并用 --user 指定桌面用户")
        if options.action == "restore":
            if not options.backup:
                raise ValueError("恢复需要 --backup 指定备份文件")
            manager.restore(options.backup)
            print("原 alternative 与 XDG/桌面配置已恢复；请重新启动入口验证。")
        else:
            if not options.acceptance:
                raise ValueError("设置默认前必须提供已通过的 --acceptance 实机验收记录")
            build = json.loads(Path("/usr/share/udeck-terminal/build-info.json").read_text())
            validate_acceptance(options.acceptance, build["buildId"])
            if not shutil.which("xdg-terminal-exec") or not Path(TERMINAL).is_file():
                raise ValueError("请先安装 udeck-terminal 与 xdg-terminal-exec")
            print(f"配置已应用。恢复备份：{manager.apply()}")
            print("请逐个验证 x-terminal-emulator、xdg-terminal-exec、Gio Terminal=true、快捷键及文件管理器；配置写入不等于启动验收。")
        return 0
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError) as error:
        print(f"默认终端配置失败：{error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
