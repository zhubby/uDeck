# uDeck Logo 定稿与接入验证

用户于 2026-11-10 确认采用 v6。正式 SVG 保留定稿的全部路径和配色，文件 SHA-256 为 `5f9cc342bce14935e47f202ade61442fb04013905caa9f7d7592fdc67354b3d9`。

## 接入位置

- `src/udeck/assets/branding/udeck.svg`：运行时的正式源文件。
- `packaging/udeck.svg`：Debian 桌面安装图标，与正式源文件逐字节一致。
- `src/udeck/qml/BrandLogo.qml`：共用显示组件，用于首页左上角、启动加载页、五个内置应用的页眉和终端页眉。
- `src/udeck/main.py`：桌面窗口图标。
- `docs/design/branding/udeck-logo.png`：正式透明 PNG，与获准的 v6 PNG 一致。
- 项目 README 使用正式 SVG。

## 验证结果

在 macOS 上使用 Python 3.12.14、PySide6 / Qt 6.8.3，以隔离配置、offscreen 和软件渲染运行现有检查：

```sh
python -m pytest -q --tb=short tests/test_home_qml.py tests/test_launch_qml.py tests/test_theme_qml.py
```

结果为 **27 passed**，耗时 79.75 秒。覆盖 1280×720 / 960×600，中英文，经典 / 黑暗主题，加载动画与减少动态效果、键盘焦点恢复，以及八个现有窗口中的主题同步与会话保持。截图中首页、启动页、Reader 和终端均显示新 Logo；未出现 QML 错误。

执行 `python -m build --wheel --no-isolation`，生成 `udeck-0.2.3-py3-none-any.whl`。检查归档内容，确认包含正式 SVG、共享 QML 组件与各调用位置，归档中的 SVG 和组件均与源码一致。Debian 安装规则包含整个运行时 assets 目录与可缩放安装图标；此阶段未构建 arm64 Debian 包，后续实机安装见下文。

验证报告与保留截图位于本地 `artifacts/branding-v6-validation/`，包括 `render-verification.json`、`package-verification.json`、首页、启动页和应用截图。

## uConsole 实机安装与截图（2026-11-10）

已将 v6 安装到 `clockworkpi`（uConsole / CM4，Debian 13.5 arm64，Qt 6.8.2）。采用有备份的定向运行时更新，共安装并逐一校验 8 个文件；已安装软件包版本仍为 `0.2.3`，本次没有重建或安装新的 Debian 包。

设备应用页眉所在的 `apps/common/qml/Main.qml` 使用此前安装的列表与加载实现，因此只将原有 `uD` 文字替换为 `Shared.BrandLogo`；没有用本地较新版本覆盖整个文件。部署清单记录原文件、新文件的 SHA-256 和该适配方法。

先用设备上实际安装的 Python 模块完成以下 offscreen 检查，全部通过，QML 错误均为零：

- 1280×720 英文经典主题首页、导航与焦点恢复。
- 960×600 中文黑暗主题首页、导航与焦点恢复。
- 隔离运行 Music 的共享应用页眉及现有 smoke 检查。

随后只终止旧桌面 shell，由当前正式登录会话的监督脚本启动新 shell。父会话、labwc、LightDM、音频进程以及已经打开的 Reader（PID 2521）和 Emulator（PID 3322）均保留原进程身份。重新加载后检查实际 D-Bus 状态：`mock=false`、`page=home`、窗口协议可用、无服务错误，指针会话正常。原配置、会话脚本与图标别名保持一致；运行时包内只有预期的 7 个文件发生变化，另有 1 个系统图标更新。已经打开的应用保留其内存中的旧页眉，下次启动会加载新 Logo。

通过真实 Wayland 输出 `DSI-1` 使用 `grim` 截取首页，并将屏幕恢复到截图前的关闭状态。实机原始截图 SHA-256 为 `9fa7d987834068583eb0357bebc17d5517de923e605096cc251e81bdfafbd148`。

本地证据位于 `artifacts/branding-v6-device/logo-v6-20261110-01/`：

- `device-home.png`：真实设备首页截图。
- `verification.json`、`doctor-final.json`：安装清单、进程/配置保持与真实桌面状态。
- `offscreen-validation.json`：设备 Qt 上的隔离渲染检查，和真实桌面截图分别记录。
- `source-manifest.json`、`before.json`、`backup/`：安装与回退依据。

设备备份保存在 `/home/zhubby/.local/state/udeck/deployments/logo-v6-20261110-01/backup/`。需要回退文件时，可在设备上执行同目录的 `python3 deploy-logo.py rollback`，它会校验并恢复原文件；该命令不会自动重启当前桌面或应用。

## 按主题实时配色与实机复验（2026-11-10）

用户随后要求 Logo 随主题配色。`BrandLogo.qml` 将同一份 v6 SVG 的两种颜色绑定到现有共享色板，再通过 SVG data URL 显示：经典主题前景为暖金色 `accent`，黑暗主题前景为浅色 `text`，背景使用当前界面的 `background`。首页、启动页、应用与终端页眉都显式传入当前色板，主题变化时立即重新着色，无需重建窗口。模板还原两种色值后，与正式 SVG 逐字节一致；轮廓、比例、透明度与元数据均未改变。独立 SVG 与系统安装图标仍保留原始灰白版本。

在现有主题渲染检查中增加对实际 Logo 图像像素的检查：原先固定颜色的实现会因黑暗主题前景像素数为零而失败，修改后通过。本地以 Python 3.13.18 / Qt 6.8.3 再次运行上述三个测试文件，结果 **27 passed in 83.59s**，包含八个窗口的实时主题同步和会话保持。

设备定向更新 5 个 QML 文件，继续保留应用页眉所在文件的旧列表/加载实现。设备 Qt 6.8.2 的经典 / 黑暗首页与共享应用页眉隔离检查均通过，无 QML 错误；重新加载真实 shell 后，通过现有快捷设置菜单完成经典 → 黑暗 → 经典切换，两个主题的首页均由真实 `DSI-1` 输出截图。实际截图 Logo 区域分别测得暖金色和浅色像素，确认颜色已在设备生效。合成 Wayland 键盘事件用于操作菜单，不代表物理按键验收。

最终核对 5 个文件的哈希、包内改动范围、用户配置和原有 Reader / Emulator 等进程，均符合预期。主题和屏幕电源均恢复到测试前状态。没有重建或安装新 Debian 包，版本仍为 `0.2.3`。

本地证据位于 `artifacts/branding-theme-device/logo-theme-20261110-01/`：`verification.json`、`theme-captures.json`、`artwork-verification.json`、`device-home-classic.png`、`device-home-dark.png`；`device-logo-themes.png` 是两张真实截图页眉的并排放大裁剪。设备同名部署目录中的 `backup/` 保留本次安装前的文件。
