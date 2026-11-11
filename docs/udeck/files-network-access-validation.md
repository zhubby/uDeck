# Files 网络访问验收记录

日期：2026-11-11。实现分支：`codex/files-network-access`。功能说明见 [Files 网络访问](files-network-access.md)。

## 验收范围

实现了本机 Files 的网络访问菜单、共享目录选择、多网络选择、永久与 1 / 6 / 12 小时时长，以及浏览器中的上传、下载和批量文件管理。网页使用现有 Logo、文件图标、Saira / LXGW 字体和 Classic / Dark 主题。

验证在独立工作树与 uConsole 隔离测试目录完成。设备的正式桌面和真实用户目录未替换、未作为测试共享目录；本记录不代表正式桌面部署。

## 自动化与界面

| 检查 | 结果与覆盖范围 |
| --- | --- |
| 网络文件测试 | 最新源码本地 22 项通过（1.75 秒）；设备 22 项通过（3.08 秒） |
| 相关回归 | 273 项通过（29.35 秒），覆盖 Files、文件任务与回收站、QML、图标、翻译、核心与设置菜单；13 条既有 dbus-next 弃用告警 |
| 目录与并发边界 | 上级/绝对路径、符号链接、特殊文件、父目录被移出共享范围、上传竞争、错误长度、复制与上传取消、断连后的 ZIP/上传清理 |
| HTTP 与批量操作 | Host / Origin、分页、Range、单项与批量下载、ZIP 空目录、重命名、保留两者、替换确认、移动、回收与部分失败 |
| 生命周期 | 永久配置恢复、端口占用、限时计时、会话 owner 消失、共享根目录替换、撤销网络后关闭已有连接、配置类型校验 |
| 网络身份 | NetworkManager 连接 UUID、Wi-Fi 永久 MAC、元数据缺失时撤销监听；这些用例不等同于真实网卡切换验收 |
| Files QML | 英文/中文 × Classic/Dark × 1280×720/960×600 共 8 组；菜单键盘操作及图标与两行文字块等高通过 |
| Chromium / WebKit | 桌面 1280×800 与手机 390×844、中英文与两种主题通过；无脚本错误或手机横向溢出 |
| 浏览器文件操作 | 上传、下载字节校验、文件夹上传与重名保留、拖拽文件/文件夹与空目录、复制、重命名、ZIP、回收站、列表、搜索与二次替换确认通过 |
| 静态检查 | 修改范围 Ruff、JavaScript 语法、`git diff --check`、离线依赖锁检查通过 |

273 项回归之后补充了“上传父目录移出共享范围”用例及对应防护，并重新验证最新的 22 项网络文件测试。设备 QML 使用 Python 3.13.5 / PySide6 6.8.2.1 的 offscreen 渲染，`qmlErrors: []`；本地使用 PySide6 6.8.3。设备上的 offscreen 渲染不代表正式桌面中的物理按键验收。

全量测试曾运行得到 **1328 passed、5 skipped、3 failed**，不能称为全量通过。后续核查结果：

- Native video 的 `videoSink() is None` 在当前源码与未修改基线的单独重跑中均通过，属于本次观测到的偶发现象。
- 翻译测试运行期间新增了三条文案，进程缓存了旧 catalog；新进程中的翻译与相关回归已通过。
- `test_all_qml_pages_render_without_engine_warnings` 在退出时因 QML controller context 变为空输出 TypeError。其 smoke 结果通过、`qmlErrors: []`，但 stderr 断言失败；同一问题已在未修改 HEAD 基线复现。本功能未扩展修改主程序的退出流程。

## 设备与独立客户端

设备：uConsole，`zhubby@192.168.11.59`。共享范围为 `/tmp/udeck-network-files-acceptance/share`，仅包含测试生成的文件与目录；配置、数据和 Python 环境均隔离。

通过产品客户端、本轮临时安装的 systemd 用户 unit 和设备真实会话 D-Bus 验证：

- 永久开启后用户 unit 为 enabled、linger 为 yes；重启文件服务后 PID 改变，新进程从保存配置自动恢复监听。
- 1 小时模式在测试 D-Bus owner 消失后自动关闭；随后恢复永久模式用于外部客户端验证。
- 所选 `wlan1` 连接仅监听 `192.168.11.59:8787` 与该连接的 IPv6 地址；未监听候选 `docker0` 地址。
- 最新 15 个产品源文件与本地源码 SHA-256 一致。

Mac 通过设备实际 HTTP 地址进行独立传输验证：

| 数据 | 结果 |
| --- | --- |
| 4,194,335 字节上传/下载 | 字节相等；SHA-256 为 `ee28a5fe7df764958ece78b1c6793119d3fe7f7ea23ce42bb2525fe03c3ea61a` |
| 同批 Range / 复制 / 重命名 / 移动 / 回收 / Host 拒绝 | 全部通过 |
| 同批 ZIP | 8,389,350 字节，内容与 CRC 校验通过 |
| 最新源码 65,567 字节上传/下载 | SHA-256 为 `655815109e024f9c50ebe8bbde69d83038563bb40144d6e1c816486d46c7584b`，同组文件操作通过 |
| 最新源码 ZIP | 131,814 字节，内容校验通过 |

## 打包

- 已构建 `udeck-0.2.3-py3-none-any.whl`，逐字节核对网络文件模块与网页源码，确认字体、Logo、入口与 aiohttp 依赖包含在包中。
- Debian 安装清单包含模块、启动器与用户 unit，并声明 aiohttp / QtNetwork 依赖。
- 设备 debhelper 13.24.2 已执行 `debian/rules` 中的服务集成目标：dry run 和隔离目录中的 maintainer snippet 生成均通过。使用 `dh_installsystemduser --no-enable`，首次安装不默认启用或启动网络访问。
- 设备临时测试 unit 的 `systemd-analyze --user verify` 通过。
- **未构建或安装完整 Debian 包。**上述检查不替代完整原生包构建与安装验收。

## 证据与剩余边界

本地证据保存在工作树的 ignored 目录 `artifacts/network-files/`：

- `device-http-report.json`、`device-http-final-report.json`：两组设备传输结果。
- `device-service-report.json`、`device-source-manifest.json`：服务恢复、监听与源码一致性。
- `debian-service-check.json`、`device-packaging-report.json`：Debian 服务集成检查。
- `shots/device-web-classic.png`：浏览器访问设备测试共享目录的截图。
- `qml/device-network-access.png`：设备 offscreen QML 菜单截图。
- `baseline/`：未修改 HEAD 的 QML 基线复现源码。
- `device-cleanup-report.json`：测试服务、linger、监听与隔离目录的最终恢复结果。

**未进行整机重启、真实 Wi-Fi 拔插/断网、真实 VPN 或其他物理网卡切换、正式桌面部署与物理按键操作。**永久模式已验证文件服务新进程恢复；开机恢复的整机验收仍待执行。

首次加载的 CJK 字体约 25 MiB，设备网络较慢时字体替换会稍晚；页面使用 `font-display: swap` 先显示系统字体，并缓存静态字体与图标。

设备验收结束后停止并移除本轮临时 unit，恢复测试前的 `Linger=no`，移除本轮隔离目录并确认端口不再监听。正常产品关闭功能只禁用文件服务，不修改可能被其他用户服务使用的 linger。
