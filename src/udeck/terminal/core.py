"""Launch and preference contracts; terminal contents stay out of persistent state."""

import argparse
import json
import os
import pwd
import shutil
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path


def _string(value):
    return isinstance(value, str) and "\x00" not in value


@dataclass
class LaunchRequest:
    cwd: str
    argv: list[str]
    title: str
    environment: dict[str, str]
    new_window: bool = False

    def __post_init__(self):
        if not _string(self.cwd) or not Path(self.cwd).is_absolute() or not Path(self.cwd).is_dir():
            raise ValueError("工作目录不存在或无法访问")
        if not isinstance(self.argv, list) or not all(_string(item) for item in self.argv):
            raise ValueError("程序参数必须是独立的文字参数")
        if self.argv and not self.argv[0]:
            raise ValueError("未指定要运行的程序")
        if not _string(self.title) or type(self.new_window) is not bool:
            raise ValueError("终端窗口参数无效")
        if not isinstance(self.environment, dict) or not all(
            _string(key) and key and "=" not in key and _string(value)
            for key, value in self.environment.items()
        ):
            raise ValueError("程序环境无效")

    def to_json(self):
        return json.dumps(asdict(self), ensure_ascii=False)

    @classmethod
    def from_json(cls, value):
        try:
            data = json.loads(value)
            if not isinstance(data, dict) or set(data) != {"cwd", "argv", "title", "environment", "new_window"}:
                raise ValueError("窗口请求无效")
            return cls(**data)
        except (TypeError, KeyError, json.JSONDecodeError) as error:
            raise ValueError("窗口请求无效") from error

    def executable(self):
        program = self.argv[0] if self.argv else (pwd.getpwuid(os.getuid()).pw_shell or "/bin/sh")
        if "/" in program:
            path = Path(program) if Path(program).is_absolute() else Path(self.cwd) / program
            resolved = str(path) if path.is_file() and os.access(path, os.X_OK) else None
        else:
            search_path = os.pathsep.join(str(Path(self.cwd) / entry) if not Path(entry).is_absolute() else entry
                                          for entry in self.environment.get("PATH", os.defpath).split(os.pathsep))
            resolved = shutil.which(program, path=search_path)
        if not resolved:
            raise ValueError(f"无法运行程序：{program}")
        return resolved, self.argv[1:] if self.argv else []


def parse_launch(arguments=None, *, cwd=None, environment=None):
    arguments = list(arguments) if arguments is not None else None
    parser = argparse.ArgumentParser(description="uDeck Terminal · 按键原生终端")
    parser.add_argument("--new-window", action="store_true")
    parser.add_argument("--working-directory")
    parser.add_argument("-T", "--title", default="")
    parser.add_argument("-e", dest="execute", nargs=argparse.REMAINDER)
    parser.add_argument("--mock", action="store_true", help="安全界面预览，不启动真实进程")
    parser.add_argument("--windowed", action="store_true")
    parser.add_argument("--no-input", action="store_true")
    parser.add_argument("--screenshot", type=Path)
    parser.add_argument("--quit-after", type=float, default=0)
    parser.add_argument("--smoke-test", action="store_true")
    parser.add_argument("--doctor", action="store_true", help="输出只读诊断 JSON")
    parser.add_argument("program", nargs=argparse.REMAINDER)
    options = parser.parse_args(arguments)
    command = options.execute if options.execute is not None else options.program
    if command[:1] == ["--"]:
        command = command[1:]
    actual = arguments if arguments is not None else sys.argv[1:]
    if (options.execute is not None or "--" in actual) and not command:
        parser.error("-e 或 -- 后必须指定程序")
    if options.execute is not None and options.program:
        parser.error("程序参数不能重复指定")
    if options.smoke_test and not options.mock:
        parser.error("--smoke-test 必须配合 --mock，避免执行真实命令")
    directory = Path(options.working_directory or cwd or Path.cwd()).expanduser().absolute()
    request = LaunchRequest(str(directory), command, options.title,
                            dict(os.environ if environment is None else environment),
                            bool(options.new_window or options.working_directory or options.title or command))
    return request, options


def paste_needs_confirmation(text):
    return any(ord(character) < 32 or 127 <= ord(character) < 160 for character in text)


class TerminalPreferences:
    def __init__(self, path=None):
        self.path = Path(path) if path else Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "udeck/terminal.json"
        self.font_size = 20
        self.color_scheme = "udeck"
        try:
            data = json.loads(self.path.read_text())
            if isinstance(data, dict):
                size = data.get("fontSize")
                if type(size) is int and size in range(14, 29, 2):
                    self.font_size = size
                if data.get("colorScheme") in ("udeck", "SolarizedLight"):
                    self.color_scheme = data["colorScheme"]
        except (OSError, ValueError, TypeError):
            pass

    def change_font(self, amount):
        self.font_size = max(14, min(28, self.font_size + int(amount) // 2 * 2))

    def save(self):
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(prefix=".terminal-", dir=self.path.parent)
        try:
            with os.fdopen(descriptor, "w") as stream:
                json.dump({"version": 1, "fontSize": self.font_size, "colorScheme": self.color_scheme}, stream)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        finally:
            Path(temporary).unlink(missing_ok=True)
