# emulator/
> L2 | Parent: ../../../../AGENTS.md

成员清单：

__init__.py: Python 包入口。
browser.py: 列表与游戏浏览状态，向控制器提供导航行为。
catalog.py: Libretro 核心发现、平台策略与固件检查。
controller.py: 启动预检、运行摘要与原生窗口激活；游戏写回后退出应用。
engine.py: RetroArch 进程协议、单条状态查询背压与存读档确认。
game_info.py: 选中游戏信息与游玩时长展示。
library.py: 后台列表与封面解析、内容约束、扫描代次和封面修订隔离。
library_management.py: 目录选择、扫描预览与迁移交互。
migration.py: 游戏库迁移计划、提交与恢复。
platform_icons.py: 平台图标选择与本地资源映射。
playlists.py: Libretro 列表解析、路径重定位与生成。
probe.py: 独立进程中的原生核心能力探测。
save_management.py: 原生存档、历史与同步的界面编排。
services.py: 核心检查与启动预检的后台任务。
settings.py: 模拟器目录、核心与预览偏好交互。
thumbnails.py: 单项封面查找、单轮目录索引、下载、校验与取消。
qml/: 按游戏身份保留封面的详情视图。见该目录 AGENTS.md。
resources/: 平台、数据库和图标的固定资源。

控制器连接原生进程信号与共享应用界面。
进程确认决定暂停和存读档结果。
状态查询等待回复；VERSION 回复隔开读档前后状态。
状态变化和读档完成发布界面快照。
重复状态不发布快照，输出按整批行解析。
前台窗口切换由控制器执行。
发送原生命令时，控制器唤回 RetroArch 窗口。
退出主界面遮挡后，原生进程继续接收命令。
初始封面查找随列表任务进入工作线程。
批量刷新和下载准备复用单轮目录索引。
索引拒绝符号链接，不跨刷新保存缺失结果。
显式封面刷新使旧快照失效，后台补读后发布。

[PROTOCOL]: Update this header on change, then check AGENTS.md
