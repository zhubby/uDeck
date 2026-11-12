# 系统设置 → 共享

系统设置和 Y 快捷设置均提供「共享」。两个子菜单分别管理「网页文件访问」和「SMB 文件共享」，每行左侧为图标与名称，右侧为开关或状态。开关反映服务的实际启用状态；目录、网络、开放时长和访问地址分别显示在同一行。处理时显示「正在应用」，失败时保留菜单、焦点及实际开关状态。

网页访问继续使用 `~/.config/udeck/network-files.json` 和原有用户 D-Bus 接口，已有配置保留。文件菜单的旧入口已移除，内部 `network-*` 调用转发到新的网页访问菜单。

SMB 初始关闭，首次开启前需选择目录及网络。共享名为 `udeck`，地址显示为 `smb://地址/udeck`，IPv6 地址带方括号。它使用标准 Samba 的 SMB2/3，免密码来宾读写。客户端必须支持并允许来宾访问；例如部分 Windows 默认策略禁止来宾连接，需要在客户端按自身管理要求配置。

文件操作映射到开启共享的本机 Unix 用户；不会为共享修改原目录或文件权限。用户无法读取或写入的文件仍会拒绝访问，符号链接不跟随。网页和 SMB 的目录、网络、草稿、错误及计时独立。

## 时长与网络

两个协议均支持永久、1 小时、6 小时、12 小时。永久共享在相应服务恢复后等待已选 NetworkManager 连接；限时共享在到期、发起会话退出或服务重启后关闭。SMB 根据 D-Bus 调用者的实际 PID 和登录会话识别发起者，并防止 PID 重用。

仅绑定所选 NetworkManager 连接当前的实际地址，不监听通配地址。同一网卡换用另一个连接配置不会继承授权。撤销网络时关闭已建立的连接；网络恢复后，仍启用的永久或未到期共享可以恢复。关闭、到期、目录失效或 Samba 异常退出会终止连接。目录 inode 变化后需要重新选择目录；SMB 的独立 bind mount 保证替换路径不会短暂暴露替换后的目录。

## 系统服务

系统 D-Bus 服务 `io.github.zhubby.uDeck.Smb` 暴露 `Status`、`Configure`、`Stop`，响应为 JSON。配置示例：

```json
{"root":"/home/user/Shared","networks":["mac:xx:xx:xx:xx:xx:xx@connection-uuid"],"duration":3600}
```

服务从系统总线读取 UID/PID，从账号数据库取得用户名；载荷中的 UID、用户名和进程身份不作为授权依据。配置及关闭受 Polkit 管理；默认需要当前本地活动用户认证。其他用户无法修改已有共享。root 可以关闭共享用于管理，但不能开启映射为 root 的来宾共享。

- `udeck-smb-manager.service`：控制、持久化、网络和生命周期检查。
- `udeck-smb.service`：专用 Samba 进程及连接子进程，整体停止。
- `/var/lib/udeck-smb/settings.json`：独立 SMB 配置，权限 0600。
- `/run/udeck-smb/smb.conf`：生成的专用 Samba 配置，权限 0600。
- `/var/lib/udeck-smb/samba.log`：Samba 日志。

不会修改 `/etc/samba/smb.conf` 或停止标准 Samba 服务。所选地址的 445 端口冲突会明确报错；保存或启动失败时恢复之前的有效配置。后台状态轮询与文件页面无关。

安装使用发行套件的 `install.sh`，其 Samba 启动保护覆盖依赖安装全过程，详见[Debian 安装说明](debian-distribution.md)。
