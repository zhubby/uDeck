# 轨迹球点击与全局控制台

2026-11-10，基于 uDeck 0.2.3。发行继续使用单个 `udeck` 包；本次不创建 GitHub Release。

## 输入行为

- 仅识别内置 `ClockworkPI uConsole Mouse` 的 `BTN_MIDDLE`（274），不修改外接鼠标中键或 L/R。
- 短按在松开时发出一次左键；持续按住严格超过 2 秒发出一次右键，之后松开不再发出左键。使用内核单调事件时间戳与精确定时器；事件积压、下按和松开一起读取时仍能识别长按。内核不支持切换事件时钟时退回读取时的单调时钟。
- 壳内保持按键导航，左键确认当前选中项、右键打开上下文菜单；其他应用通过 Wayland 虚拟指针接收真实左/右键按下和松开，并接收内置轨迹球移动与滚轮。长按右键与延后左键意味着轨迹球按住不进行拖动；原有手柄 A 拖动仍保留。
- 拔插、丢帧、设备关闭、焦点改变、进入测试/校准、会话失活或锁屏取消未完成的手势。设备恢复产生的诊断松开不算点击。测试页仍显示原始轨迹球事件，不注入左/右键。
- 全屏真实模式持有物理接口，虚拟指针直接进入合成器，不经过 evdev，因此不会反馈循环。窗口化与 `--no-input` 模式不接管硬件。
- 原桌面与独立会话均监控当前图形会话的 logind 状态；网络或蓝牙初始化失败不阻断会话监控。会话不可用、失活或锁屏时不注入点击、不打开控制台。完整手柄兼容层仍由独立 uDeck 会话启用。

## 控制台

`Ctrl+Shift+Esc` 或 `udeckctl console` 打开控制台，提供回到主界面、运行中、设置、关机、重启。方向键和 A/Enter 选择，Esc/B 关闭并恢复原应用。重复快捷键不堆叠菜单，不丢失已打开的确认框。关机和重启沿用 logind 与现有二次确认，默认选中取消。

独立 uDeck 会话已经包含全局绑定。它由 labwc 消费，在终端、原生应用或第三方应用前台时都可打开；普通 QML 窗口内也提供相同快捷键，包含按键测试页。

在原有 Raspberry Pi / labwc 桌面中运行全屏 uDeck 时，执行一次：

```sh
udeckctl bind-console
```

命令要求已有、属于当前用户的 `~/.config/labwc/rc.xml`（遵循 `XDG_CONFIG_HOME`）。支持 `labwc_config` 和原桌面的 `openbox_config`，保留原有 XML 命名空间。先把原始字节以 0600 权限备份到 `~/.local/state/udeck/shortcuts/`（遵循 `XDG_STATE_HOME`），再添加/替换 `Ctrl+Shift+Esc` 的绑定并请求 labwc 热重载。保留其余快捷键、主题、注释及文件权限；重复执行不重复备份或添加。若原来同一组合键启动任务管理器，该绑定会被替换；返回的 JSON 提供原配置备份路径。恢复时把该备份复制回原路径并执行 `labwc --reconfigure`。快捷键配置不修改 LightDM、默认桌面、自动登录或系统默认终端。

通过 SSH 启动临时用户服务时，需从实际 labwc 图形会话继承 `XDG_SESSION_ID`、`XDG_SESSION_TYPE`、`XDG_SEAT`、`XDG_VTNR`，并设置已核对的 `WAYLAND_DISPLAY`。执行热重载还需该合成器的 `LABWC_PID`。SSH 自身的登录会话不能代替图形会话，也不要通过设置 `UDECK_SESSION=1` 绕过独立会话校验。

## 验证记录

- Debian 13 arm64 / PySide6 6.8.2.1：最终 Debian 构建内全量 **1154 passed**，包含真实原生终端插件、PTY、五应用和 QML 回归，无跳过。通过 `debian/rules` 执行，未使用 `nocheck`。
- 补充内核时间戳处理后，输入、控制台、快捷键配置、CLI 和兼容路由 **81 项针对性回归通过**；包含下按/松开积压读取、严格 2 秒边界、重复事件、恢复不点击、锁屏与焦点丢失，以及两语言 × 两主题 × 两尺寸的 QML 检查。
- `tools/verify-trackball-console.py` 在独立 Debian arm64 / labwc 0.8.3 合成器中，分别对独立 Wayland、Xwayland Qt 客户端验证真实鼠标 `down:1 / up:1 / down:2 / up:2`；全局组合键通过合成器执行独立 `udeckctl` 进程，再通过 D-Bus 打开控制台，Esc 恢复同一原窗口。输入恢复不生成点击。该合成器验证不替代 CM4 的 labwc 0.9.2 实机验收。
- Ruff 与 `git diff --check` 通过；面板截图已人工检查。验证输出与截图保存在忽略目录 `artifacts/trackball-console/`。
- main 原有加载动画、圆球光标与本次改动整合后，**109 项回归通过**，加载/QML 整合检查也已通过；原有未提交工作保持未提交。
- 原桌面配置的 Openbox 根元素与命名空间、无独立会话标记时的 logind 更新、网络初始化失败后的会话监控均有回归覆盖。构建还复现并修复了文件任务完成后被迟到进度恢复为运行中的竞态，以已完成 worker 的排队事件确定性验证。

## CM4 部署记录

2026-11-10，已在 `192.168.11.59` 的 Debian 13.5 arm64 / labwc 0.9.2 原桌面部署最终 `udeck_0.2.3_arm64.deb`。包对应代码提交 `f6b6d16b4834cea8f7de908ad63b6ee0951583ee`，构建工作区干净；SHA-256 为 `bcb98a48368307f4f8493e084d2ed6de7fba809882a0beea262a89c23f5f32a3`。后续验收文档提交不改变该二进制的来源。

- 安装前校验整个安装压缩包的校验清单；先卸载已安装的 `udeck` 和三个旧分包，再安装新包，未执行 `autoremove`。`dpkg -V udeck` 通过，正式进程使用 `/usr/lib/python3/dist-packages/udeck`，已移除临时源码覆盖环境。
- 已安装包在实机 Wayland、Xwayland 客户端中收到一次左键与一次右键的完整按下/松开序列；合成组合键经过真实 labwc 全局绑定及独立 `udeckctl` 进程打开面板，Esc 恢复相同原窗口。主页、运行中、设置三个入口通过实际面板选择与 D-Bus 状态验证。
- `udeckctl bind-console` 重复两次均返回 `changed: false`。原始 labwc 配置备份与安装前字节哈希一致；LightDM 配置和 `.dmrc` 与安装前一致，未改变原桌面或默认登录方式。
- `x-terminal-emulator`、`xdg-terminal-exec` 均在私有 D-Bus 中启动新终端进程，实际入口解析为 `/usr/bin/udeck-terminal`。两者标准输入、输出、错误均为真实 PTY，`TERM=xterm-256color`；记录了新进程 PID、入口路径及哈希，未复用或关闭用户原有终端。
- `udeckctl doctor --json` 显示真实壳已呈现首帧、物理输入已接管、轨迹球指针无错误；原桌面继续保留完整手柄应用兼容层需要独立 uDeck 会话的边界。

日志、诊断、探针及两张实机控制台截图保存在本地忽略目录 `artifacts/trackball-console/device/`；构建全量测试日志为 `artifacts/trackball-console/build-verified.log`。代码提交已合并到 `main` 并推送，现场软件复验使用正式安装包，不创建 Release。

真实物理轨迹球下按、长按手感、外设以及关机/重启仍需实机人工验收。模拟输入、设备枚举、软件启动与实机部署分别记录，不替代物理验收。
