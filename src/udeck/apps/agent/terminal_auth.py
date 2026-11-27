"""[INPUT]: 依赖 uDeck Terminal 启动的认证命令。
[OUTPUT]: 将认证退出码写入当前认证尝试的私有文件。
[POS]: 跨终端窗口转发实际命令的结果。
[PROTOCOL]: Update this header on change, then check AGENTS.md
"""

import json
import os
import subprocess
import sys
from pathlib import Path


def main():
    request, status = map(Path, sys.argv[1:])
    launch = json.loads(request.read_text(encoding="utf-8"))
    request.unlink()
    try:
        code = subprocess.run(launch["argv"], env={**os.environ, **launch["env"]}, check=False).returncode
    except OSError:
        code = 127
    try:
        temporary = status.with_suffix(".tmp")
        temporary.write_text(str(code), encoding="ascii")
        temporary.replace(status)
    except FileNotFoundError:
        pass
    return code


if __name__ == "__main__":
    raise SystemExit(main())
