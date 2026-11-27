# uDeck - 面向 uConsole 物理按键的桌面
Python 3.13.18 + PySide6 6.8.3 + Qt Quick + Debian 13 + labwc

<directory>
.github/ - push/PR 检查；仅在 Release 发布时构建和分发 arm64 制品。
src/udeck/ - 桌面、系统接口与应用入口。
src/udeck/apps/ - 共享应用框架与独立应用。
src/udeck/apps/agent/ - Agent 的 ACP 连接、安装与历史。
src/udeck/apps/emulator/ - 游戏库、RetroArch 与存档编排。见该目录 AGENTS.md。
src/udeck/emulator_saves/ - 原生存档、历史快照与云同步。
src/udeck/runtime_console/ - 应用运行统计、进程身份与退出编排。
tests/ - pytest 回归与独立进程探针。见该目录 AGENTS.md。
docs/ - 当前产品设计、技术契约与维护指南。
docs/motion/ - 桌面短过渡、输入连续性与响应约束。
docs/readme/ - 英文首页的实机截图与来源记录。
packaging/ - 会话入口、服务与运行包装。
debian/ - Debian 单包构建与安装脚本。
tools/ - 开发、构建与设备诊断工具。
references/ - uConsole 硬件与上游资料。
vendor/ - 随包集成的上游组件。
</directory>

<config>
src/udeck/__init__.py - 唯一版本源；标签和 Debian 版本必须一致。
pyproject.toml - Python 依赖、入口、pytest 与 Ruff 配置。
README.md - 英文项目概览、实机截图与安装入口。
uv.lock - 开发依赖锁定版本；使用 uv 0.13.7。
.python-version - 开发解释器版本 3.13.18。
src/udeck/qml_cache.py - 按源码内容隔离 Qt 编译缓存。
</config>

沿用已有模块和测试布局。只为本次触及的边界补充文档。
界面只启动和激活内置应用；命令固定到 uDeck 模块。
保留受控 RetroArch、锁屏和系统授权组件。
网页禁用系统协议处理器；终端显式命令不属于应用路由。
业务文件用 L3 头说明依赖、输出与职责。
新增文件时更新所属模块清单。
源码验证、设备安装与物理按键验收分别记录。
运行测试前设置 QT_QPA_PLATFORM=offscreen。
所有 shell 命令使用 rtk 前缀。

[PROTOCOL]: Update this header on change, then check AGENTS.md
