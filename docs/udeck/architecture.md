# uDeck v1 架构与边界

## 分层

| 模块 | 职责 |
| --- | --- |
| `qml/Main.qml` | 原生 Qt Quick 视觉、按键交互、焦点滚动和输入框；阻止鼠标手势，外部文本按纯文本显示 |
| `controller.py` | 五页快照、上下文菜单、弹层栈、焦点恢复、文件异步任务和操作反馈 |
| `core.py` | 非循环空间导航、XDG 配置校验与私有原子保存 |
| `input.py` | evdev 独立手柄发现、八步映射、前台 grab/release、方向长按重复和热拔插恢复 |
| `pointer.py` | 会话内持续屏蔽独立鼠标接口，仅将已确认的内置 L/R 前台按下沿转为切页 |
| `desktop.py` | 标准 desktop entry 读取、去重、本地化、图标元数据和 Gio 启动 |
| `windows.py` | libwayland-client + ctypes，实现已公布的 wlr foreign-toplevel v3 客户端 |
| `files.py` | 文件列表、名称验证、安全重命名/复制/移动、Gio 打开与回收站 |
| `backend.py` | 单独 asyncio 线程上的系统 D-Bus 代理、音频子进程和背光/电源读取 |
| `mock.py` | 无副作用的固定数据与模拟操作 |
| `main.py` / `cli.py` | 进程生命周期、主题图标、QML 引导、会话 IPC 和诊断 |

QML 不调用 shell 命令、不直接访问设备。耗时 D-Bus 调用和子进程在 asyncio 工作线程执行；文件 I/O 与应用启动使用单工作线程。工作结果通过 Qt signals 回到主线程，不以等待服务阻塞方向导航。

## 窗口与会话

不写新合成器，不以进程列表代替窗口列表。`zwlr_foreign_toplevel_manager_v1` 提供真实窗口的标题、app_id、状态、父子关系、激活与关闭请求；主程序维护独立 Wayland 连接，通过 QSocketNotifier 接入 Qt 事件循环。原生 Wayland 与 Xwayland 使用同一窗口协议。

会话入口是 `/usr/share/wayland-sessions/udeck.desktop`。启动器使用 `labwc -C /usr/share/udeck/labwc -S /usr/libexec/udeck/session`，不覆盖 `~/.config/labwc`。独立 autostart 明确为空，防止回退执行原面板或桌面管理器。监督脚本最多重启异常退出的桌面壳三次，正常退出则结束独立会话。

labwc 普通窗口规则负责默认最大化，不抢占应用内部键盘，不自动关闭其他窗口。模态对话框和全屏不改造；完整会话兼容性须现场验证。原桌面会话保留；软件包不修改 LightDM 默认值，只有显式运行自动登录工具才会备份并修改默认会话。

从 0.1.1 开始，桌面壳本身请求真正的 `Window.FullScreen`，而不是以最大化模拟全屏。所有 present 路径都显式恢复全屏，避免 `show()` 把返回桌面的壳恢复成普通窗口。窗口化和 mock 预览保持普通窗口。包安装仍不改变登录默认值；管理员可单独执行 `tools/configure-login.py --user USER`，在备份和校验后选择 uDeck 自动登录，不触发当前会话注销或系统重启。

## 输入所有权

ABXY 仅打开符合已确认 uConsole VID/PID 的独立游戏手柄事件节点。手柄发现排除 Keyboard、Mouse、Consumer Control，不对整个键盘调用 EVIOCGRAB。键盘字母不会被当作 ABXY。

已实按确认的 `1eaf:0024:20230713` 固件在没有保存映射且按钮能力匹配时使用官方布局：A=289、B=290、X=288、Y=291；未知固件仍需校准，自定义配置优先且绑定设备 fingerprint。`mapped` 表示按钮路由完整，`verified` 表示完整校准配置；二者不替代现场功能验收。不会推断 j/k/u/i 字母。

八步校准支持混合输入：独立手柄按钮/轴经 evdev 采集，原生键盘方向经 Qt 前台事件进入校准状态机并保存为 `keyboardDirections`，不会因此独占键盘。校准取消立即退出采集状态，未完成的映射不保存。

0.1.3 的真实全屏模式由 `PointerGuard` 另行持有独立鼠标接口：识别左键及相对/绝对双轴能力，排除任何含普通键盘键位的混合接口。独占后丢弃移动、滚轮及鼠标按键事件；只在壳前台时，将已确认 fingerprint 和设备名的内置 L/R 新按下沿转为上一页/下一页。外接独立鼠标也被屏蔽，但不成为切页键。L/R 不重复触发、不循环翻页，弹层期间无效，返回页面恢复原选中项。

鼠标接管持续到壳退出，壳失焦后仍屏蔽第三方应用的鼠标操作；手柄继续按前台所有权释放。扫描支持热拔插，事件溢出后重同步按住状态，不制造按键；权限失败报告到诊断而不强占键盘。未改变的扫描状态不重复发布 UI。关闭壳释放所有鼠标接口。独立 labwc 配置仅对精确名称 `ClockworkPI uConsole Mouse` 设置 `sendEventsMode=no`，使内置指针从会话启动即被禁用；不覆盖原桌面配置。

QML 列表与滚动条不接受指针滚动/拖动，输入框不允许鼠标选字；没有项目单击、双击或位置选中逻辑。唯一的顶层鼠标区域消耗移动/滚轮/双击，将窗口化预览中的左/右按下模拟为 L/R 切页。壳内隐藏光标；不声称替第三方应用隐藏其自行绘制的光标。窗口化、mock 和 `--no-input` 不接管整个会话的鼠标。第三方应用使用自身键盘或手柄支持，不注入虚拟肩键或改造其焦点系统。

只有 Qt 窗口 active 时持有手柄；失焦、退出、设备消失和事件丢失都会释放。方向键初次移动后约 350 ms 开始重复，随后约 90 ms 一步；A/B/X/Y 不因 Linux 自动重复而重复确认。

独立会话的 `Ctrl+Alt+Esc` 通过 labwc 调用 `udeckctl home`，再通过窗口协议激活桌面，不建立全局 ABXY 拦截器。

## 系统服务

- NetworkManager：系统 D-Bus 获取网卡、AP、连接状态与已保存 profile；SecretAgent 在界面请求密码，取消使用 NetworkManager 的错误类型。新个人网络凭据交给 NetworkManager 管理，不写入 uDeck 配置。
- BlueZ：ObjectManager 追踪适配器与设备；Agent1 支持 PIN、passkey、数字确认与服务授权；显示配对码的进度更新同一弹层。独立会话请求默认代理，窗口化测试不抢换原默认代理。
- 音频：`wpctl` 读写音量/静音；`pactl` 枚举输出、设置默认 sink，并订阅变化；复用现有 PipeWire/WirePlumber。
- 背光/电池：读已有 sysfs；仅使用当前用户已有的背光写权限，不更改设备节点权限或以 root 启动整个壳。
- 电源：logind 处理注销、重启、关机；swaylock 锁屏，wlopm/swayidle 熄屏。不把熄屏称为系统休眠。

主动操作与状态分离：D-Bus 请求返回不等于网络已连通、蓝牙已连接或音频已播放；界面依据后续状态更新显示结果。设备消失、权限错误与失败留在当前页面。

## 本机通信与数据

会话 D-Bus 名称 `io.github.zhubby.uDeck`，对象 `/io/github/zhubby/uDeck`，接口 `io.github.zhubby.uDeck.Control`。暴露 `Home`、`Switcher`、`QuickSettings`、`Diagnose`；不开放 TCP/HTTP，不允许通过 IPC 传入任意文件或执行命令。

配置位于 `$XDG_CONFIG_HOME/udeck/settings.json`，未设置时为 `~/.config/udeck/settings.json`；包含 favorites、recent、focus、preferences、input。临时文件以 0600 创建，fsync 后原子替换。输入密码和配对确认只存在于瞬时内存；SSH 密码没有部署文件或日志入口。

文件覆盖使用明确确认；无覆盖 rename 使用 Linux `renameat2(RENAME_NOREPLACE)`，开发机使用 macOS 对应排他 rename。大文件复制有 staging、取消、源变化检测和清理；临时目录以 0700、临时文件以 0600 创建，再保留源权限，避免复制私密文件期间被其他用户读取。拒绝复制管道/设备/套接字。跨文件系统移动的源只移入系统回收站，不以递归永久删除作为后备。

Gio 文件服务失败会把 stderr 原因返回当前页面。挂载点不支持回收时保留源；跨文件系统移动会报告目标已复制但源仍保留，并附系统原因，不把部分成功包装为成功移动。

所有外部参数通过结构化 D-Bus 或 argv 传入，不把 SSID、设备名、文件名、desktop entry 字段拼入 shell。固定的熄屏/恢复命令不接受用户参数。QML 显示外部文字时禁用富文本解释。

## 上游接口参考

- [wlr foreign-toplevel 协议原文](https://gitlab.freedesktop.org/wlroots/wlr-protocols/-/blob/master/unstable/wlr-foreign-toplevel-management-unstable-v1.xml)
- [NetworkManager D-Bus API](https://networkmanager.dev/docs/api/latest/)
- [个人网络 PSK / SAE 设置](https://networkmanager.dev/docs/api/latest/settings-802-11-wireless-security.html)
- [BlueZ Agent API](https://github.com/bluez/bluez/blob/master/doc/org.bluez.Agent.rst)
- [labwc 配置文档](https://labwc.github.io/labwc-config.5.html)

这些接口文档用于实现契约；实机通过项目与待现场验收项目分开记录，不以规范或设备枚举推定硬件成功。
