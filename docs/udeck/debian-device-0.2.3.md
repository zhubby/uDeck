# uDeck 0.2.3 CM4 实机部署记录

日期：2026-11-09。本文记录现有设备的升级与软件验证；原始官方 SD 镜像纯净安装、物理操作及重启验收继续独立记录。

## 设备与安装

| 项目 | 实测 |
| --- | --- |
| 设备 | ClockworkPi uConsole，Raspberry Pi Compute Module 4 Rev 1.0 |
| 系统 | Debian 13.5 / Trixie，arm64，内核 `6.12.62-v8+` |
| 运行时 | Python 3.13.5，PySide6 6.8.2.1，labwc 0.9.2 |
| 已部署 | 单个 `udeck=0.2.3`，桌面、终端与五应用 |
| 源码基线 | `6aa4b947145b2b0316f36e023b8f1a4276d41c54`；326 个运行文件逐字节一致 |
| 二进制 | `udeck_0.2.3_arm64.deb`，23,145,020 字节 |
| SHA-256 | `7e74ce99043938a031310a9f7999fc40f22957ce5dbc772ec60834df4785263f` |

使用已验证安装压缩包中的真实安装器，先卸载设备上的 `udeck 0.2.0`、`udeck-apps 0.2.0`、`udeck-terminal 0.1.5`，再安装完整 `udeck 0.2.3`。设备未安装旧 `udeck-shell`。没有执行 `autoremove`、旧 Games 状态迁移或存档复制。旧 terminal 在 dpkg 中保留 `config-files` 状态，已不属于安装中的软件包。

安装前将旧包的 430 个文件及相关配置备份到设备的 `/var/backups/udeck-0.2.3-ecdkhvpa/`，目录权限 0700，文件权限 0600；私有配置备份没有取回或提交。现有闲置 Games、Reader、Video 窗口通过 Wayland 正常关闭；安装后只重启 `udeck-fullscreen.service`，没有重启合成器、显示管理器或设备。

## 依赖变更

设备已有音频服务，但缺少 `pipewire-audio` 元包。直接使用最新候选版本会连带升级相机和音频库，因此先核对依赖关系并安装与现有组件匹配的两个包：

- `pipewire-audio=1.4.2-1`：来自现有签名 Debian Trixie APT 索引；SHA-256 为 `a118a3b35bf8fa818612f74595640b96e1069af337987d79bca7ab5fdc534668`。
- `pipewire-alsa=1.4.2-1+rpt2`：通过 HTTPS 获取 [Raspberry Pi 官方归档中的对应版本](https://archive.raspberrypi.com/debian/pool/main/p/pipewire/pipewire-alsa_1.4.2-1+rpt2_arm64.deb)，核对包名、架构和精确版本依赖；SHA-256 为 `25a6e2f7e8b27f2e68abf43196279c9a2af048e605101d1997319f97f12e26ab`。

实际只新增这两个依赖包；原有系统组件未升级，`pipewire 1.4.2-1+rpt2` 与 `libcamera0.6 0.6.0+rpt20251202-1` 保持原版本。没有新增 APT 源、持久化版本锁定或替换系统 Python。安装器使用临时 APT 配置自动确认并关闭推荐包安装，安装日志确认只移除三个旧 uDeck 包、再新增一个完整 uDeck 包。

## 已通过的安装版检查

- `udeck-preflight --check-installed --json` 通过；`dpkg --verify udeck` 无差异；安装后的全部 326 个 Python、QML、字体和资源文件与源码基线一致，原生终端插件哈希与安装元数据一致。
- 新桌面已在真实 Wayland 会话运行，诊断为 `version=0.2.3`、`ready=true`，窗口协议可用；Wi-Fi、蓝牙、音频、亮度和电池后端均为 available，`serviceErrors` 为空。本轮并行验证期间首次帧报告为 5.413 秒，不据此宣称启动性能达标。
- 五应用的隔离启动、真实 QML 冒烟、独立 `gdbus` 客户端、第二次启动路由均通过。原生终端探针与三种默认终端入口检查也通过，合计 21 个记录检查项。
- 在实际 Wayland 合成器上启动五应用 × 中英文，共 10 个窗口；独立窗口观察器确认正确的应用 ID 和本地化标题，保存截图且 QML 错误为空。包括 `io.github.zhubby.uDeck.Emulator` / `uDeck Emulator` / `uDeck 模拟器`，以及 Reader / 阅读器。
- 系统 alternatives 为 `manual -> /usr/bin/udeck-terminal`；系统及 uDeck 专用 XDG 列表首项均为 `io.github.zhubby.uDeck.Terminal.desktop`。
- 分别真实执行 `x-terminal-emulator`、`xdg-terminal-exec` 和 `XDG_CURRENT_DESKTOP=uDeck` 下的 `xdg-terminal-exec`。在独立 D-Bus 会话中，子进程确认 stdin/stdout 为 TTY，父进程映射了本包的原生 QMLTermWidget 插件。
- 安装版独立子进程核心 API 探测通过：Gambatte `v0.5.0`、mGBA `0.10.5`、Nestopia `1.53.0`。本轮没有把 API 探测算作游戏运行验收。
- 原桌面和登录配置的 16 个文件哈希未变，labwc 原进程保留，NetworkManager、BlueZ、LightDM 持续 active。既有终端及其 zsh 进程保留；它们继续使用已加载的旧版代码，关闭旧窗口后再启动会加载新安装版本。

设备验证材料保存在 `/var/tmp/udeck-0.2.3-jiykpu1_/`；本地副本位于忽略目录 `artifacts/0.2.3/deployment/device-evidence/`。材料包括安装日志、依赖来源、逐文件校验、默认终端 PTY 结果、核心探测、Wayland 窗口清单和 10 张窗口截图。登录凭据没有写入这些材料或仓库。

## 仍需人工验收

本轮没有刷写或校验原始官方 v3.1 SD 镜像，没有进行注销、重启或关机，也没有确认物理 ABXY／L／R、真实中文输入法候选窗、蓝牙音频输出、音视频观感、实际游戏、USB 热插拔、持续性能或耗电。

安装默认终端的切换已完成，不依赖人工验收 JSON。构建与容器验证见 [0.2.3 单包验证](debian-single-package-0.2.3.md)；本次没有创建标签或 GitHub Release。
