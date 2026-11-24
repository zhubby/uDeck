# src/udeck/
> L2 | Parent: ../../AGENTS.md

__init__.py: 唯一版本源；桌面、独立应用和 setuptools 共用。
app_routing.py: 内置应用白名单、稳定身份和 D-Bus 路径。
appearance.py: 界面主题选择；文档调色板独立。
apps/: 共享应用框架和独立应用。
build_info.py: 读取构建时冻结的提交、源码摘要与包身份。
assets/: 随包图标、品牌、输入提示与界面音效。
audio.py: PulseAudio 与 PipeWire 设备状态归一。
backend.py: 系统服务、音频状态去重、蓝牙授权和网络授权。
battery.py: 电池测量读取与展示数据。
cli.py: 命令入口、诊断和控制请求。
compatibility.py: 输入预释放、原生窗口恢复与异步身份复验。
console.py: 全局 Console 面板、受控引擎授权与原生焦点恢复。
controller.py: 桌面交互编排；局部选择与轻量视图独立于完整诊断。
core.py: 导航、偏好存储和主题语言基础。
cursor.py: 指针光标图像与位置。
desktop.py: 桌面元数据索引、Exec 解析与固定内置模块启动。
directions.py: 方向接口连接预筛选、修饰键隔离与松键读取。
emulator_saves/: 原生存档、历史快照和云同步。
file_controller.py: 文件浏览、Reader 全格式关联、内置白名单与预览任务。
file_icons.py: 文件类型到图标的映射。
file_jobs.py: 后台文件任务与源路径去重。
file_locations.py: 用户目录、挂载点与卸载。
file_model.py: 文件列表的 Qt 模型。
file_preview.py: 常规文件安全读取与预览。
file_trash.py: 回收站目录、身份和文件恢复。
files.py: 文件查询、名称校验与基础操作；不提供系统默认打开。
fonts/: 界面字体、许可证和来源。
home.py: 首页快捷入口。
hotspot.py: 热点名称校验与公开状态。
hotspot_backend.py: 设备绑定的 NetworkManager 热点配置。
hotspot_controller.py: 热点菜单与按钮导航。
i18n.py: 稳定消息标识、翻译和错误文案渲染。
icons.py: 随包图像与应用图标提供器。
input.py: sysfs 预筛选、启动按键隔离、事件投递开关与交接重试。
interface_audio.py: 单条复用 PCM 音频流、空闲暂停、字节写入与设备恢复。
ipc_client.py: 无 Qt 依赖的已有实例启动转发。
key_test.py: 诊断弹窗中的按键边沿观测。
key_test_device.py: 诊断激活期间的 sysfs 预筛选与键盘报告读取。
key_test_layout.py: uConsole 两层固件的键帽映射。
launch.py: 按应用和文件去重的启动请求与窗口状态跟踪。
launch_controller.py: 内置应用筛选、文件启动、单实例转发与失败反馈。
locales/: 中英文稳定消息目录。
main.py: 桌面启动、系统服务、显示前输入释放与输入路由组装。
menu_icons.py: 系统菜单图标与动作分离。
messages.py: Python 与 QML 共用的稳定消息标识。
mock.py: 桌面预览的隔离系统状态。
network_files/: 网络文件访问服务与网页。
performance.py: 内存中的启动、激活和交互阶段计时。
session_supervisor.py: 滚动崩溃预算、正常退出和桌面子进程清理。
pointer.py: sysfs 预筛选、指针输入归属与保护；轮询不打开非指针接口。
preflight.py: 只读 CM4 系统和依赖兼容检测。
qml/: 桌面视图、控件和动效。
qml_cache.py: 按源码内容隔离 QML 编译缓存。
runtime_console/: 应用指标、进程身份和有序终止。
screenshot.py: Wayland 实际屏幕捕获与 PNG 验证。
session_config.py: labwc 会话配置生成与方向隔离。
session_shortcuts.py: 共用系统动作表的离线快捷键工具。
share_settings.py: 共享偏好保存的事务与回滚。
sharing.py: 共享菜单、草稿与状态去重；隐藏且已关闭的服务停止查询。
sharing_messages.py: 共享服务错误到界面消息的转换。
shortcut_controller.py: 系统快捷键设置的按钮交互。
shortcut_recorder.py: 临时抑制 labwc 快捷键的录制窗口。
shortcut_session.py: 串行协调快捷键变更与方向隔离。
shortcuts.py: 系统动作、固定原生终端和 Console 窗口切换快捷键。
smb_files/: Samba 共享服务与访问边界。
sounds.py: 前台音效、单事件合并与独立线程调度；复用持续音频流。
system_info.py: 硬件和操作系统信息读取。
terminal/: 原生终端、默认项与私有插件入口。
terminal_routing.py: 依据前台窗口身份转发套件输入。
text_input.py: 文本输入与物理按钮的归属判定。
timezone.py: 时区分组、标签和本地时间。
trackball.py: 固件轨迹球手势与输入路由。
virtual_input.py: 合成系统输入。
wifi.py: Wi-Fi 身份、状态和错误文案。
wifi_backend.py: NetworkManager 读取与设备绑定配置。
wifi_controller.py: Wi-Fi 菜单及稳定网络选择。
windows.py: 合成器窗口发现、激活确认、内置边界与按进程身份的引擎授权。

[PROTOCOL]: Update this header on change, then check AGENTS.md
