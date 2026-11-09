# uDeck 使用与维护

## 运行边界

uDeck 是原生 PySide6 / Qt Quick 桌面壳，完整套件的浏览器与 EPUB 阅读使用 QtWebEngine。真实后端仅在 Linux 运行；macOS 和开发机使用 `--mock --windowed`。第三方应用兼容层需要独立 uDeck 会话，原桌面中运行壳不会启用。

首次默认英文。在 `Settings → Language` 或 `Y → Language` 选择 `English` / `简体中文`，立即切换并保存。已安装的 Terminal 0.1.4 同步界面语言，保留会话和输出。详见 [中英文界面记录](i18n-2026-11-06.md)。

目标环境为 CM4、约 4 GiB 内存、Debian 13、Qt 6.8、labwc 0.9 系列和横屏 1280×720。不会替换官方镜像、显示驱动、内核或窗口合成器。

## 开发预览

```sh
python3.13 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/udeck --mock --windowed
```

预览的应用启动、文件操作、无线网络、蓝牙和电源动作全部是模拟；配置保存在临时目录，退出即清理。预览可以检查焦点与视觉，但不能证明硬件功能。

```sh
QT_QPA_PLATFORM=offscreen PYTHONPATH=src .venv/bin/python -m udeck.main \
  --mock --windowed --smoke-test --page files \
  --screenshot artifacts/preview-files.png --quit-after 2
.venv/bin/python -m pytest -q
.venv/bin/ruff check src tests tools
```

Qt 6.8 的 Python 开发环境使用 3.11–3.13，不使用系统默认的 Python 3.15 来安装该版本 PySide6。界面英文使用 Saira Semi Condensed，中文使用 LXGW 文楷屏幕版；字体随包提供，缺字时回退到系统字体。

## Debian 软件包

完整发行包名为 `udeck`，严格拉齐 `udeck-shell`、`udeck-terminal`、`udeck-apps`。安装目标、完整依赖、GitHub Release 下载及旧 XFCE 镜像迁移见 [Debian 发行与安装](debian-distribution.md)。在 Debian 13 arm64 源码目录构建：

```sh
sudo apt-get build-dep .
python3 tools/build-release --output dist/release
sh dist/release/install.sh
```

依赖由 Debian 提供，包括 PySide6 Qt 6.8、Qt Quick Controls、dbus-next、evdev、Gio、NetworkManager、BlueZ、PipeWire/WirePlumber、wlr-randr、swayidle/swaylock、wlopm、fcitx5 和 lxpolkit。构建不打包 358 MiB 的硬件资料、虚拟环境或测试缓存。

主要安装路径：

| 路径 | 用途 |
| --- | --- |
| `/usr/bin/udeck` | 桌面壳 |
| `/usr/bin/udeckctl` | 本机会话控制和诊断 |
| `/usr/bin/udeck-session` | labwc 独立会话启动器 |
| `/usr/share/wayland-sessions/udeck.desktop` | 登录界面中的可选会话 |
| `/usr/share/udeck/labwc/` | 隔离的 labwc 配置与空 autostart |
| `/usr/libexec/udeck/session` | 输入法、认证代理、熄屏和桌面壳监督进程 |
| `/usr/lib/python3/dist-packages/udeck/` | Python/QML 程序 |

安装脚本没有修改默认会话、重启 LightDM、刷写固件或变更设备权限的维护脚本。

## 先在原桌面中运行

```sh
udeck --windowed
```

这是真实后端：文件、音量、亮度和设备操作都会生效。仅检查系统状态时可使用：

```sh
udeck --windowed --no-input --quit-after 30
udeckctl doctor --json
```

不要把 `--windowed` 当作安全模拟模式；只有 `--mock` 才隔离实际操作。真实壳同一用户会话只允许一个实例。

真实全屏模式同时接管当前用户可访问的独立鼠标接口，持续到壳退出；第三方窗口前台时仍屏蔽鼠标。窗口化和 mock 预览仅在 uDeck 窗口内使用按键逻辑，不接管开发机鼠标。`--no-input` 供诊断使用，禁用手柄和鼠标设备接管。

SSH 调试必须连接实际图形会话，使用正确的 `XDG_RUNTIME_DIR`、`WAYLAND_DISPLAY` 和 `DBUS_SESSION_BUS_ADDRESS`。Xwayland 检查还需要图形会话的 `DISPLAY` / 必要时 `XAUTHORITY`，不能用缺失 DISPLAY 的 SSH 环境判定 Xwayland 不可用。不要把 SSH 密码写入命令文件、环境持久配置或仓库。

## 键盘与手柄操作

| 物理操作 | 键盘等价 | 语义 |
| --- | --- | --- |
| 上下左右 | 方向键 | 按可见行列移动，不越界循环 |
| A | Enter | 确认或打开 |
| B | Esc | 返回或关闭当前弹层 |
| X | F10 | 当前项目的上下文菜单 |
| Y | F1 | 快捷设置 |
| L / R | PageUp / PageDown | 上一页 / 下一页；到边界停止，弹层打开时无效 |
| — | Ctrl+F | 搜索应用 |

顶部只有主页、应用、运行中、文件四个标签。首页固定展示终端、音乐、视频、阅读器、模拟器、设置六个大图标，左右选择且不首尾循环，1280×720 下一屏可见，小窗口随焦点横向滚动；收藏与最近使用不改变顺序。设置作为首页的子页面，B 返回首页并恢复设置图标焦点；设置页内 L/R 不切页，Y 快捷设置仍可使用。未安装的原生应用保留禁用入口。安装完整的 udeck 包时自动将 uDeck Terminal 设为系统默认终端，原桌面与默认登录方式保持现状。

首页任意图标、其他页面内容第一行向上进入顶部导航，再按下回到内容焦点。关闭弹层恢复原页和选中位置；目录返回以项目路径恢复选中项，而不只恢复旧行号。应用页网格固定五列；列表、菜单和弹层随焦点滚动。

标有 L/R 的实体键在固件中仍发送鼠标左/右键事件，uDeck 将它们解释为切页键，与轨迹球位置无关。轨迹球移动、鼠标点击选中、双击打开、拖动和滚轮操作全部禁用；文件和设置均由方向键选中、A 打开、B 返回、X 菜单、Y 快捷设置。关闭弹层与切回页面恢复原焦点。

实体键盘正常输入文字，文本编辑时方向键用于移动光标，中文输入沿用 Qt/fcitx5。A/B/X/Y **不是**键盘字母快捷键。第三方应用中的物理鼠标仍被屏蔽；独立会话提供以下兼容操作。

| 按键 | 默认按键模式 | 手动指针模式 |
| --- | --- | --- |
| 方向键 | 应用原生方向操作 | 移动虚拟指针，长按加速 |
| A | Enter | 左键，按住并移动可拖动，连续短按可双击 |
| B | Esc | Esc |
| X | Shift+F10 | 右键 |
| Y | 应用控制菜单 | 应用控制菜单 |
| L / R | Shift+Tab / Tab | 向上 / 向下滚动 |

Y 菜单默认选中「返回应用」，还提供模式切换、常用操作、返回桌面、快捷设置和请求关闭。B 逐层返回；退出菜单恢复原窗口，窗口已关闭则回到运行中。浏览器的地址栏、后退、刷新，编辑器的打开、保存，以及文件管理器的上级目录等由常用操作提供，B 始终保留 Esc 语义。

按 app_id / WM_CLASS 保存选择；子对话框继承父应用。未知应用默认按键模式。RetroArch 默认原生输入，释放独立手柄，使用 `Ctrl+Alt+Esc` 返回桌面；uDeck Terminal 使用自己的原生交互。按键模式依赖应用自身的焦点系统，不保证方向键空间导航；处理文本和中文候选时使用按键模式。

指针启用要等待独立会话的方向键拦截确认；失败留在菜单并报告原因。方向键接口断开会停止指针、恢复普通方向键。窗口切换或菜单交接时按住的按钮须松开后再按，避免误点击。虚拟指针只由手柄驱动，物理轨迹球和外接鼠标继续禁用。

### 首次实按校准

固件 fingerprint 为 `1eaf:0024:20230713` 且公布相应按钮能力时，首次运行自动采用已实按确认的 A=289、B=290、X=288、Y=291 映射，显示「ABXY 已映射」。这不代表已完成整机验收。保存过的自定义映射优先；不同设备或未知固件仍需校准。

1. 用方向键和 A，或键盘方向键与 Enter 进入「设置 → 按键与控制器」。
2. 依屏幕顺序实按并松开：上、下、左、右、A、B、X、Y。
3. 方向键可通过正常 Qt 键盘事件完成校准；ABXY 只采集已确认 VID/PID 的独立手柄接口。校准记录 `keyboardDirections`，不独占键盘或 Consumer Control；鼠标由独立的会话屏蔽逻辑接管。
4. 如果 ABXY 只产生 j/k/u/i 等字母，切换设备原有手柄模式后重新校准。本程序不会刷固件。
5. 校准后继续实测长按重复、中文输入、L/R 切页、轨迹球无效和第三方应用键盘操作。映射文件存在不等于这些验收已通过。

本次十个物理按键的真实事件与旧版修复说明见 [0.1.2 输入修复记录](input-2026-11-06.md)；当前行为见 [0.1.3 手柄交互记录](controller-mode-2026-11-06.md)。Debian 上运行完整 QML 输入回归还需安装开发测试包 `python3-pyside6.qttest`；正常桌面运行不依赖它。

独立会话由实际前台窗口决定手柄所有权，兼容模式接管，原生模式释放；退出、锁屏或设备断开时释放注入状态。不通过全局 ABXY 返回桌面。在独立 uDeck 会话内：`Ctrl+Alt+Esc` 返回主页、`Ctrl+Alt+Tab` 切换窗口、`Ctrl+Alt+S` 快捷设置。窗口化运行不会向原桌面写入这些全局快捷键。

鼠标的屏蔽生命周期与手柄不同：打开第三方应用后仍持有鼠标接口，L/R 按当前应用模式工作。新插入的独立鼠标会重新扫描并接管；无法访问或混有普通键盘键位的接口不会被强占，原因显示在 `udeckctl doctor --json` 的 `runningShell.input.pointer.errors` 中。独立会话还通过自己的 labwc 配置禁用内置 `ClockworkPI uConsole Mouse` 的指针事件，不影响原桌面配置。

## 功能使用与安全保护

- 应用：X 加入/取消收藏、搜索、分类。读取 XDG applications，尊重用户覆盖、Hidden/NoDisplay、OnlyShowIn/NotShowIn 和 TryExec，按界面语言读取应用提供的本地化名称和说明；优先使用 Gio 启动及处理终端应用。
- 窗口：只列举真实 foreign-toplevel 窗口；A 激活，X 请求关闭。请求关闭允许应用显示保存确认，并非杀死进程。
- 文件：从主目录开始，X 新建、重命名、复制/剪切、粘贴或移入回收站。覆盖默认不发生，文件夹不会合并/覆盖。没有“永久删除”后备路径。
- 移动：同文件系统使用原子 rename；跨文件系统先完整复制并检查源是否变化，再将源移入回收站。回收站不支持或源改变时保留源，明确报告“目标已复制但源仍保留”，不会调用递归永久删除源目录。
- 回收站限制：某些挂载点不支持 Gio 回收，例如此设备的 `/tmp` tmpfs。失败时会显示系统原因并保留源文件；这不等于主目录的回收站不可用，不会改为永久删除。
- Wi-Fi：先选网卡，在网络上按 A 打开加入、重新加入、断开、自动连接、修改密码、遗忘和详情菜单；同名多配置先选具体配置。遗忘默认取消，确认后先断开再删除所选配置；修改密码只保存，X 显示／隐藏本次输入，由用户选择何时重新加入。保存列表在 Wi-Fi 关闭或不在范围内时仍可管理。内置与 USB 网卡独立显示，B 逐层返回并保留焦点；另一卡占用的配置禁止修改，从扫描列表可新建独立配置。路由继续由系统管理。详见 [多网卡记录](multi-wifi-2026-11-06.md)、[管理交付记录](wifi-management-2026-11-07.md)和[设计规范](../design/wifi-management.md)。
- 蓝牙：配对与连接是不同状态；PIN、配对码和确认请求在弹层中处理。配对后尝试连接；失败保留“已配对/未连接”状态，不宣称功能已经可用。
- 音量：A 打开音量菜单，进入滑杆或切换静音；输出设备菜单选择系统默认输出。
- 音频输出与麦克风：设置或 Y 快捷设置中选择输出和麦克风输入，蓝牙设备有明确标记。麦克风支持输入音量和静音，扬声器回录 Monitor 不会作为麦克风显示。蓝牙音频模式可在播放与通话配置之间切换；通话模式可能降低播放音质，切换前需确认。设备断开后自动刷新，各操作始终绑定所选设备。系统默认设备不覆盖应用自身显式指定的设备。
- 电池：查看电量、充电／放电／满电状态、电池电压、电流和电池侧功率估算，每 5 秒刷新。缺失传感器读数显示“不可用”，与实测零功率区分；功率不代表充电器输入总功率。音频和电池的测试、截图及实机验收边界见 [交付记录](power-audio-2026-11-07.md)。
- 亮度：左右调整后 A 应用、B 取消。最低为 5%，避免滑杆意外熄屏。熄屏另设入口，沿用 wlopm/swayidle；按方向键或键盘恢复，不是系统休眠。
- 电源：Y → 电源与会话，或设置列表底部。注销、重启和关机默认选中“取消”。锁屏和熄屏也应先在现场验证，避免唯一 SSH 通路上失联。

## 独立会话与回退

**先保存所有应用工作，再在现场操作。** 在登录界面的会话选择中进入 uDeck。仅安装软件包不会修改现有自动登录策略；需要开机直接进入 uDeck 时，使用下方显式配置工具。勿通过唯一 SSH 链路远程试切换会话。

希望开机直接进入 uDeck 时，可在安装完成后的源码目录中显式执行：

```sh
sudo python3 tools/configure-login.py --user "$(id -un)"
sudo lightdm --show-config
```

这是单独授权的管理操作，不是软件包安装步骤：工具在 `/var/backups/udeck/` 中备份原配置，保留其他配置与注释，原子写入 `[Seat:*]` 的 `user-session=udeck`、`autologin-session=udeck`、`autologin-user` 和零秒等待。不自动注销、重启或修改原 labwc 用户配置；有特定 seat 覆盖时拒绝静默写入。请保存工具打印的备份路径，原配置可由管理员复制回 `/etc/lightdm/lightdm.conf`。自动登录允许接触设备的人直接进入该用户桌面，是否开启应明确选择。

`udeck` 的真实模式使用无边框全屏，返回主页、窗口切换器或快捷设置时保持全屏；`udeck --windowed` 与 mock 仍是普通预览窗口。开机默认会话设置与当前显示模式是两个独立步骤：设置 LightDM 不会自动替换当前已登录的桌面。设备上的本次设置及确切备份路径见 [开机配置记录](boot-2026-11-06.md)。

独立会话使用自己的 labwc 配置，不读取原用户面板/桌面管理器的 autostart；按需启动 fcitx5、lxpolkit，保留 DSI-1 的 270° 横屏方向。规则请求普通主窗口默认最大化；应用自己的全屏和模态对话框行为仍由应用与 labwc 处理。当前原桌面会话存在合成器返回零尺寸的最大化异常，独立会话实际几何、全屏和模态行为仍需现场验收，不能视为已通过。

未开启自动登录时，退出 uDeck 后可在登录界面选择原「Raspberry Pi Desktop on Wayland」。已经开启 uDeck 自动登录时，先恢复工具打印的 LightDM 备份，再保存工作并在现场注销或重启；具体命令见 [开机配置记录](boot-2026-11-06.md)。卸载前也必须恢复登录配置，避免默认会话指向已移除的程序：

```sh
sudo apt-get remove udeck udeck-shell udeck-terminal udeck-apps
```

不要附带执行 `autoremove`、删除原桌面配置或删除用户数据。`~/.config/udeck/settings.json` 包含收藏、偏好、焦点和校准结果；卸载后保留，是否清理由用户另行决定。

## 诊断与复现

```sh
udeckctl home
udeckctl switcher
udeckctl quick-settings
udeckctl app-menu
udeckctl input-mode keyboard
udeckctl input-mode pointer
udeckctl input-mode native
udeckctl doctor --json
PYTHONPATH=src python3 tools/verify-windows.py
PYTHONPATH=src python3 tools/measure-shell.py --seconds 60 --output artifacts/performance.json
```

`doctor` 是只读检查；`verify-windows.py` 默认仅创建、激活和请求关闭自己创建的 Wayland/Xwayland 测试窗口，额外传入 `--check-maximized` 才测试 foreign 协议最大化及实际渲染尺寸；`measure-shell.py` 启动无手柄输入的真实窗口化壳并自动退出。后两项需要正确的图形会话环境，不能代替物理按键或独立登录验收。

验证安装版而非源码时去掉 `PYTHONPATH=src`，并确认没有继承其他 `PYTHONPATH`。性能输出区分内部首帧时间和包含 Python 导入的 `launchToReadySeconds`，启动目标使用后者；RSS/CPU 为壳进程的空闲采样，不是整机或完整登录会话指标。

具体已测事实、局限和未完成的现场项目见 [实机验收记录](acceptance-2026-11-06.md)。

0.1.4 的 `runningShell.input.compatibility` 显示前台应用、当前模式、虚拟输入、方向键接口、拦截配置及错误；原桌面显示明确的不可用原因。完整应用控制的部署和验收边界见 [应用兼容层记录](application-control-2026-11-06.md)。
