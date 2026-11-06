# uDeck Terminal v1 — CM4 安装验收记录

日期：2026-11-06。软件已实现并安装，自动验收和性能门槛通过。真人实按、真实中文输入法及硬件异常恢复仍待观察，因此没有应用系统默认设置；当前仍为 `auto → /usr/bin/lxterminal`。

## 构建与设备

| 项目 | 实际值 |
| --- | --- |
| 设备 | ClockworkPi uConsole / CM4，aarch64 |
| 系统 | Debian 13.5，Linux 6.12.62-v8+ |
| 图形环境 | labwc 0.9.2，Wayland 与 Xwayland 分别验证 |
| Qt / PySide6 | 6.8.2 / 6.8.2.1-4 |
| 已安装包 | `udeck 0.1.4 arm64`、`udeck-terminal 0.1.0 arm64` |
| 终端构建 ID | `5339088bbd72cdf484a0fdb5fcf57fd34b1663036fb904e7da71f8e77d04d93a` |
| ARM64 插件 SHA256 | `8e9fbddbafda7994c061172bdd4ce4a4f603f9f9f2b2cfb9c29e0d96b38169be` |
| QMLTermWidget 上游提交 | `8913504fa2ebd220ebe7c680c32954e1b3c035c5` |

实现位于隔离工作树 `/Users/zhubby/.codex/worktrees/udeck-terminal-v1/uDeck`，分支 `codex/udeck-terminal-v1`，基于 `45af5921bfb8b44df36028053f9f296bd6575103`。实现期间保留原工作区及其硬件资料；本记录初次采样时尚未提交，后续 Git 交付见仓库历史。

设备构建与验收目录为 `/home/zhubby/udeck-terminal-v1-20261106`。安装前基础包备份位于该目录的 `artifacts/pre-install/`；默认配置尚未修改，不存在正式 apply 的恢复清单。

## 自动验收结果

| 范围 | 结果与证据 |
| --- | --- |
| 完整测试 | 本机 157 passed / 17.46 秒；CM4 157 passed / 35.47 秒。均有 13 条既有 dbus-next 弃用警告 |
| 静态检查 | `ruff check src tests tools` 通过；补丁可从固定上游重建当前修改文件 |
| 原生 PTY | 中文、空格、引号和空参数逐项传递；cwd、调用方环境隔离、resize/SIGWINCH、前后台进程组回收通过 |
| 原生缓冲与输入 | 宽字符/组合字符选区、普通文本搜索、bracketed paste、控制字符和不追加回车通过 |
| IME 底层接口 | 合成 QInputMethodEvent 提交、候选矩形查询、UTF-16 光标偏移通过；不等同于真实输入法验收 |
| 产品生命周期 | 稳定多标签、窗口/标签确认关闭、取消后继续运行、最小化后继续输出、自然/异常退出移除通过 |
| 安装版 Wayland / Xwayland | 实际 QQuickWindow 快捷键、弹层隔离，以及 Esc、功能键、方向键、Ctrl、普通字母到 PTY 的字节通过 |
| 真实 TUI | 两种图形路径均完成 Vim 编辑保存退出、less 滚动搜索退出、tmux shell/分离，以及 Codex CLI 0.130.0 编辑器呈现和按键退出 |
| Codex 验证边界 | 使用账户已有信任目录，未修改信任设置，未提交提示词或模型请求 |
| 安装版 CLI / D-Bus | 普通启动激活、显式参数新窗口、错误目录/程序提示通过；已有主进程时文件页指定目录确实创建对应 cwd 的窗口 |
| 输入所有权 | 原桌面前台取得内置接口，失焦释放、重新前台再取得；uDeck PointerGuard 持有鼠标，终端持有 ABXY，Home 后释放 ABXY 并保留 shell |
| 默认入口隔离演练 | 真实 update-alternatives、xdg-terminal-exec、Gio Terminal=true 和强制缺 GI 后备路径均启动安装版；恢复 auto 状态及绑定 XML 原字节通过 |
| 包完整性 | 基础包 25 个、终端包 71 个常规文件与设备安装内容逐字节一致；权限/属主正确，无重叠文件；插件为 AArch64 且所有动态依赖可解析 |

TUI 键盘测试使用 Qt 合成事件。输入所有权测试读取实际设备 grab 状态，但没有证明实体按键或轨迹球的操作结果。默认入口演练使用隔离的 alternatives 数据库、链接和 XDG 配置，不能代替正式系统默认入口的验收。

## CM4 性能采样

采样对象为当前安装构建，单窗口、单本地 zsh，会话空闲，持续 **60.0396 秒**。采样前后校验运行进程启动时缓存的构建 ID 与已安装包一致。

| 指标 | 结果 | 门槛 |
| --- | --- | --- |
| 进程启动至首帧（含 Python / Qt 导入） | 1.998 秒 | ≤5 秒，通过 |
| main 入口至首帧（辅助值） | 1.003 秒 | 单独记录 |
| 终端主进程最大 RSS | 195.609 MiB | ≤250 MiB，通过 |
| 空闲 CPU，单逻辑核心口径 | 0.01666% | ≤3%，通过 |
| 直接子进程 zsh | RSS 5.555 MiB，CPU 0% | 与主进程分列 |

## 未完成的关键验收

- [ ] uDeck 下实际 ABXY、方向键、L/R 边界与弹层隔离、轨迹球不操作终端。
- [ ] 无鼠标历史选区复制、搜索、危险粘贴预览、字体调整、确认关闭和取消操作。
- [ ] Y 打开快捷设置；返回主页或切换应用后任务继续。
- [ ] 真实中文输入法：预编辑、候选框位置、中英文混排、宽字符及组合字符。
- [ ] 原桌面下同样实按；失焦不抢键，返回动作最小化且任务继续。
- [ ] 实际焦点往返、可操作的输入设备断连/恢复及事件丢失后的按住状态恢复，无重复触发。

用户反馈暂时不方便实测，因此 `ime-cjk`、`physical-udeck-input`、`physical-original-desktop-input` 和 `focus-hotplug-dropped-events` 保持 pending。只读调用 `validate_acceptance()` 已确认上述 pending 项会阻止默认设置；没有为测试该门槛执行全局 apply。代码提交与合并不代表这些实机项目通过，也不会改变默认终端。

## 正式默认切换与恢复演练

全部关键项通过后，才更新对应构建的验收 JSON，并运行使用手册中的 `udeck-terminal-default apply`。本次用户已授权实施方案，后续无须重复询问是否同意该方案，但不能以授权代替未观察的验收结果。

执行后须在图形用户会话运行 **`labwc --reconfigure`**，然后逐个观察实际启动结果：Debian alternative、XDG、uDeck 快捷键、文件页指定目录、应用列表、Gio 及缺 GI 后备路径、原桌面快捷键和文件管理器。记录 PID、安装模块及 cwd，不能仅根据配置已写入认定通过。

随后用 apply 返回的 root 私有备份恢复原 alternative 的 auto/manual 状态和配置字节，再执行 `labwc --reconfigure` 并复验原入口；恢复演练成功后按计划重新应用。上述**全局默认切换、所有正式入口回读及全局恢复演练尚未执行**。

## 交付文件与复现

`dist/` 中提供两个 arm64 Debian 包、完整源码包、交付总包和 SHA256SUMS。总包包含使用手册、本记录、固定上游源码/许可/补丁以及 `evidence/` 中的原始记录。构建命令、CLI、实体按键和恢复工具见 [terminal.md](terminal.md)。

关键证据为 `cm4-terminal-acceptance.json`（汇总与未完成项）、`cm4-terminal-performance-raw.json`（未改写的采样）、`package-validation.json`、`installed-*-probe.json`、`installed-input-ownership.json`、`installed-default-rehearsal.json`、`default-gate-validation.json` 和两端测试日志。Codex 编辑器截图分别保留 Wayland 与 Xwayland 版本。

后续修改终端安装内容或原生插件会改变构建 ID，必须重建、安装并重新验收；不得沿用本记录给其他构建放行。
