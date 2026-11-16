# emulator/
> L2 | Parent: ../../../../AGENTS.md

成员清单：

__init__.py: Python 包入口。
browser.py: 列表与游戏浏览状态，向控制器提供导航行为。
catalog.py: Libretro 核心发现、平台策略与固件检查。
controller.py: 启动预检与应用状态编排，保留原有引擎导入接口。
engine.py: RetroArch 进程协议、单条状态查询背压与存读档确认。
game_info.py: 选中游戏信息与游玩时长展示。
library.py: 游戏库扫描、内容路径约束与条目身份。
library_management.py: 目录选择、扫描预览与迁移交互。
migration.py: 游戏库迁移计划、提交与恢复。
platform_icons.py: 平台图标选择与本地资源映射。
playlists.py: Libretro 列表解析、路径重定位与生成。
probe.py: 独立进程中的原生核心能力探测。
save_management.py: 原生存档、历史与同步的界面编排。
services.py: 核心检查与启动预检的后台任务。
settings.py: 模拟器目录、核心与预览偏好交互。
thumbnails.py: 缩略图定位、下载、校验与取消。
qml/: 游戏库与详情的 Qt Quick 视图。
resources/: 平台、数据库和图标的固定资源。

控制器连接原生进程信号与共享应用界面。
进程确认决定暂停和存读档结果。
状态查询等待回复；VERSION 回复隔开读档前后状态。
状态变化和读档完成发布界面快照。
重复状态不发布快照，输出按整批行解析。
前台窗口切换由控制器执行。

[PROTOCOL]: Update this header on change, then check AGENTS.md
