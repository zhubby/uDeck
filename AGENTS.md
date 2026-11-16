# uDeck - 面向 uConsole 物理按键的桌面
Python 3.13.18 + PySide6 6.8.3 + Qt Quick + Debian 13 + labwc

<directory>
src/udeck/ - 桌面、系统接口与应用入口。
src/udeck/apps/ - 共享应用框架与六类独立应用。
src/udeck/apps/emulator/ - 游戏库、RetroArch 与存档编排。见该目录 AGENTS.md。
src/udeck/emulator_saves/ - 原生存档、历史快照与云同步。
src/udeck/runtime_console/ - 应用运行统计、进程身份与退出编排。
tests/ - pytest 回归与独立进程探针。见该目录 AGENTS.md。
docs/ - 设计、运行说明与验证记录。
packaging/ - 会话入口、服务与运行包装。
debian/ - Debian 单包构建与安装脚本。
tools/ - 开发、构建与设备诊断工具。
references/ - uConsole 硬件与上游资料。
vendor/ - 随包集成的上游组件。
</directory>

<config>
pyproject.toml - Python 依赖、入口、pytest 与 Ruff 配置。
uv.lock - 开发依赖锁定版本；使用 uv 0.13.7。
.python-version - 开发解释器版本 3.13.18。
</config>

沿用已有模块和测试布局。只为本次触及的边界补充文档。
业务文件用 L3 头说明依赖、输出与职责。
新增文件时更新所属模块清单。
源码验证、设备安装与物理按键验收分别记录。
运行测试前设置 QT_QPA_PLATFORM=offscreen。
所有 shell 命令使用 rtk 前缀。

[PROTOCOL]: Update this header on change, then check AGENTS.md
