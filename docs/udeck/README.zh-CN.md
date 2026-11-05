# uDeck 使用与维护

## 运行边界

uDeck 0.1.0 是原生 PySide6 / Qt Quick 桌面壳，不包含 Electron、Chromium 或 HTTP 服务。真实后端仅在 Linux 运行；macOS 和开发机使用 `--mock --windowed`。

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

Qt 6.8 的 Python 开发环境使用 3.11–3.13，不使用系统默认的 Python 3.15 来安装该版本 PySide6。中文字体优先 Noto Sans CJK SC，macOS 预览回退 PingFang SC。

## Debian 软件包

构建脚本使用当前 Debian 架构，不做交叉编译。在 arm64 设备的源码目录执行：

```sh
sh tools/build-deb
dpkg-deb --info dist/udeck_0.1.0_arm64.deb
sudo apt-get install ./dist/udeck_0.1.0_arm64.deb
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

SSH 调试必须连接实际图形会话，使用正确的 `XDG_RUNTIME_DIR`、`WAYLAND_DISPLAY` 和 `DBUS_SESSION_BUS_ADDRESS`。Xwayland 检查还需要图形会话的 `DISPLAY` / 必要时 `XAUTHORITY`，不能用缺失 DISPLAY 的 SSH 环境判定 Xwayland 不可用。不要把 SSH 密码写入命令文件、环境持久配置或仓库。

## 键盘、按键与轨迹球

| 物理操作 | 键盘等价 | 语义 |
| --- | --- | --- |
| 上下左右 | 方向键 | 按可见行列移动，不越界循环 |
| A | Enter | 确认或打开 |
| B | Esc | 返回或关闭当前弹层 |
| X | F10 | 当前项目的上下文菜单 |
| Y | F1 | 快捷设置 |
| — | Ctrl+F | 搜索应用 |

内容第一行向上进入顶部导航，再按下回到内容焦点。关闭弹层恢复原页和选中位置；目录返回以项目路径恢复选中项，而不只恢复旧行号。网格固定五列；列表、菜单和弹层随焦点滚动。

轨迹球单击选择、双击打开，弹层按钮可单击执行。实体键盘正常输入文字，文本编辑时方向键用于移动光标，中文输入沿用 Qt/fcitx5。A/B/X/Y **不是**键盘字母快捷键。

### 首次实按校准

1. 用键盘或轨迹球进入「设置 → 按键与控制器」。
2. 依屏幕顺序实按并松开：上、下、左、右、A、B、X、Y。
3. 只采集已确认 VID/PID 的独立手柄接口；键盘、鼠标和 Consumer Control 接口不被独占。
4. 如果 ABXY 只产生 j/k/u/i 等字母，切换设备原有手柄模式后重新校准。本程序不会刷固件。
5. 校准后继续实测长按重复、中文输入、轨迹球和第三方应用。映射文件存在不等于这些验收已通过。

壳失焦或退出即释放手柄；不通过全局 ABXY 返回桌面。在独立 uDeck 会话内：`Ctrl+Alt+Esc` 返回主页、`Ctrl+Alt+Tab` 切换窗口、`Ctrl+Alt+S` 快捷设置。窗口化运行不会向原桌面写入这些全局快捷键。

## 功能使用与安全保护

- 应用：X 加入/取消收藏、搜索、分类。读取 XDG applications，尊重用户覆盖、Hidden/NoDisplay、OnlyShowIn/NotShowIn 和 TryExec，按系统区域设置读取本地化名称；优先使用 Gio 启动及处理终端应用。
- 窗口：只列举真实 foreign-toplevel 窗口；A 激活，X 请求关闭。请求关闭允许应用显示保存确认，并非杀死进程。
- 文件：从主目录开始，X 新建、重命名、复制/剪切、粘贴或移入回收站。覆盖默认不发生，文件夹不会合并/覆盖。没有“永久删除”后备路径。
- 移动：同文件系统使用原子 rename；跨文件系统先完整复制并检查源是否变化，再将源移入回收站。回收站不支持或源改变时保留源，明确报告“目标已复制但源仍保留”，不会调用递归永久删除源目录。
- 回收站限制：某些挂载点不支持 Gio 回收，例如此设备的 `/tmp` tmpfs。失败时会显示系统原因并保留源文件；这不等于主目录的回收站不可用，不会改为永久删除。
- Wi-Fi：可开关、主动扫描、选择已保存个人网络或输入密码连接；切网有明确二次确认。企业认证、VPN 和热点不在首版。
- 蓝牙：配对与连接是不同状态；PIN、配对码和确认请求在弹层中处理。配对后尝试连接；失败保留“已配对/未连接”状态，不宣称功能已经可用。
- 音量：A 打开音量菜单，进入滑杆或切换静音；输出设备菜单选择系统默认输出。
- 亮度：左右调整后 A 应用、B 取消。最低为 5%，避免滑杆意外熄屏。熄屏另设入口，沿用 wlopm/swayidle；不是系统休眠。
- 电源：Y → 电源与会话，或设置列表底部。注销、重启和关机默认选中“取消”。锁屏和熄屏也应先在现场验证，避免唯一 SSH 通路上失联。

## 独立会话与回退

**先保存所有应用工作，再在现场操作。** 在登录界面的会话选择中进入 uDeck。现有自动登录策略不会被程序修改；若当前设备直接自动登录，请在现场用系统原有登录设置处理，勿通过唯一 SSH 链路远程试切换。

独立会话使用自己的 labwc 配置，不读取原用户面板/桌面管理器的 autostart；按需启动 fcitx5、lxpolkit，保留 DSI-1 的 270° 横屏方向。规则请求普通主窗口默认最大化；应用自己的全屏和模态对话框行为仍由应用与 labwc 处理。当前原桌面会话存在合成器返回零尺寸的最大化异常，独立会话实际几何、全屏和模态行为仍需现场验收，不能视为已通过。

退出 uDeck 后在登录界面选择原「Raspberry Pi Desktop on Wayland」即可回退。软件卸载：

```sh
sudo apt-get remove udeck
```

不要附带执行 `autoremove`、删除原桌面配置或删除用户数据。`~/.config/udeck/settings.json` 包含收藏、偏好、焦点和校准结果；卸载后保留，是否清理由用户另行决定。

## 诊断与复现

```sh
udeckctl home
udeckctl switcher
udeckctl quick-settings
udeckctl doctor --json
PYTHONPATH=src python3 tools/verify-windows.py
PYTHONPATH=src python3 tools/measure-shell.py --seconds 60 --output artifacts/performance.json
```

`doctor` 是只读检查；`verify-windows.py` 默认仅创建、激活和请求关闭自己创建的 Wayland/Xwayland 测试窗口，额外传入 `--check-maximized` 才测试 foreign 协议最大化及实际渲染尺寸；`measure-shell.py` 启动无手柄输入的真实窗口化壳并自动退出。后两项需要正确的图形会话环境，不能代替物理按键或独立登录验收。

验证安装版而非源码时去掉 `PYTHONPATH=src`，并确认没有继承其他 `PYTHONPATH`。性能输出区分内部首帧时间和包含 Python 导入的 `launchToReadySeconds`，启动目标使用后者；RSS/CPU 为壳进程的空闲采样，不是整机或完整登录会话指标。

具体已测事实、局限和未完成的现场项目见 [实机验收记录](acceptance-2026-11-06.md)。
