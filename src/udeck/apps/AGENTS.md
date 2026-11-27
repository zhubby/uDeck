# apps/
> L2 | Parent: ../../../AGENTS.md

成员清单：

__init__.py: 应用包版本。
main.py: 轻量启动入口；先转发已有实例请求。
runtime.py: 会话 D-Bus、文件索引、交接显示与共享圆点生命周期。
common/: 应用共享状态、输入、菜单与 QML 窗口。
agent/: ACP 会话、版本管理和 Agent 界面。
browser/: 浏览器控制器与网页导航。见该目录 AGENTS.md。
emulator/: 游戏库、RetroArch 进程协议与存档。见该目录 AGENTS.md。
media/: 音乐与视频共用播放引擎。见该目录 AGENTS.md。
music/: 专辑、封面更新与播放队列。
reader/: 文档解析、分页与阅读窗口。见该目录 AGENTS.md。
video/: 视频库、字幕与播放指针观测。见该目录 AGENTS.md。

运行层将启动请求传入应用控制器。
桌面先释放输入，应用再接管设备并显示窗口。
焦点确认后，应用才投递已到达的按键事件。
模拟器运行中再次打开应用，先请求暂停。
模拟器确认暂停后，控制器显示操作菜单。

[PROTOCOL]: Update this header on change, then check AGENTS.md
