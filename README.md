# uDeck · 面向 uConsole 物理按键的桌面

uDeck 是面向 1280×720 横屏 uConsole 的原生 Qt Quick 桌面壳：方向键导航，A 确认、B 返回、X 上下文菜单、Y 快捷设置，L/R 切换页面，实体键盘输入文字。全屏真实模式在整个会话中屏蔽物理轨迹球和鼠标；独立会话中的第三方应用可使用按键导航或由手柄控制的虚拟指针。

基于现有 Debian 13 / labwc / Wayland 添加**独立可选会话**，不刷镜像、不改驱动、不替换合成器。软件包不修改原桌面配置或默认登录项；开机自动进入 uDeck 通过单独授权的配置工具开启。第三方应用使用自身焦点系统，Y 菜单切换按键、指针或原生输入模式。

当前基础包版本：**0.1.10**，原生应用包与独立终端均为 **0.1.3**。默认英文与经典主题，可在设置中切换简体中文及黑暗主题；英文界面使用 Saira Semi Condensed，中文界面使用 LXGW WenKai Screen（霞鹜文楷屏幕阅读版）。支持内置与 USB 多无线网卡分别管理，包含第三方应用手柄兼容层。完整兼容层仅在独立 uDeck 会话启用；自动化与窗口化实机验证不等同于物理按键、真实配对或完整登录会话验收。

## 桌面功能

- 主页与应用：标准 `.desktop` 条目、系统图标、收藏、最近使用、分类和搜索。
- 运行中：真实 Wayland / Xwayland 窗口列表、激活、请求关闭；独立会话为普通主窗口配置默认最大化。
- 文件：浏览、新建文件夹、重命名、复制、剪切/粘贴、明确确认覆盖、移入回收站。
- 设置：NetworkManager 多网卡 Wi-Fi（逐网卡扫描、连接、断开与热插拔）、BlueZ 配对代理、音量/静音/输出设备、背光、电池与充电状态、电源操作。
- 语言：`Settings → Language` 提供 `English` 和 `简体中文`；切换立即生效并保存，内置终端同步界面语言，保留终端会话和原始输出。
- 主题：`Settings → Theme` 和快捷设置提供 `Classic / 经典`、`Dark / 黑暗`；原生应用与终端窗口在一秒内跟随，网页、阅读夜间模式和终端文字配色独立保留。
- 输入：按实际前台窗口交接独立手柄，保留现有校准；普通字母和实体组合键不作按钮映射。壳内 L/R 切页；第三方按键模式中 A/B/X 为 Enter/Esc/Shift+F10，L/R 切换控件；指针模式支持点击、拖动与滚动，原生模式释放手柄。物理鼠标在壳失焦后继续屏蔽，退出壳时释放。

## 安全预览

建议 Python 3.13；支持 Python 3.11–3.13，Qt / PySide6 固定 6.8 系列。

```sh
python3.13 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/udeck --mock --windowed
```

`--mock` 不访问真实系统服务、不打开真实文件、不启动第三方应用，也不保存用户配置。

无显示器冒烟检查：

```sh
QT_QPA_PLATFORM=offscreen PYTHONPATH=src .venv/bin/python -m udeck.main \
  --mock --windowed --smoke-test --screenshot artifacts/preview-home.png
.venv/bin/python -m pytest -q
.venv/bin/ruff check src tests tools
```

## Debian 安装与运行

在 Debian arm64 设备上的源码目录构建、安装：

```sh
sh tools/build-deb
sudo apt-get install ./dist/udeck_0.1.10_arm64.deb
udeck --windowed
udeckctl doctor --json
```

安装只新增程序、依赖和会话入口；**不会重启显示管理器、切换当前会话或更改自动登录**。完整会话需在现场保存工作后，通过登录界面选择 **uDeck**；原 **Raspberry Pi Desktop on Wayland** 保留。

`Ctrl+Alt+Esc` 返回 uDeck、`Ctrl+Alt+Tab` 打开窗口切换器，仅在独立 uDeck 会话中生效。

如需开机自动进入全屏 uDeck，在源码目录中显式执行：

```sh
sudo python3 tools/configure-login.py --user "$(id -un)"
```

工具先备份 LightDM 配置，再设置默认和自动登录会话；不会自行注销、重启或删除原桌面。自动登录意味着能接触设备的人可以直接进入该用户桌面。保存工作后再安排重新登录或重启验证；具体配置与回退见下方记录。

## 文档

- [使用、构建、安装与回退](docs/udeck/README.zh-CN.md)
- [架构、输入边界与安全设计](docs/udeck/architecture.md)
- [2026-11-06 实机验证与现场验收清单](docs/udeck/acceptance-2026-11-06.md)
- [0.1.1 全屏与开机默认会话配置记录](docs/udeck/boot-2026-11-06.md)
- [0.1.2 ABXY 与 L/R 修复、实按事件记录](docs/udeck/input-2026-11-06.md)
- [0.1.3 手柄交互与会话级鼠标屏蔽](docs/udeck/controller-mode-2026-11-06.md)
- [0.1.4 应用操作、部署记录与待现场验收](docs/udeck/application-control-2026-11-06.md)
- [0.1.5 多无线网卡使用与验证记录](docs/udeck/multi-wifi-2026-11-06.md)
- [0.1.6 中英文界面、翻译约定与验证记录](docs/udeck/i18n-2026-11-06.md)
- [0.1.9 全局主题、配色与验证记录](docs/udeck/themes-2026-11-07.md)
- [0.1.10 中英文字体、离线资源与验证记录](docs/udeck/fonts-2026-11-07.md)
- [uDeck Terminal：构建、按键、输入交接、默认终端与恢复](docs/udeck/terminal.md)
- [uDeck Terminal：CM4 安装验收与待验项目](docs/udeck/terminal-acceptance-2026-11-06.md)

---

## uConsole 硬件资料库

本目录用于整理 ClockworkPi **uConsole** 的硬件、固件、系统构建和结构设计资料。整理日期：**2026-11-05（Asia/Shanghai）**。

## 从这里开始

- [硬件概览与阅读路线](docs/uconsole/硬件概览.md)：先理解主板、核心板、键盘、屏幕、电池及扩展模块之间的关系。
- [资料索引](docs/uconsole/资料索引.md)：按用途查找已经下载的 PDF、PCB、源码、结构模型和网页快照。
- [系统镜像下载入口](docs/uconsole/系统镜像索引.md)：保存官方镜像版本、下载链接和上游 MD5；大型系统镜像本体没有下载。
- [来源、完整性与使用边界](docs/uconsole/来源与边界.md)：区分官方资料、社区资料和整理者笔记，说明尚未验证的事项。

## 目录

| 路径 | 内容 |
| --- | --- |
| `references/uconsole/clockworkpi-uConsole/` | 官方仓库完整文件快照：装配手册、原理图、显示驱动资料、PCB、键盘源码、内核补丁、工具及固件 |
| `references/uconsole/clockworkpi-uConsole-wiki/` | 官方 GitHub Wiki 原始 Markdown 快照 |
| `references/uconsole/wiki-offline/` | 本地化 Wiki、产品说明与可获取配图；3 张 UART 附件下载失败，保留原链接 |
| `references/uconsole/raspberry-pi/` | CM4、CM5、参考 IO 板及相关芯片的官方资料 |
| `references/uconsole/components/` | 相关芯片资料；共享核心的资料不等同于整机兼容证明 |
| `references/uconsole/kernel/` | 官方镜像构建说明指定提交中的 uConsole 设备树及相关驱动节选 |
| `references/uconsole/community-3d-models/` | 社区粗略 FreeCAD 模型及预览；不适合严格公差，也不是官方商店原件 |
| `references/uconsole/web/` | 官方产品页、官方模型领取页和社区硬件/系统目录快照 |
| `references/uconsole/pdf-text/` | 从 PDF 提取的可搜索文本，阅读图纸仍以原 PDF 为准 |

原始文件保留上游名称和目录，不执行其中的刷写脚本。uDeck 的软件安装与设备操作边界见上方项目文档。

## 校验

在本目录运行：

```sh
shasum -a 256 -c references/uconsole/SHA256SUMS
```

来源 URL、仓库提交、下载时间、文件大小及校验值见 `references/uconsole/sources.json` 和 `references/uconsole/downloads.json`。
