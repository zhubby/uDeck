# uDeck Debian 发行与安装

目标为 **uConsole CM4 v3.1、arm64 用户空间、Debian 13 / Raspberry Pi OS Trixie**。用户安装的软件包名为 **`udeck`**，它安装完整套件。系统依赖通过镜像已有的 APT 源获取，因此安装时需要网络；套件压缩包不是离线系统依赖合集。

## 软件包

| 包 | 内容 |
| --- | --- |
| `udeck`（arm64） | 桌面壳、共享资源、labwc 会话、原生终端及 Music、Video、Browser、Reader、Emulator 全部应用 |

一个包统一版本、完整安装。安装器先卸载现有 `udeck`、`udeck-shell`、`udeck-terminal`、`udeck-apps`，再安装新包；开发阶段不提供旧包兼容、旧命令别名或旧状态迁移。源码按 common/media 和五应用模块组织。

## 镜像基线及证据边界

| 镜像 | 支持方式 |
| --- | --- |
| `uConsole_CM4_v3.1_64bit.img.bz2` | 主要安装目标；安装前必须检测实际发行版、用户空间架构、Python 和 APT 候选版本 |
| `uConsole_CM4_v0.1b_xfce_64bit.img.7z` | 官方 README 描述为 Bullseye/XFCE 基础；先备份并迁移到 v3.1，首版不提供旧系统原地运行时回移 |

上游镜像入口及旧版说明：[ClockworkPi uConsole README](https://github.com/clockworkpi/uConsole#uconsole-os-images)。[上游 pi-gen 的 uconsole_arm64 分支](https://github.com/cuu/pi-gen/tree/uconsole_arm64)目前配置为 Trixie，但分支内容不能替代发布镜像的根文件系统取证。

2026-11-09 已核对官方镜像索引、pi-gen 配置、Debian Trixie arm64 包索引与 Raspberry Pi 源。官方 v3.1 HTTP 入口返回 2,212,739,229 字节；下载速度不足，已停止并保留为临时 `.partial`，**没有完成镜像解包和 SHA-256 校验，不能据此宣称原始镜像已经通过安装或实机验收**。CI 的干净 Debian 容器和 Raspberry Pi 源验证覆盖依赖及安装生命周期，原始 SD 镜像与物理设备测试需另行记录。

## 系统组件清单

`debian/control` 是直接依赖的完整机器可读清单；Release 中以 `DEPENDENCIES.debian-control` 分发。以下按用途说明，APT 自动解析它们的传递依赖。

| 功能 | 必需组件 |
| --- | --- |
| 镜像硬件底座 | ClockworkPi 内核、设备树、CM4 启动固件、DRM/KMS/Mesa、键盘固件、背光与电池 sysfs；由镜像提供，不随 uDeck 替换 |
| Python | `python3 >= 3.11, << 3.14`、`python3-dbus-next`、`python3-evdev`、`python3-gi` |
| Qt 桌面 | PySide6 QtQuick、QtQml、QtDBus、QtMultimedia、QtQuickControls2；直接使用的 PySide6 模块固定 `>= 6.8, << 6.9` |
| QML 与图像 | QtQuick、Controls、Layouts、Window、WorkerScript、Templates QML 模块，`qt6-svg-plugins`、`qt6-wayland` |
| Wayland 会话 | `labwc >= 0.9`、`xwayland`、`wlr-randr`、`libwayland-client0`、`libxkbcommon0`、`xkb-data`、`procps` |
| 系统与授权 | `systemd`、`libpam-systemd`、`dbus-user-session`、`lxpolkit`、`tzdata`；沿用镜像显示管理器 |
| Wi-Fi 与热点 | `network-manager`、`wpasupplicant`、`dnsmasq-base`、`nftables`；不安装独立 dnsmasq 服务或修改原网络配置 |
| 蓝牙与音频 | `bluez`、`pipewire-audio`、`pulseaudio-utils`；`pipewire-audio` 依赖 `libspa-0.2-bluetooth`、PipeWire/Pulse 兼容服务及 WirePlumber |
| 文件、回收站与卸载 | `libglib2.0-bin`、`gvfs`、`udisks2`、`xdg-utils`、`shared-mime-info`、`hicolor-icon-theme` |
| 中文输入与字体 | `fcitx5`、`fcitx5-frontend-qt6`、`fcitx5-pinyin`、`fonts-noto-cjk`，加上随程序分发的界面字体 |
| 锁屏与熄屏 | `swaylock`、`swayidle`、`wlopm` |
| 原生终端 | QtWidgets、`libutempter0`、`xdg-terminal-exec`、随包编译的私有 QMLTermWidget；本机库依赖由 `dh_shlibdeps` 生成 |
| 五个原生应用 | QtWidgets、QtTest、QtWebEngineQuick/Core、QtPdf、QtMultimedia、对应 WebEngine/Multimedia QML 模块、`ffmpeg`、`ca-certificates` |

QtTest 当前用于浏览器实际交互，属于应用运行依赖。GVfs 主包的传递依赖提供本地回收站和 UDisks2 监视器；网络、手机、MTP 等后端作为 `gvfs-backends` 推荐安装。

推荐增强：`fcitx5-frontend-gtk3`、`fcitx5-frontend-gtk4`、`gvfs-backends`、`gvfs-fuse`、`retroarch` 及主仓库 GB/GBA/NES 核心。`libretro-snes9x` 位于 Debian `non-free`，只列为可选项，不自动添加源。游戏 ROM 和 BIOS 由用户提供。

**labwc 来源必须核对。** Debian Trixie 主仓库的 0.8.3 低于要求，需使用官方镜像已有的 Raspberry Pi 源。不要混入 testing/sid、替换系统 Python，或通过系统级 pip 拼装另一个 Qt。兼容检测记录 APT 主机与发行版信息，最终可安装性以 `apt-get -s install` 的实际求解为准。

测试容器使用官方 `raspberrypi-archive-keyring` 2025.1+rpt1，并校验下载包的 SHA-256 后启用签名仓库。2026 年的 APT 策略会拒绝旧下载页公钥中的 SHA-1 自签名；遇到对应错误时，应先更新官方 keyring，再重试安装。测试镜像的固定下载地址与校验值见 `tools/debian-test.Dockerfile`。

## 下载与安装

在 [GitHub Releases](https://github.com/zhubby/uDeck/releases) 下载 `udeck_<版本>_arm64.tar.xz` 和该 Release 的 `SHA256SUMS`。校验后解压：

```sh
sha256sum --ignore-missing --check SHA256SUMS
tar -xf udeck_<版本>_arm64.tar.xz
cd udeck_<版本>_arm64
python3 ./udeck-preflight --json
sh ./install.sh
```

`udeck-preflight` 只用 Python 标准库，旧镜像的 Python 3.9 也能运行。默认退出码 0 表示发行版、用户空间架构与 Python 满足目标条件；缺少的软件依赖单独列出，由 APT 安装。`--check-installed` 进一步要求桌面运行依赖齐全。检测通过不证明该 SD 镜像或硬件已经通过验收。

安装器先核对压缩包内的校验值、执行兼容检测，再运行 APT 更新索引和安装单个 `udeck` 包；APT 展示实际依赖变更供用户确认。不执行整机 `upgrade`、`autoremove`、固件刷写或显示管理器重启。

安装后：

```sh
udeck-preflight --check-installed --json
udeck --windowed
udeckctl doctor --json
```

`doctor` 保留原字段，新增 `system`，报告发行版、架构、包版本、缺失/不兼容组件、服务状态和背光可写性。无图形会话时 Wayland 诊断可失败；这与系统依赖检查分开解释。真实模式的文件、网络和音量操作会生效；安全预览使用 `udeck --mock --windowed`。

通过登录界面选择 **uDeck** 启动完整会话。安装保留原桌面与默认登录，并自动将 uDeck Terminal 设为系统默认终端。可选自动登录管理仍使用源码中的独立 `tools/configure-login.py`，终端默认管理使用 `udeck-terminal-default status/apply/restore --system`，无需验收 JSON。

输入读取与背光权限沿用镜像已有的 udev/logind/厂商规则。`rpi-backlight` 并非 Debian 主仓库依赖；已有硬件快捷键会调用它，检测报告是否存在。缺权限时显示不可用及原因，不给整个桌面 root 权限、不把用户加入通用 `input` 组。物理亮度键与设置滑杆分别验收。

## 升级、卸载与旧版迁移

开发阶段更新时解压新套件，执行其中的 `install.sh`。安装器先卸载已安装的四个旧包名，再安装一个完整 `udeck` 包；不执行旧包接管或状态迁移。安装前保存并关闭正在运行的应用。

卸载完整套件：

```sh
sudo apt-get remove udeck
```

卸载会撤销本包的系统默认终端配置；如曾手动配置用户级终端或 uDeck 自动登录，按各工具备份单独恢复。
不附带 `autoremove`。用户的 `~/.config/udeck`、终端与应用状态、媒体库和游戏存档保留。

旧 `v0.1b` 系统迁移流程：备份 SD 卡及用户数据，另备可恢复的网络/登录方式；使用新卡部署官方 v3.1，核对硬件驱动、系统发行版和 APT 源，再安装 uDeck。按需恢复主目录配置与媒体/存档；不整目录覆盖新系统的 `/etc`、系统 Python、Qt、网络和音频服务配置。不提供跨 Bullseye 到 Trixie 的自动就地升级脚本。

## 构建与 GitHub Release

Debian 源包采用 `3.0 (native)`，`debian/rules` 使用 debhelper 和 `dh_python3`；本机依赖由 `dh_shlibdeps` 自动计算。可在 Debian arm64 安装构建依赖后执行：

```sh
sudo apt-get update
sudo apt-get build-dep .
python3 tools/build-release --output dist/release
```

其他开发机使用容器：

```sh
docker build --platform linux/arm64 -f tools/debian-build.Dockerfile -t udeck-debian-builder .
docker run --rm --platform linux/arm64 -v "$PWD:/workspace" \
  udeck-debian-builder python3 tools/build-release --output dist/release
```

构建器在临时目录中构建插件及完整源码包，执行包括真实 PTY 的测试，再输出一个 arm64 `.deb`、`.dsc`、源码 `.tar.xz`、`.buildinfo`、`.changes`、套件压缩包、安装器、依赖清单、构建清单与 SHA-256。源码归档包含 vendor 原件、补丁和许可证，不包含硬件参考资料、虚拟环境或开发缓存。

GitHub Actions **只监听 `release: published`**，不监听 push、pull_request、tag push 或 workflow_dispatch。发布步骤：

1. 同步源码版本与 `debian/changelog`，提交构建所需文件。
2. 创建匹配的 `vX.Y.Z` 标签并发布 GitHub Release；草稿保存不触发构建。
3. Action 使用原生 arm64 runner 和 Debian 13 容器，校验标签、源码及 changelog，构建并运行软件包安装/卸载/重装与默认终端检查。
4. 所有检查通过后才将产物附加到该 Release。重新运行同一次发布会替换同名附件。

普通 tag push 只创建标签，不构建；从草稿转为已发布 Release 才构建。稳定版本格式为 `vX.Y.Z`，版本不匹配时停止。Release 构建禁止 `nocheck` 跳过测试。默认分支保留该工作流，发布标签也必须包含该工作流及打包文件。

## 验收层次

自动检查覆盖：版本拒绝、旧系统/armhf 拒绝、依赖缺失与 Qt/labwc 版本、原生插件/PTY、已安装包 QML/SVG 与五应用启动、源码对应、文件所有权、旧包先卸载、新包安装生命周期与默认终端实际启动。CI 使用 Raspberry Pi 签名 APT 源补足 labwc，且以 `--no-install-recommends` 安装，防止推荐包掩盖必需依赖。

尚需分别记录原始 v3.1 SD 镜像安装，以及 CM4 的完整登录/退出、1280×720 屏幕方向、ABXY/L/R、中文候选框、真实蓝牙播放、背光、电源、存储卸载和原桌面恢复。容器检查不把这些项目判为通过。

0.2.2 的历史四包验证记录保留在 `debian-release-2026-11-09.md`；0.2.3 单包结果见[单包发行验证记录](debian-single-package-0.2.3.md)。
现有 CM4 的实际升级、默认终端切换和软件检查见[0.2.3 实机部署记录](debian-device-0.2.3.md)，原始官方 SD 镜像纯净安装与人工硬件验收仍独立记录。
