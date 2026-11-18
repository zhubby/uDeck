# smb_files/
> L2 | Parent: ../AGENTS.md

__init__.py: SMB 系统服务、对象路径和专用单元身份。
client.py: 桌面工作线程中的受限系统 D-Bus 请求。
daemon.py: 调用方认证与授权；关闭时停止网络发现，启用后检查撤销。
lifecycle.py: 配置事务、目录身份和共享连接撤销。
runtime.py: 专用 Samba 单元、目录权限与配置验证。

[PROTOCOL]: Update this header on change, then check AGENTS.md
