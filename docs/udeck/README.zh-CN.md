# uDeck 使用与维护

uDeck 是面向 uConsole 物理按键的原生桌面。
目标环境为 CM4、Debian 13 arm64、Qt 6.8、labwc 和 1280×720 横屏。
它提供桌面、文件、系统设置、Console 和七个内置应用。
安装与升级见[Debian 发行指南](debian-distribution.md)，
开发预览见[开发指南](development.md)。

## 启动与会话

从登录界面选择 uDeck，进入独立 labwc 会话。
安装保留原桌面与默认登录，并设置 uDeck Terminal 为系统默认终端。
原桌面内可运行真实后端：

```sh
udeck --windowed
udeckctl doctor --json
```

真实后端的文件、音量和设备操作会生效。
安全预览使用 `udeck --mock --windowed`，配置退出即清理。
`--no-input` 禁止手柄和鼠标设备接管，用于诊断。
真实模式同一用户图形会话只运行一个桌面实例。

独立会话使用自己的 labwc 配置，启动输入法、授权代理和熄屏组件。
它不读取原桌面的面板与文件管理器 autostart。
桌面全屏显示，窗口化与 mock 使用普通窗口。
安装不会主动注销或重启显示管理器。
首次真实运行会备份并接管 labwc 快捷键，
包括窗口化运行；恢复方法见[输入指南](input.md)。

## 桌面与按键

顶部为主页、应用、Console、文件四页，设置从首页进入。
首页固定展示终端、音乐、视频、阅读器、模拟器、浏览器和设置。
方向键随焦点横向滚动，到边界停止。
收藏与最近使用不改变首页顺序。

| 输入 | 桌面动作 |
| --- | --- |
| 方向键 | 按可见行列选择 |
| A / Enter | 确认、打开 |
| B / Esc | 返回、关闭当前弹层 |
| X / F10 | 当前项操作 |
| Y / F1 | 快捷设置 |
| L/R / PageUp/PageDown | 上一页 / 下一页 |
| Ctrl+Alt+Esc | 主页 |
| Ctrl+Alt+Tab | Console |
| Ctrl+Alt+M | 游戏暂停菜单 |

弹层按层返回并恢复原焦点。
设置页内 L/R 不切主页面，Y 仍可打开快捷设置。
普通键盘字母 A/B/X/Y 输入文字。
实体 L/R 来自内置鼠标左右按钮，不依赖光标位置。

轨迹球支持相对移动和圆点显示。
短按轨迹球确认当前选中项，长按超过 2 秒打开上下文菜单。
应用内点击按该应用的输入策略执行。
校准、兼容指针模式、快捷键录制与恢复见[输入指南](input.md)。
游戏中的普通按钮交给 RetroArch，不能用 B 退出游戏。

## 内置应用与文件

内置应用包括 Terminal、Music、Video、Browser、Reader、Emulator 和 Agent。
文件按共享格式表进入内置应用，其他格式使用预览或详情。
网页未知协议不能唤起系统处理器。
受控 RetroArch、锁屏和授权组件保留。
终端里显式输入的命令遵循操作系统权限。
完整边界见[架构](architecture.md)。

[文件工作区](files.md)支持位置、搜索、筛选、多选、传输和回收站。
覆盖默认取消，目录不合并或覆盖，不提供永久删除后备操作。
跨卷移动先复制再回收源；源回收失败保留两份并显示原因。
挂载设备卸载前核对身份，传输中的设备不能卸载。

[应用指南](../apps/README.md)说明内容目录和引擎能力。
Music、Video、Reader 未配置来源时分别扫描
`~/Music`、`~/Video`、`~/Books`。
[模拟器](../apps/emulator.md)使用 Libretro 列表、
用户提供的 ROM/固件和 RetroArch 原生存档。
[Terminal](terminal.md)保留独立 PTY，切回桌面不会结束任务。

[Console](../console/README.md)显示应用状态、CPU、内存和存活时间。
详情提供打开、正常退出和强制终止；强制终止先确认。
应用激活仅接受内置或已监管的游戏窗口。

## 系统设置

语言首次默认英文，可立即切换简体中文。
Classic/Dark 与语言同步到已打开的内置应用，保留内容和会话。
视觉规则见[语言、主题与字体](../design/appearance.md)。

- Wi-Fi 先选网卡，再加入、断开或编辑配置。
  同名多配置先选具体配置；另一网卡占用的配置不能修改。
  详见[Wi-Fi 规范](../design/wifi-management.md)。
- 蓝牙区分配对与连接；PIN 和配对确认在本地弹层完成。
  失败保留实际状态。
- 音频选择输出、麦克风、静音和蓝牙模式。
  通话模式改变音质前先确认。
- 电池展示电压、电流和电池侧估算功率，缺少读数显示不可用。
  该功率不代表充电器输入功率。
- 亮度最低 5%；熄屏使用独立入口，不称作系统休眠。
- 接入 Micro-HDMI 后默认复制内屏，进入「设置 → 显示」可切换为扩展。
- 时区、系统信息、快捷键和键位测试见[系统设置规范](../design/system-settings.md)。
- 共享提供[网页访问](files-network-access.md)和 [SMB](sharing.md)，
  目录、网络与开放时长分别授权。
- 注销、重启和关机默认选中取消；锁屏和熄屏需现场验证恢复路径。

## 自动登录与回退

需要开机直接进入 uDeck 时，在源码目录显式运行：

```sh
sudo python3 tools/configure-login.py --user "$(id -un)"
sudo lightdm --show-config
```

工具备份 `/etc/lightdm/lightdm.conf` 到 `/var/backups/udeck/`。
它只写入经过校验的会话选择与自动登录配置，不触发重启或注销。
保存工具打印的备份路径。
自动登录允许接触设备的人直接进入该账号。

回退前保存全部工作。
恢复对应 LightDM 备份后，在现场注销或重启，
登录时选择原 Raspberry Pi Desktop on Wayland。
若未开启自动登录，可直接在登录界面选择原会话。
卸载前先恢复手动设置的自动登录和用户级默认终端。
卸载保留用户配置、内容与存档，见[发行指南](debian-distribution.md)。

## 诊断

```sh
udeckctl doctor --json
udeck-terminal --doctor
udeck-app reader --doctor
```

诊断是只读检查，设备枚举和进程存在不等于功能验收。
SSH 调试须使用实际图形会话的 Wayland、运行时目录和 D-Bus 环境。
Xwayland 还需要该会话的 DISPLAY 与必要的 XAUTHORITY。
测试步骤与证据层次见[验证规范](validation.md)。

[PROTOCOL]: Update this header on change, then check AGENTS.md
