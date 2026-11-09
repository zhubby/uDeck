# uDeck 0.2.3 单包发行验证

日期：2026-11-09。目标：uConsole CM4 v3.1 / Debian 13 Trixie arm64。
本记录来自本机 arm64 Debian 容器和 Qt 离屏验证；未安装到官方 SD 镜像或物理 CM4。

## 实现与交付

- 实现提交：`42c8cdae879506d42846a0dcc40d5b0c29c42d77`，已 fast-forward 合并至 `main` 并推送到 `origin`；本地 `main`、远端分支和实现分支的提交一致。本记录通过后续文档提交补充。
- 代码按 `common`、`media`、`music`、`video`、`browser`、`reader`、`emulator` 组织；各应用继续独立运行。
- Games 应用统一为 Emulator／模拟器，命令为 `udeck-emulator`，标识为 `io.github.zhubby.uDeck.Emulator`；Books 应用入口统一为 Reader／阅读器，沿用 Reader 标识。游戏和书籍等内容术语保留。
- 删除旧模块启动入口，不提供别名，不读取旧 Games 应用状态或复制旧存档。
- 只发行完整的 `udeck` 包，包含桌面、终端和五应用。新包与 `udeck-shell`、`udeck-terminal`、`udeck-apps` 冲突；安装器先卸载这三个旧分包及已安装的 `udeck`，不执行 `autoremove`。
- 安装时自动配置系统默认终端和 uDeck 会话入口，不需要验收 JSON；卸载时撤销本包注册并恢复先前默认配置，保留安装期间管理员后续作出的选择。

## 验证产物

- 单个 `udeck_0.2.3_arm64.deb`，大小 23,145,020 字节。
- SHA-256：`7e74ce99043938a031310a9f7999fc40f22957ce5dbc772ec60834df4785263f`。
- 同时生成 `.dsc`、对应 `.tar.xz` 源码、安装压缩包、构建元数据、依赖清单和 `SHA256SUMS`，共 12 个文件。外层校验和及安装压缩包内的校验和均通过；压缩包只包含一个 `.deb`。
- 本地构建目录为 `dist/release-0.2.3-final/`。这是预提交验证产物；归档生成早于最后两处测试夹具修正及本验收记录。二进制运行时源码和资源的全部 326 个文件已与实现提交逐字节核对一致，正式 Release 将从发布标签重新构建。
- GitHub Actions 仅监听 `release: published`，先完整构建和安装验证，再上传。本次未创建标签或 Release，未实际触发该 Action。

## 源码与界面验证

- 最终 Debian 原生测试：**1102 passed**，耗时 329.73 秒，另有 13 项上游 dbus-next 弃用警告；原生 QMLTermWidget 由 Qt 6.8.2 编译，未使用 `nocheck`。
- 99 项定向回归通过，覆盖模拟器索引、存档隔离、忽略旧状态、路由、安装器相对路径和系统默认终端恢复。
- 五应用 × 中英文共 10 项真实 QML 窗口测试通过，窗口标题和应用标识一致。
- 首页中英文变更前后检查共 4 组通过：四个标签、六个卡片、返回后焦点恢复，QML 错误为零；已检查 Reader／阅读器和 Emulator／模拟器截图。
- wheel 内 **326** 个 Python、QML、字体及资源文件与源码逐字节一致；五个新启动入口正确，旧 Games 命令和资源路径未进入 wheel。
- Foliate 等 13 个阅读器资源与重组前逐字节一致。许可证和上游来源保留在源码与安装载荷中。
- 原生测试包含实际媒体播放、控制与字幕、PDF／EPUB／TXT 阅读、浏览器交互、独立子进程核心探测和真实终端 PTY；这些结果不代表物理播放或商业游戏兼容性。
- Ruff、ShellCheck、actionlint 和 Git diff 空白检查通过；代码审查在主任务中顺序完成，未使用独立审查代理。

## 安装版验证

在干净的 Trixie arm64 容器中，使用 Debian／Raspberry Pi 签名依赖源和临时本地 APT 包索引，以 `--no-install-recommends` 安装 `udeck=0.2.3`。验证时 `labwc=0.20.2-1~bpo13+1`，`python3-pyside6.qtquick=6.8.2.1-4`。

- 桌面、终端及五个已安装应用入口均可启动；五应用使用独立 `gdbus` 客户端核对服务、接口、对象路径、doctor 和第二次启动路由。
- 原生终端插件和独立真实 PTY 探测通过。分别实际执行 `x-terminal-emulator`、`xdg-terminal-exec` 和 `XDG_CURRENT_DESKTOP=uDeck` 下的 `xdg-terminal-exec`；子进程确认标准输入输出均为 TTY，且父进程的 `/proc/<pid>/maps` 已加载本包的原生终端插件。
- 安装后的 326 个 Python／QML／资源文件与归档源码逐字节一致；两个已安装原生终端配色文件与模板一致，`dpkg --verify` 无差异。
- 通过真实安装器验证先移除四个旧名称软件包再安装新包。这里使用的是四个一次性同名哨兵包，用于验证卸载次序和文件清理，不表示已验证真实旧镜像或迁移旧载荷。
- 重复配置、覆盖重装、卸载、默认配置恢复和再次安装均通过。原 alternatives 为自动模式时，安装期间新增的更高优先级终端能在卸载后正确接管；桌面／登录配置夹具和用户数据保持不变。
- 独立安装推荐核心后，实际子进程 API 探测通过：Gambatte `v0.5.0`、mGBA `0.10.5`、Nestopia `1.53.0`。这验证了核心加载与查询，不代表实际游戏运行验收。

完整生命周期结果：

```json
{"packageLifecycle":"passed","installedSourceFilesChecked":326,"physicalAcceptance":"not checked"}
```

本地证据保存在忽略目录 `artifacts/0.2.3/`：`debian-build-final.log`、`package-lifecycle-verified.log`、`core-probe-installed.log`、`wheel-validation-final.json`、`bundle-validation.json`、`artifact-validation.json`、`home-rendering.json` 和 `review.md`。早期失败的测试夹具日志保留供追溯，最终安装结论以 `package-lifecycle-verified.log` 为准。

## 实机验收

以下项目仍需在 CM4 v3.1 的实际登录会话单独验收：官方镜像完整性与真实安装、原桌面及 uDeck 登录、重启、ABXY／L／R 实按、输入交接、中文输入法候选窗、音频／视频输出、模拟器实际游戏，以及持续性能与耗电。

安装会按要求自动切换默认终端；上述实机验收记录独立保存，不是安装或默认切换的 JSON 前置门槛。未对 `uConsole_CM4_v0.1b_xfce_64bit.img.7z` 提供兼容承诺。
