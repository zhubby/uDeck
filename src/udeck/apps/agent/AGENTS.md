# agent/
> L2 | Parent: ../AGENTS.md

__init__.py: Agent 应用包。
acp.py: ACP v1 握手、逐行 JSON-RPC、双向请求取消与进程组回收。
catalog.py: 固定分发来源、ARM64 发布元数据和登录命令。
controller.py: 路由会话操作、权限请求和设置中的 Agent 管理。
content.py: ACP 内容、工具输出与计划条目的大小限制和展示模型。
client_calls.py: 授权目录内的文本文件操作、终端输出与结构化输入应答。
client_events.py: 按事件顺序展示客户端请求、终端输出和交互回执。
conversation.py: ACP 更新排序、消息模型、会话权限与取消。
install.py: 安装暂存、上游校验、握手、版本切换与回退。
session_actions.py: 会话操作、连接选项、附件与交互表单的共享菜单。
session_events.py: 会话元数据、结束原因与组件动作的数据格式。
session_rpc.py: 按 ACP 能力校验会话请求，并限制子会话操作。
sessions.py: SQLite 会话索引、消息历史与回放去重。
terminal_auth.py: 向发起认证的会话回传终端命令退出码。
qml/: 会话及 Agent 管理界面。

[PROTOCOL]: Update this header on change, then check AGENTS.md
