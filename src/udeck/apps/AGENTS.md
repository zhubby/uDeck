# apps/
> L2 | Parent: ../../../AGENTS.md

成员清单：

__init__.py: 应用包版本。
main.py: 轻量启动入口；先转发已有实例请求。
runtime.py: 会话 D-Bus、轻量运行摘要与退出请求；暂停确认后显示菜单。
common/: 应用共享状态、输入、菜单与 QML 窗口。
browser/: 浏览器控制器与网页导航。
emulator/: 游戏库、RetroArch 进程协议与存档。见该目录 AGENTS.md。
media/: 音乐与视频共用播放引擎。
music/: 音乐库与队列。
reader/: 文档解析、分页与阅读窗口。
video/: 视频库与字幕。

运行层将启动请求传入应用控制器。
模拟器运行中再次打开应用，先请求暂停。
模拟器确认暂停后，控制器显示操作菜单。

[PROTOCOL]: Update this header on change, then check AGENTS.md
