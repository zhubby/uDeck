# uDeck 架构与边界

## 分层与分发

uDeck 使用 Python / PySide6、Qt Quick、labwc 和 Linux 系统服务。
一个 arm64 Debian `udeck` 包分发桌面、Terminal、五个内容应用和共享资源。
版本只定义在 `src/udeck/__init__.py`，标签与 Debian changelog 同步。
开发锁定 uv 与 Python，设备使用 APT 的系统 Python 与 Qt。
安装、升级和发行契约见[发行指南](debian-distribution.md)。

| 模块 | 职责与依赖方向 |
| --- | --- |
| `main` / QML | 装配窗口、控制器和输入；QML 不执行系统命令 |
| `controller` | 页面、菜单、焦点、模型与动作编排 |
| `backend` | 系统接口和 Mock 状态，不承担页面布局 |
| `apps/common` / `apps/media` | 应用共享状态、索引、输入与媒体引擎 |
| `terminal` | 独立 PTY、原生插件与终端窗口 |
| `runtime_console` | 应用身份、指标聚合和退出 |
| `network_files` / `smb_files` | 独立网络共享服务 |
| `emulator_saves` | 原生存档、不可变历史与后台同步 |

应用保持独立进程、内容引擎与数据协议。
共同设计和引擎边界见[应用架构](../design/app-suite/native-integration.md)。

## 会话与生命周期

独立会话使用专用 labwc 配置和受监督桌面。
启动输入法、系统授权代理、熄屏组件并设置横屏方向。
原桌面与默认登录由安装保留；自动登录仅由显式工具配置。
真实桌面请求全屏，窗口化与 mock 保持普通窗口。

监督器只重启异常退出的桌面。
最近 60 秒的崩溃使用三次预算，稳定运行后重置。
正常退出和会话 TERM 不重启；结束时恢复输入配置。
安装不主动结束现有应用，旧进程保留已加载的代码。
QML 编译缓存按源码内容隔离，避免更新后复用旧编译内容。

## 内置应用路由

界面通过七个固定身份启动和激活内置应用。
`app_routing.native_app_id` 在创建启动请求和 D-Bus 调用前校验身份。
`DesktopCatalog` 可读取名称和图标，不能替换启动命令。
Exec、Terminal 和桌面文件工作目录不进入执行路径。
文件以绝对路径参数传入，终端入口固定到 uDeck 模块。

Files 按 `apps/common/library.py` 共享格式表路由，
不调用系统默认应用或第三方打开方式。
ZIP 和其他未支持格式只展示详情，见[Files](files.md)。
Browser 和 Reader 禁止未知协议的系统分发，
拒绝网页上传与颜色选择的系统选择器。
网页确认与认证仍使用进程内 Qt Quick 对话框。

Console、Alt-Tab 和异步恢复都在激活前复核目标身份。
第三方窗口可保留诊断和退出入口，不作为界面激活目标。
受监管的 RetroArch 游戏进程保留。
其窗口授权依赖唯一窗口与监管进程证明；
返回游戏等待合成器确认身份与活动状态，失败保留前端。
锁屏、系统授权和后台工具不受应用列表过滤影响。
终端中显式输入的命令遵循操作系统权限。

## 输入所有权

ABXY 只打开已确认身份的独立游戏手柄接口。
不独占普通键盘、Consumer Control 或含普通键位的混合接口。
校准按设备指纹保存，普通字母不冒充按钮。
独立会话根据真实前台窗口交接手柄。
接管确认后显示窗口，Qt 焦点确认后投递排队事件。
锁屏、失活、断开和交接释放注入状态。
返回 Home 不同时最小化应用，避免焦点竞争。

`PointerGuard` 负责鼠标抓取、L/R、原始诊断和相对帧。
`TrackballInput` 负责倍率、手势与目标归属。
`VirtualInput` 向合成器一次提交双轴相对移动。
`PointerCursor` 只观察 Qt 坐标和窗口状态，不累加设备位移。
机身轨迹球倍率为 4 px/count，合成器维护全局坐标。
窗口间切换不恢复旧绝对坐标，方向键指针模式共用相对入口。
完整操作、快捷键事务和恢复见[输入指南](input.md)。

## 系统服务

- NetworkManager 通过系统 D-Bus 提供网卡、AP、连接和配置。
  Wi-Fi 操作携带 deviceId，凭据提交前后重新核对设备与请求。
  SecretAgent 无法确定归属时返回 NoSecrets，不猜测网卡。
  infrastructure 配置复用与热点配置分开，路由由 NetworkManager 决定。
- BlueZ ObjectManager 提供适配器与设备；Agent1 提供 PIN、passkey 和确认。
  独立会话请求默认代理，窗口化测试不抢换原代理。
- PipeWire/WirePlumber 沿用系统服务。
  wpctl 提供音量与静音，pactl 枚举设备并订阅变化。
- 背光、电池和系统信息读取现有 sysfs、设备树与 /proc。
  背光仅使用当前用户已有权限，不以 root 运行整个桌面。
- logind 负责会话和电源，timedate1 负责时区。
  swaylock 锁屏，wlopm/swayidle 熄屏，不将熄屏称作系统休眠。
- 共享服务独立于文件页面，目录、网络授权和开放时长见
  [网页访问](files-network-access.md)及 [SMB](sharing.md)。

请求返回不等于系统状态完成。
UI 根据后续实际状态报告结果，失败保留页面、焦点和原因。
硬件缺失显示不可用，不伪造零值或成功。

## 本地通信与持久化

桌面 D-Bus 名称为 `io.github.zhubby.uDeck`，
对象为 `/io/github/zhubby/uDeck`，
接口为 `io.github.zhubby.uDeck.Control`。
`udeckctl` 提供固定的页面、输入、锁屏和诊断动作，
不接受任意脚本、文件执行或键盘序列。

内置应用使用按图形会话散列的 D-Bus 名称。
Terminal 的 Open 请求使用结构化 cwd、argv、title 和环境，
诊断不输出完整环境，启动参数不经 shell 重新拆分。

全局设置位于 `$XDG_CONFIG_HOME/udeck/settings.json`，
默认根为 `~/.config`；快捷键独立保存到 `shortcuts.json`。
收藏、焦点、偏好、输入映射和应用输入配置保留已有字段。
临时文件以 0600 创建，fsync 后原子替换，保存失败恢复旧值。
密码与配对确认保持瞬时状态，凭据由对应系统服务保存。

文件复制使用私有 staging、源变化检查、取消和原子发布。
跨卷移动只将源移入回收站，失败保留源。
共享目录使用描述符和身份约束，拒绝路径逃逸。
外部名称和路径使用结构化 D-Bus 或 argv，不拼接 shell。
QML 对外部文字禁用富文本解释。

## 导航与响应

页面使用模型与轻量视图快照，导航只发布选中索引。
后台任务用稳定身份与代次拒绝旧结果。
Console 统计只在可见时运行，详情内存只读取已归属进程。
音效复用 PCM 流，隐藏和空闲时取消无用途工作。
短过渡不延迟真实操作，见[动效规范](../motion/README.md)。
验证按源码、安装包、设备和物理体验分层，见[验证规范](validation.md)。

## 上游接口

- [wlr foreign-toplevel](https://gitlab.freedesktop.org/wlroots/wlr-protocols/-/blob/master/unstable/wlr-foreign-toplevel-management-unstable-v1.xml)
- [NetworkManager D-Bus](https://networkmanager.dev/docs/api/latest/)
- [BlueZ Agent](https://github.com/bluez/bluez/blob/master/doc/org.bluez.Agent.rst)
- [labwc 配置](https://labwc.github.io/labwc-config.5.html)

[PROTOCOL]: Update this header on change, then check AGENTS.md
