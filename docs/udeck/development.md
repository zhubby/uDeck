# 开发与诊断

## 固定工具链

开发使用 uv 0.13.7 和 Python 3.13.18。
`.python-version` 固定开发解释器，`pyproject.toml` 支持 Python 3.11–3.13。
PySide6 范围为 6.8，`uv.lock` 固定开发依赖。
Debian 设备仍使用系统 Python 与 APT 的 Qt，不需要 uv。

按[官方固定版本安装说明](https://docs.astral.sh/uv/getting-started/installation/#installing-a-specific-version)
安装 uv，并先核对 `uv --version`。
在独立工作目录中执行：

```sh
uv python install
uv sync --locked --extra dev
uv run --locked --extra dev udeck --mock --windowed
```

uv 安装用户级解释器，不替换系统 Python。
源码 editable 安装，修改即时生效。
`--mock` 使用临时配置并模拟桌面设备操作。
真实 `--windowed` 会执行实际系统动作并接管快捷键。

Linux 的 evdev 源码构建需要 `build-essential`。
选择系统 Python 时还需要对应 `python3-dev`。
不要用系统级 pip 拼装另一个 Qt，或复用其他工作树的虚拟环境。
迁移已有环境前将其备份到独立的 `artifacts/` 目录，
并在解释器可用时保存依赖清单。

## 回归与构建

Qt 测试先设置离屏平台。
本地完整回归通过逐文件进程隔离 Qt 生命周期：

```sh
env QT_QPA_PLATFORM=offscreen uv run --locked --extra dev python tools/test-suite --output artifacts/test-suite
uv run --locked --extra dev ruff check src tests tools tools/build-release tools/test-suite
uv run --locked --extra dev python tools/build-release --check-version
uv lock --check
git diff --check
```

输出目录须为空；重复执行时指定新目录，保留旧证据。
定向执行可在 `tools/test-suite` 后传入测试文件路径。
执行器保存日志、JUnit、退出码和超时汇总，不重试失败。
直接运行单个 pytest 文件时也须设置 `QT_QPA_PLATFORM=offscreen`。

QML 桌面预览：

```sh
env QT_QPA_PLATFORM=offscreen PYTHONPATH=src uv run --locked --extra dev python -m udeck.main \
  --mock --windowed --smoke-test --page files \
  --screenshot artifacts/preview-files.png --quit-after 2
```

原生 Terminal 回归需目标 Qt 6.8 的 QMLTermWidget 插件。
macOS/mock 的布局检查不能替代 Debian arm64、PTY 和输入法验证。
原生插件步骤见[终端指南](terminal.md)，
单包和容器构建见[发行指南](debian-distribution.md)。

wheel 构建保持隔离 setuptools 后端：

```sh
uv run --locked --extra dev python -m build --wheel
```

## 依赖维护

日常命令使用 `--locked`，不自动刷新锁文件。
`uv sync` 会移除选定依赖以外的包，临时工具使用独立环境或 uvx。

```sh
uv add <运行依赖包名>
uv add --optional dev <开发依赖包名>
uv lock --upgrade-package <包名>
uv sync --locked --extra dev
```

依赖更新审查声明和锁文件，并执行对应回归。
涉及 Qt、evdev 和原生插件时验证 Debian arm64。
升级 uv 同步修改 required-version 与工作流；
升级开发 Python 同步修改 .python-version 并重建环境。
APT 依赖由 debian/control 与目标镜像解析，不由 uv.lock 固定。

## 诊断与性能

`udeckctl doctor --json` 汇总构建身份、会话、输入和服务。
性能工具在源码中按任务选用：

| 工具 | 用途 |
| --- | --- |
| `tools/measure-shell.py` | 桌面 CPU、内存和事件循环采样 |
| `tools/verify-windows.py` | 创建并验证自身 Wayland/Xwayland 测试窗口 |
| `tools/measure-motion.py` | 内容呈现与动效测量 |
| `tools/terminal-acceptance` | 已安装终端身份与资源采样 |

参数以各工具 `--help` 为准。
操作图形窗口前保存工作并确认目标会话。
测量须固定输入序列、原始内容、输出设备和统计口径。
不要将离屏帧间隔或软件阶段耗时称作物理响应。
证据与未完成项按[验证规范](validation.md)记录。

## 文档边界

当前文档入口为[文档索引](../README.md)。
业务文件保持 INPUT/OUTPUT/POS 头，文件变化同步所属 AGENTS.md。
产品设计与技术说明直接更新稳定文件，不新增按日期拆分的发布流水。
许可证、上游固定版本和正式截图来源随资源保留。

[PROTOCOL]: Update this header on change, then check AGENTS.md
