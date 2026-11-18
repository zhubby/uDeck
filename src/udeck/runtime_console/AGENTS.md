# runtime_console/
> L2 | Parent: ../../../AGENTS.md

成员清单：

__init__.py: Console 运行服务包入口。
processes.py: proc 快照、应用进程树统计与 pidfd 终止。
model.py: 按应用身份增量更新的 Qt 列表模型。
service.py: 可见期采样、状态去重、过期回包隔离与有序退出。
controls.py: 桌面导航、详情操作与退出确认的桥接。

窗口列表提供应用入口，不提供进程身份。
会话 D-Bus 所有者确定内置应用主进程。
仅可见期查询所有者；模拟模式不连接会话总线。
proc 启动时刻验证 PID 身份。
独立应用主进程划分资源与终止边界。
采样不请求游戏暂停，不激活应用窗口。
详情按应用标识刷新；退出后禁用操作。
强制终止确认固定点击时的进程身份。
正常退出先调用原生接口；旧应用回退窗口关闭。

[PROTOCOL]: Update this header on change, then check AGENTS.md
