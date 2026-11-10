# uDeck 自有终端方案调研

调研日期：2026-11-06，Asia/Shanghai。

## 建议

建议维护一个独立的 **uDeck Terminal** 应用：使用与桌面相同的 PySide6 / Qt Quick，接入 Qt 6 版 **QMLTermWidget**，自行实现适合 uConsole 的全屏布局、ABXY 菜单、L/R 会话切换、无鼠标复制与历史浏览。

维护边界是「uDeck 终端产品 + 明确记录的终端组件补丁」。终端协议、PTY 和屏幕状态优先复用组件。登录 shell 继续使用用户已有的 bash/zsh；SSH 交给 OpenSSH。这些与是否使用系统自带的终端应用是不同层次。

这是优先做原型验证的路线。QMLTermWidget 已迁移 Qt 6，但本轮没有编译、安装或运行候选终端；其在 CM4、Qt 6.8、labwc、fcitx5 上的表现仍需验证。若中文输入、目标 TUI 或维护差距无法接受，优先转用发行版 QTermWidget 做独立 Qt Widgets 应用；若长期需要更现代的终端内核，再评估 libghostty-vt。

## 当前项目约束

本轮读取当前仓库源码和文档确认：

- 桌面为 PySide6 / Qt Quick，Qt 固定 6.8 系列；目标环境记录为 CM4、约 4 GiB 内存、Debian 13、labwc / Wayland、1280×720 横屏。
- 方向键导航，A 确认、B 返回、X 菜单、Y 快捷设置，L/R 上一页和下一页；实体键盘负责文字输入。
- ABXY 来自独立手柄接口，桌面失焦时释放；L/R 实际来自内置鼠标接口，由 `PointerGuard` 持续独占。鼠标移动、点击和滚轮在会话内禁用。
- `packaging/labwc/rc.xml` 的 `Ctrl+Alt+T` 当前执行 `x-terminal-emulator`。
- `DesktopCatalog.launch()` 在 Linux 优先使用 Gio 启动 `.desktop`；只有缺少 GI 的后备路径才自行将 `Terminal=true` 包成 `x-terminal-emulator -e …`。因此接入自有终端不能只改这一个后备调用。
- 桌面的 D-Bus 控制接口当前没有终端会话或按键转交接口。

以上是仓库现状，设备运行状态没有在本轮重新采样。既有实机记录见 [架构](architecture.md) 和 [手柄模式](controller-mode-2026-11-06.md)。

## 候选比较

下表的适配工作量是基于当前项目的工程判断，不是性能实测或固定工期。

| 路线 | 如何维护自有终端 | 主要收益 | 主要投入与限制 | 对 uDeck 的建议 |
| --- | --- | --- | --- | --- |
| **Qt Quick + QMLTermWidget** | 自有 QML 界面、Python 控制器，打包 C++ QML 插件 | 和现有界面最一致；组件已有 PTY、VT、滚动历史、搜索、剪贴板、输入法入口 | 需要自己打包插件；原生无鼠标选区接口需要补充；分支内含终端核心源码，需要跟进上游修复 | **首选原型** |
| **Qt Widgets + QTermWidget** | 新建自有原生 Qt 终端应用，使用发行版终端库 | Debian 13 有 Qt 6 / arm64 包；可复用的组件接口较完整，依赖维护方便 | 属于 QWidget；不能直接作为 QML Item 使用；自定义外观和焦点交互要另做，官方 Python 绑定是 PyQt 而非 PySide | **稳妥备选** |
| **Qt Quick + libghostty-vt** | 自有 Qt 终端视图、PTY 和会话层，C API 接内核 | 现代 VT、Unicode、重排、搜索、输入编码等能力；MIT 许可 | 库不提供可直接使用的 Qt 终端控件；要维护绘制、字体、输入法、PTY 等；1.0 前 API/ABI 可能变化 | **长期候选** |
| **WebView + xterm.js** | 自有网页界面，原生进程连接 PTY | 浏览器终端生态成熟，官方文档列出 CJK、IME、TUI 支持 | 当前 Qt 工程需要新增 WebView/浏览器运行时与桥接层；整体资源和生命周期需要单测实机 | 有 Web 终端共用需求时考虑 |
| **GTK + VTE** | 自有 GTK 应用使用 VTE 控件 | 成熟的原生终端组件 | 新增 GTK UI 与输入适配；无法直接复用现有 QML 界面 | 当前优先级低 |
| **整体改造 QMLKonsole** | fork 完整应用，替换其触屏交互 | 可参考移动设备终端的产品功能 | 当前代码有 Kirigami、多个 KDE Frameworks 依赖；仍需手柄导航与输入转交，长期合并改动范围较大 | 作为实现参考 |

### QMLTermWidget 的核查结果

其官方 README 明确说明 **主分支已经迁移 Qt 6**，Qt 5 使用单独分支。官方示例使用 `import QMLTermWidget 2.0`，演示了 shell 启动、字体、搜索和剪贴板。不能再依据旧资料把它一概当作 Qt 5 专用组件。[S1][S2]

源码显示终端视图继承 `QQuickPaintedItem`，带有输入法事件与光标位置查询实现；会话对象提供工作目录、程序与参数、标题、前台进程信息，以及发送键和文字、搜索等入口。绘制使用 QPainter，这意味着 CM4 上的持续输出、滚动与帧耗时必须实测，不能凭「原生 Qt」推定轻量。[S3][S4]

当前公开 QML 接口有复制、粘贴及按键模拟，但选区主要由内部屏幕对象和鼠标路径操作。要做到真正的方向键选字，预计需要新增小范围原生接口：选区起止、移动选区光标、历史视口定位和选中文本读取。应让这些接口直接操作终端状态，避免模拟鼠标拖动。[S3][S4]

插件虽然面向 QML，但构建依赖 Qt Widgets，源码调用 QApplication 的接口。独立终端进程应使用 `QApplication` 引导，并在设备上确认；现有桌面仍是 `QGuiApplication`。插件与 PySide 必须使用兼容的系统 Qt 6.8 构建，避免混用 pip 自带 Qt 与系统插件。[S3][S4]

它内含自己的终端核心源码，并非薄薄链接到当前发行版 QTermWidget。应固定源码版本，保留来源和补丁清单，检查 QTermWidget/Konsole 的相关修复是否适用。当前 README 为 GPL-2.0-or-later；若采用，应在分发终端组件及应用时按相应许可提供所需源码、许可与修改说明。[S1][S3]

### QTermWidget 的核查结果

官方说明它是 Qt 6 的可嵌入 QWidget 组件，并提供程序、参数、工作目录、选区、滚动与剪贴板等接口。Debian 13 的 `libqtermwidget6-2` 页面列出 2.1.0-1 和 arm64 架构，说明有发行版库可用；这不代表系统自带 QTerminal 应用必须成为产品界面。[S5][S6]

适合的接入方式是独立 C++ / Qt Widgets 应用，或另外验证 Python 绑定方案。官方构建说明中的 Python 绑定使用 PyQt/SIP，不能直接当作当前 PySide6 的控件导入；Qt Widgets 也不能直接塞进 Qt Quick Item 树。[S5]

### libghostty-vt 的核查结果

当前官方 README 已将跨平台嵌入库列为可用能力，并明确区分 `libghostty-vt` 与 Ghostty GUI。C 头文件提供终端状态、滚动历史、重排、渲染状态、搜索、选择和输入编码等接口，同时明确 **1.0 前次版本可能破坏 API/ABI**。不能用旧结论说「完全不能嵌入」，也不能把它当作稳定 Qt 控件。[S7][S8]

官方 Ghostling 示例说明窗口与绘制由消费者提供，并使用 Raylib 演示；它自称最小示例，不是日常完整终端。对 uDeck 而言，仍要自己做好 Qt 渲染、字体排版与回退、输入法、PTY、标签和会话生命周期。构建还需匹配所选库版本要求的 Zig 版本。[S9][S10]

## 建议的产品形态

### 独立应用，共用操作习惯

建议程序名 `udeck-terminal`，独立窗口和进程，复用 uDeck 的颜色、间距、菜单和焦点组件。终端退出与桌面壳生命周期分开；返回主页和切换应用不会主动关闭终端及其 PTY。真实终端建议在设备 Linux 环境验证，开发机可以先预览界面。

建议首版界面：

- 默认全屏，以一个终端视图为主；顶部保留紧凑会话条，底部保留 ABXY / L/R 操作提示。
- 首屏直接进入本地 shell，支持新建、切换、重命名、关闭会话；L/R 在两端停止，不循环。
- X 打开上下文操作；从菜单进入历史浏览、复制模式、搜索、粘贴、字体缩放和会话管理。
- 关闭会话时检查前台任务并让用户明确选择；普通返回桌面动作保持会话运行。
- 终端字体优先验证等宽拉丁字符与中文回退，初始可试 18–20 像素字高附近的配置，再按真实观感和终端行列数调整。

首版先覆盖本地 shell 和基础会话管理。SSH 收藏、串口、多面板、自动恢复放在后续；这些不是完成自有终端所必需的前置功能。

### 两类交互状态

**输入状态**：实体键盘和方向键交给前台终端程序，保留 shell 历史、Vim、less、tmux 等原有键位。桌面方向导航只在菜单、设置和复制等界面状态中工作。

**菜单 / 历史 / 复制状态**：方向键控制界面或终端选区，A 确认，B 取消或返回；退出后恢复终端输入焦点。历史视口或复制光标应与正在运行的终端程序光标区分显示，输入状态也要有明确标识。

建议按键表如下，属于待原型验证的设计：

| 按键 | 终端输入状态 | 菜单 / 复制状态 |
| --- | --- | --- |
| 实体方向键 | 按终端当前模式编码并发给程序 | 移动焦点、浏览历史或移动选区光标 |
| A | 发送 Return，等同用户明确按下 Enter | 确认操作；复制模式按当前步骤设定或完成选区 |
| B | 发送 Escape，供 Vim 等程序使用 | 取消、返回上一层，不关闭会话 |
| X | 打开终端操作菜单 | 菜单内按上下文定义，不能穿透到后方 shell |
| Y | 打开 uDeck 快捷设置 | 优先遵守当前弹层规则，防止重复触发 |
| L / R | 上一 / 下一终端会话，到边界停止 | 弹层期间不切换；历史浏览可另提供翻页动作 |
| Ctrl+Alt+Esc | 返回 uDeck 主页，保持终端运行 | 同左，沿用独立会话已有全局键 |

ABXY 指独立物理手柄按钮，不能映射普通字母 a/b/x/y。实体 Esc、F1、F10、PageUp/PageDown 默认按终端程序要求处理，不能机械继承桌面的菜单快捷键；菜单打开后才优先处理其取消与导航。特别是 **B 不绑定 Ctrl+C，也不直接关闭终端**。需要发送 Ctrl+C 时使用真实组合键或明确的「发送按键」操作。

复制模式必须支持从历史缓冲中按键选择、复制、多字节字符边界与退出后焦点恢复。首版可优先做好按行选择，再扩展字符选择。粘贴先处理多行与控制字符预览，保留 bracketed paste；不能未经输入就主动追加回车执行。

### L/R 的接入是必要工作

当前 `PointerGuard` 独占鼠标接口且仅在桌面前台发出翻页动作，终端进程无法靠普通 Qt 鼠标事件获得 L/R。再抓一次同一个设备不能解决所有权问题。

建议首版保持一个鼠标接口持有者，在桌面现有会话 IPC 中增加窄范围的输入客户端注册与定向投递能力：

1. `PointerGuard` 持续丢弃移动、滚轮及普通点击，识别已确认设备上的 L/R 新按下沿。
2. 桌面前台时解释为上一页 / 下一页；已注册的 uDeck Terminal 前台时，定向发送上一会话 / 下一会话语义。
3. 路由依据真实活动窗口与注册连接校验，不能仅凭客户端自称「前台」或广播给所有订阅者。注册进程退出、失焦或连接断开时撤销目标。
4. ABXY 可先复用现有 `Gamepad` 类和校准数据，由当前前台应用持有，桌面失焦时释放；暂不为两个应用引入独立全局输入守护进程。
5. 失焦、恢复、热拔插及事件丢失时重置按住状态，要求新的按下沿；禁止一次按键在切换前后两个界面各触发一次。

这部分属于自有应用协议，需要新增实现与验收；当前 uDeck 尚不具备该路由。

## 接入现有桌面的范围

建议新增独立应用入口和独立 Debian 包；桌面包可推荐或依赖它，插件按选定源码版本构建。PySide 入口使用系统 Qt，界面通过 QML import 使用 C++ 插件，无须先为整个终端核心生成 PySide 绑定。

至少检查以下入口：

| 入口 | 建议处理 |
| --- | --- |
| 应用列表 | 新增 uDeck Terminal 的标准 `.desktop` 项与独立 app_id；按现有收藏机制配置 |
| Ctrl+Alt+T | 在 uDeck 独立 labwc 会话中改为 `udeck-terminal` |
| 文件页「在此打开终端」 | 结构化传递工作目录，不拼接 `cd …` 字符串 |
| `.desktop` 的 `Terminal=true` | 明确接管终端应用启动路径，验证 Gio 路径与后备路径都使用自有终端 |
| 运行中窗口 | 使用现有真实窗口协议发现、激活和返回，不使用进程列表冒充窗口 |
| 快捷设置 / 返回主页 | 复用会话 D-Bus 控制接口；恢复后不把按键重复发给 shell |

建议 CLI 契约为 `udeck-terminal --working-directory DIR -- PROGRAM ARG…`，也可提供兼容 `-e PROGRAM ARG…` 的入口。路径和命令以独立 argv 传递。需要终端程序时启动 PTY 子进程；不增加可通过网络执行任意命令的服务。首期作用范围可以限定 uDeck 会话；系统级默认终端另按用户选择配置。

终端 shell 和 PTY 的生命周期、关闭与子进程回收由终端应用负责。后续若需要应用重启后重新连接，使用显式的 tmux 集成；标签与工作目录恢复不等于正在运行的进程恢复。SSH 密钥、agent、known_hosts 沿用 OpenSSH，不把密码纳入终端配置。

## 建议验证顺序

先做最小技术原型，再确定是否长期采用该内核：

1. **组件可用性**：Qt 6.8 / Debian arm64 编译与插件加载；QApplication 入口；labwc 原生 Wayland 显示；shell、PTY 尺寸和退出行为。
2. **终端正确性**：bash/zsh、UTF-8 中文、fcitx5 预编辑与候选位置、中英混排、宽字符和组合字符、颜色、复制粘贴、resize、长历史输出。不要仅根据存在输入法函数就认定中文可用。
3. **真实目标程序**：Vim/Neovim、less、top/htop、tmux、SSH，以及实际要使用的 Codex CLI 等交互程序逐个运行；验证重绘、备用屏幕、Escape、功能键、Ctrl 组合键和输入法。普通 ANSI 输出成功不等于所有 TUI 成功。
4. **uDeck 交互**：ABXY 实按、L/R 跨应用路由、菜单不穿透、边界不循环、无鼠标历史与复制、失焦交接、返回主页、回到终端后会话仍在运行。
5. **资源与稳态**：同样字体、窗口大小、历史上限与输出负载下，对比系统终端；记录冷启动、RSS/PSS（区分应用与子进程）、空闲 CPU、持续输出、长时间滚动和输入延迟。功耗及续航另需设备测量。
6. **完整接入**：直接打开、文件夹打开、`Terminal=true`、Ctrl+Alt+T、窗口切换、子进程结束、会话关闭、安装升级与回退。

只有以上关键目标通过，才将其设为 uDeck 的默认终端入口。若 QMLTermWidget 在关键 TUI 或中文场景上需要大量改动，应尽早比较 QTermWidget 原型，避免在产品外壳上投入后才发现核心不合适。

## 调研证据与来源

本轮核查了当前仓库与下列官方文档、上游代码。部分 GitHub tree API 请求遇到限流；相关组件结论使用成功读取的 README、构建文件、头文件和实现核对。未用仓库活跃时间推定兼容性、正确性或功耗，也没有把 Ghostling 示例当作生产级终端。

- [S1：QMLTermWidget README，Qt 6 与许可说明](https://github.com/Swordfish90/qmltermwidget)
- [S2：QMLTermWidget 官方 QML 示例](https://github.com/Swordfish90/qmltermwidget/blob/master/test-app/test-app.qml)
- [S3：QMLTermWidget 构建文件](https://github.com/Swordfish90/qmltermwidget/blob/master/qmltermwidget.pro)、[视图头文件](https://github.com/Swordfish90/qmltermwidget/blob/master/lib/TerminalDisplay.h)、[会话接口](https://github.com/Swordfish90/qmltermwidget/blob/master/lib/ksession.h)
- [S4：QMLTermWidget 视图实现，输入法、绘制与选择逻辑](https://github.com/Swordfish90/qmltermwidget/blob/master/lib/TerminalDisplay.cpp)
- [S5：QTermWidget 官方说明与 API](https://github.com/lxqt/qtermwidget)
- [S6：Debian 13 libqtermwidget6-2 包与架构](https://packages.debian.org/trixie/libqtermwidget6-2)
- [S7：Ghostty 官方 README，libghostty 当前状态](https://github.com/ghostty-org/ghostty)
- [S8：libghostty-vt C API 与稳定性约定](https://github.com/ghostty-org/ghostty/blob/main/include/ghostty/vt.h)
- [S9：Ghostling 官方最小终端示例与限制](https://github.com/ghostty-org/ghostling)
- [S10：libghostty-vt 官方构建与打包说明](https://github.com/ghostty-org/ghostty/blob/main/PACKAGING-LIBGHOSTTY.md)
- [S11：xterm.js 官方说明](https://github.com/xtermjs/xterm.js)
- [S12：VTE 官方项目](https://gitlab.gnome.org/GNOME/vte)
- [S13：QMLKonsole 官方项目](https://invent.kde.org/plasma-mobile/qmlkonsole)、[当前构建依赖](https://github.com/KDE/qmlkonsole/blob/master/CMakeLists.txt)、[终端库构建](https://github.com/KDE/qmlkonsole/blob/master/lib/CMakeLists.txt)

成功下载的关键源码/文档快照、检索错误与 SHA-256 清单位于本地忽略提交的 `artifacts/terminal-research-2026-11-06/`，用于追溯本次判断。链接的默认分支将来可能变化，正式采用时需重新选择并固定版本。
