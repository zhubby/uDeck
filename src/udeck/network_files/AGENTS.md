# network_files/
> L2 | Parent: ../AGENTS.md

__init__.py: Web 共享服务身份、端口和有效时长。
client.py: 桌面工作线程中的 D-Bus 请求与用户服务启停。
controls.py: 旧文件页入口的共享选项适配。
daemon.py: 用户 D-Bus 服务；按需读取关闭状态，启用后检查网络和期限。
filesystem.py: 根目录身份校验、路径边界与文件操作。
lifecycle.py: 共享配置事务、监听地址和连接撤销。
networks.py: 连接配置身份和可用网络地址读取。
server.py: HTTP 路由、文件传输和访问会话。
web/: 文件访问网页、交互脚本和样式。

[PROTOCOL]: Update this header on change, then check AGENTS.md
