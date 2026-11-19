# packaging/
> L2 | Parent: ../AGENTS.md

bin/: 已安装命令包装与独立会话入口。
apps/: 独立应用的桌面注册、图标与许可证。
labwc/: 合成器环境、窗口规则和自动启动。
session: labwc 会话服务、桌面监督器与退出清理。
terminal.colorscheme: 终端浅色调色板。
terminal-dark.colorscheme: 终端深色调色板。
install-release: 离线安装与依赖检查。
samba-install-guard: Samba 安装事务的服务启动边界。
udeck.desktop: 登录会话注册。
io.github.zhubby.uDeck.desktop: 桌面应用注册。
io.github.zhubby.uDeck.Terminal.desktop: 默认终端注册。
udeck.svg: 桌面图标。
terminal.svg: 终端图标。
udeck-terminal.1: 终端命令手册。
udeck-terminal-default.1: 默认终端命令手册。
udeck-portals.conf: uDeck 会话的 portal 选择。
udeck-network-files.service: 网络文件用户服务。
udeck-emulator-saves.service: 存档后台用户服务。
udeck-smb.service: Samba 文件共享用户服务。
udeck-smb-manager.service: Samba 特权代理服务。
io.github.zhubby.uDeck.EmulatorSaves.service: 存档 D-Bus 激活。
io.github.zhubby.uDeck.Smb.service: Samba D-Bus 激活。
io.github.zhubby.uDeck.Smb.conf: Samba 系统总线策略。
io.github.zhubby.uDeck.Smb.policy: Samba Polkit 授权策略。

监督器按 60 秒滚动窗口限制三次崩溃。
正常退出与会话终止不重启桌面。

[PROTOCOL]: Update this header on change, then check AGENTS.md
