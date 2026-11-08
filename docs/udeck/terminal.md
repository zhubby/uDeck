# uDeck Terminal v1 使用与维护

uDeck Terminal 是独立的 QApplication / Qt Quick 应用，每个标签拥有自己的原生终端缓冲和 PTY。返回主页、切换应用或最小化不会结束任务；关闭标签或窗口时先确认，默认选择取消。应用退出后不恢复运行任务，首版不使用 tmux 托管。

## 构建与安装

目标为 Debian 13 arm64、系统 PySide6 / Qt 6.8、labwc。先使用设备系统的 Qt 开发包编译私有插件：

```sh
sudo apt-get install --no-install-recommends build-essential qt6-base-dev qt6-declarative-dev libutempter-dev python3-pytest python3-pyside6.qttest
python3 tools/build-terminal-plugin
QT_QPA_PLATFORM=offscreen UDECK_REQUIRE_NATIVE=1 PYTHONPATH=src python3 -m pytest -q
sh tools/build-deb
python3 tools/build-terminal-deb
sudo apt-get install ./dist/udeck_0.1.6_arm64.deb ./dist/udeck-terminal_0.1.1_arm64.deb
udeck-terminal
```

插件安装在 `/usr/lib/udeck-terminal/qml/QMLTermWidget`，不占用系统公共 QML 模块目录。`udeck-terminal` 0.1.1 包依赖 `udeck >= 0.1.6` 以复用输入基础代码和中英文词条，运行不依赖 uDeck 桌面进程。基础包不拥有 `udeck/terminal`，避免重复文件归属。源码安装的 Python wheel 包含 Python/QML 文件与翻译词条，仍需要单独构建原生插件；wheel 不携带任意平台的二进制。

语言跟随 uDeck 的 `Settings → Language` 设置，首次默认英文。已打开的 0.1.1 终端会在一秒内同步切换菜单和提示，不重建 PTY，也不翻译命令、输出、窗口标题或粘贴内容。旧版本中正在运行的终端保留原进程，关闭后再次启动才加载新版本。

安全界面预览不启动 shell，也不写用户配置：

```sh
PYTHONPATH=src python3 -m udeck.terminal.main --mock --windowed
QT_QPA_PLATFORM=offscreen PYTHONPATH=src python3 -m udeck.terminal.main --mock --windowed --smoke-test --screenshot artifacts/terminal.png
```

## 启动契约

```sh
udeck-terminal
udeck-terminal --new-window
udeck-terminal --working-directory '/home/zhubby/中文 目录'
udeck-terminal -T '维护任务' -e ssh host.example
udeck-terminal -- python3 script.py '中文 空格' 'literal $HOME'
```

同一图形会话只有一个终端主进程。普通调用激活最近窗口；显式目录、标题、程序或 `--new-window` 创建新窗口。未指定目录时使用调用方当前目录，未指定程序时使用账户数据库中的 shell。`-e` 与 `--` 后的参数逐项执行，不经过 shell、不展开变量或重新拆分引号。需要 shell 语法时明确指定 `sh -c`。

窗口请求通过会话 D-Bus `io.github.zhubby.uDeck.Terminal.Session_<display hash>` 发送，接口为 `io.github.zhubby.uDeck.Terminal.Control`，路径为 `/io/github/zhubby/uDeck/Terminal`。`Open(s)->s` 的空字符串表示接受请求，非空字符串为错误；请求包含 cwd、argv、title、environment、new_window。完整环境只在内存中传递，`Diagnose` 和 `--doctor` 仅返回数量、输入状态及性能信息。

## 按键与交互

| 按键 | 输入状态 | 历史或菜单 |
| --- | --- | --- |
| 方向键 | shell / TUI | 移动焦点、视口或选区 |
| 实体 A / B | Return / Escape | 确认 / 返回 |
| 实体 X | 操作菜单 | 不穿透 shell |
| 实体 Y | uDeck 快捷设置；原桌面为终端设置 | 由当前弹层处理 |
| L / R | 前一 / 后一标签，边界停止 | 不切换标签 |
| Ctrl+Shift+T / W | 新建 / 请求关闭标签 | 关闭需要确认 |
| Ctrl+Shift+C / V | 复制 / 粘贴 | 危险粘贴先预览 |
| Ctrl+Shift+F / M | 搜索 / 菜单 | Esc 返回 |

普通字母、实体 Esc、F1、F10、PageUp/PageDown 保留给终端程序；不会将普通字母 A/B/X/Y 转换成掌机动作。鼠标点击与滚轮在终端内部被消费。SSH 使用系统 OpenSSH；SSH 收藏、串口与分屏不在首版范围。

复制：X → 历史与复制 → 方向键定位 → A 设置起点 → 方向键扩选 → A 复制并回到输入。B 取消。选区直接操作原生缓冲，宽字符的续格不会成为端点。搜索区分大小写、按普通文本匹配；Enter/下方向查找下一处，上方向查找上一处，支持回绕。

含换行、C0/C1 或 DEL 的粘贴会冻结当前剪贴板文本，预览并确认后发送。保留 bracketed paste；不会额外追加回车。终端正文跟随 uDeck 界面语言：中文使用霞鹜文楷等宽 LXGW WenKai Mono，英文使用 JetBrains Mono Regular / Bold；字体和 SIL OFL 1.1 许可证均随包提供，无需预装。语言切换实时更新已有标签的字体，不重建终端会话。会话栏、菜单和按键提示沿用 uDeck 界面字体。字号默认 20 px，设置中按 2 px 在 14–28 px 间调整；历史缓冲为 10,000 行。

### 主题和 Nerd 图标

窗口、菜单和终端正文统一跟随系统 Classic / Dark，沿用约一秒的设置同步周期。Classic 使用暖炭灰背景 `#151719`、正文 `#F1EEE7`；Dark 使用冷黑背景 `#0B0E12`、正文 `#F5F2EB`。强调色均为 `#EDB866`。Classic 保留既有 ANSI 16 色，Dark 使用单独的高对比配色；光标和选区保留原生行为，程序自行指定的真彩色不被改写。终端设置仅显示当前主题，不再提供独立深浅配色开关。

已打开的所有窗口和标签同步换色，不重建终端组件或 shell，不清空历史、选区或当前标签。语言切换也不重启会话；字号仍为 14–28 px、默认 20 px。

随包提供原版 Nerd Fonts **v3.5.1 Symbols Nerd Font Mono**，以“当前界面语言文字字体 → Nerd 图标字体 → 另一套文字字体”的明确顺序补齐缺失字符，不需要联网或系统预装。它不替换 LXGW WenKai Mono / JetBrains Mono，也不自动安装或修改 Starship、Oh My Zsh 等 shell 配置。原生插件按完整 Unicode 码点测宽，私用区图标独立绘制并裁剪到当前格内，超过单元格宽度时横向适配，避免负边距或过宽字形覆盖相邻文字；支持 Powerline、文件夹、终端和补充私用区图标，不改动原字体文件。

Nerd 图标集合并非单一 OFL 许可：字体来源、版本、文件哈希记录在 `terminal/fonts/manifest.json`；上游归属表和各图标集原始许可证随 wheel 和 Debian 包提供。wheel 同时携带 `share/udeck-terminal/color-schemes` 中的两套配色模板，但原生插件仍需按目标 Qt 6.8 另行构建。构建插件时同时安装 `udeck`、`udeck-dark` 两份配色；Debian 打包会拒绝缺少或过期配色的插件，需要先重新执行 `tools/build-terminal-plugin`。

`~/.config/udeck/terminal.json` 的版本 2 仅保存 `fontSize`，权限为 0600。读取旧配置时保留字号、忽略原 `colorScheme`，下次保存时迁移；系统主题仍从 `settings.json` 读取。终端不将输出、输入和密码写入偏好文件。shell、SSH、Codex 等子程序仍可能按自身设置写历史或日志。

## 输入所有权

uDeck 的 PointerGuard 持续持有会话级鼠标接口。桌面依据 foreign-toplevel 协议报告的真实活动 app ID 和窗口 ID 建立路由，每次活动目标改变增加代数，只转发内置 L/R 边沿。终端接收后再次确认自己的 Qt 窗口实际处于前台且代数有效；弹层期间不切标签。

原桌面下，终端只在前台独占已确认指纹的 `ClockworkPI uConsole Mouse` 接口，失焦立即释放；外置鼠标不变成 L/R。ABXY 使用既有 Gamepad 和校准配置，失焦、热拔插或事件丢失后清空状态，重新获取前等待所有键松开。

返回主页：uDeck 运行时通过它的 `Home` 接口返回；原桌面下最小化终端。两种方式都保留 PTY。升级基础包后需要重启桌面进程才能启用新的 L/R broker；只启动终端即可在原桌面独立使用。

## 默认终端与恢复

安装包不会改变默认终端。`update-alternatives --install` 本身可能切换 auto 选择，因此优先级 **20** 的注册和 man page slave 延后到验收通过后的 apply 操作。

先完成安装版验收。只保留一个窗口、一个本地 shell，空闲后采样：

```sh
PYTHONPATH=src python3 tools/terminal-acceptance --output artifacts/cm4-terminal-acceptance.json
udeck-terminal --doctor
```

采样 60 秒，记录首次呈现、主进程 RSS 最大值、单逻辑核心口径 CPU，以及直接子进程的独立资源。启动 ≤5 秒、RSS ≤250 MiB、空闲 CPU ≤3%。报告的手工检查默认 pending；只能在真实观察通过后填写 passed，不能用自动按键、离屏预览或进程存在替代实按与输入法验收。

采样会比对终端启动时缓存的构建 ID 与当前安装包，拒绝源码版和升级前仍在运行的进程。启动耗时基于 Linux 进程启动时刻与首帧记录，包含 Python/Qt 导入时间；另列 main 入口至首帧的原始诊断值。升级后先关闭旧终端并重新启动，再生成验收记录。

```sh
udeck-terminal-default status --user zhubby
sudo udeck-terminal-default apply --user zhubby --acceptance artifacts/cm4-terminal-acceptance.json
sudo udeck-terminal-default restore --user zhubby --backup /var/lib/udeck-terminal/defaults/<id>.json
```

工具备份 alternative 的选择、auto/manual 状态、是否已有注册，以及系统和目标用户的 XDG 列表与受支持桌面绑定。它更新已有 `*-xdg-terminals.list`，保留旧候选项顺序；迁移 labwc/Openbox 的命令和 libfm/PCManFM/LXSession 的明确终端命令。符号链接或未知终端参数会在任何修改前阻止 apply，需要手动处理。备份为 root 私有；恢复会拒绝覆盖 apply 后另行修改的文件。

配置写入后逐个验证真实启动结果：

1. `x-terminal-emulator`、`xdg-terminal-exec`。
2. uDeck Ctrl+Alt+T、文件页“在此打开终端”、应用列表。
3. `Terminal=true` 应用：Gio 主路径和缺少 GI 的后备路径。
4. 原桌面的终端快捷键及文件管理器动作，包括含中文和空格的目录。
5. 恢复原默认并重新验证，再根据验收结果重新 apply。

未通过关键检查时保留原默认。`--config-home` 可指定目标用户实际使用的非标准 XDG 配置目录。其他桌面自身的设置后端或自定义脚本需根据 status 清单和实机入口另行核查。

## 原生组件维护

上游固定为 Swordfish90/qmltermwidget `8913504fa2ebd220ebe7c680c32954e1b3c035c5`。`vendor/qmltermwidget/UPSTREAM.json` 记录来源与下载校验；源码已包含 `patches/series` 中的补丁，不要再次叠加。终端新增代码和补丁按 GPL-2.0-or-later；原组件各文件的 GPL、LGPL 与 BSD 通知完整保留。

更新上游时重新生成补丁、编译私有插件、运行真实 PTY/缓冲测试，并重新完成 CM4 验收。不能将不同 Qt 次版本构建的插件复制到设备。完整源码随交付归档，Debian 包中保留上游许可、固定提交和补丁清单。

原生测试覆盖精确 argv/cwd/环境、宽字符和组合字符选区、普通文本搜索、bracketed paste、resize 与关闭进程组，并覆盖双主题 ANSI 16 色、真彩色保留、中英文 Nerd 图标、14 / 20 / 28 px 字号、Unicode 复制和多窗口会话/焦点保持。`tests/terminal_appearance_probe.py` 生成不启动 shell 的中英文 Mock 截图；`tests/native_terminal_appearance_probe.py` 必须加载原生插件并使用真实本地 PTY，不能用前者替代后者。离屏/容器结果仍不等于掌机物理显示、真人实按、Wayland/Xwayland 或实际输入法验收。

安装后的自动验收脚本从系统包导入应用，避免把源码运行误记为安装版通过。在设备图形会话的环境中分别执行：

```sh
QT_QPA_PLATFORM=wayland python3 tests/terminal_device_probe.py --output artifacts/installed-wayland-probe.json
QT_QPA_PLATFORM=xcb python3 tests/terminal_device_probe.py --output artifacts/installed-xwayland-probe.json
python3 tests/terminal_ipc_probe.py --output artifacts/installed-ipc-probe.json
python3 tests/terminal_default_device_probe.py --output artifacts/installed-default-rehearsal.json
```

IPC 和默认配置演练前关闭已有终端窗口。默认配置演练使用临时 alternatives 数据库、链接和 XDG 配置，检查真实 alternative / xdg-terminal-exec / Gio 启动以及精确恢复；不会替代正式系统入口验收。TUI 脚本使用 Qt 合成键盘事件，包含 Vim 保存、less 搜索、tmux 分离和 Codex 启动/按键退出。若 Codex 进入目录信任向导，脚本选择 No 退出，记录此边界，不修改用户信任设置，也不声称验证了模型请求或完整编辑器。
