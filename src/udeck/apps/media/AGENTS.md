# media/
> L2 | Parent: ../AGENTS.md

__init__.py: 共享媒体包入口。
controller.py: 音乐视频的播放权限、队列、进度持久化与交互编排。
engine.py: Qt 播放器、TS 准备状态、暂停意图、加载后定位与软件视频帧。
seekable.py: 后台无损重封装 TS；复用当前临时源并限制空间、超时与进程生命周期。

控制器只从播放引擎读取实际播放状态。
播放引擎不读取应用配置或索引。

[PROTOCOL]: Update this header on change, then check AGENTS.md
