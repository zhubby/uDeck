# tests/
> L2 | Parent: ../AGENTS.md

成员清单：

apps_motion_continuity_probe.py: 连续切页、编码封面 URL、身份与标题重选探针。
test_apps_motion_continuity.py: 共享应用动效的正常与减少动画回归入口。

navigation_continuity_probe.py: 独立桌面窗口的切页重入、滚动改向、设置刷新和补位轨迹探针。
test_navigation_continuity_qml.py: 双主题导航中途状态的离屏回归入口。

test_runtime_console_processes.py: 按应用采样的三种内存口径、失败隔离和 pidfd 终止身份回归。
test_runtime_console_apps.py: 轻量应用状态与原生存档退出回归。
test_runtime_console.py: 空所有者去重、身份变更、过期状态、详情和退出回归。
runtime_console_qml_probe.py: 等待稳定几何，验证三种内存口径、指标复用和详情输入。
test_runtime_console_qml.py: Console 详情交互、中英文与双主题尺寸回归。
motion_qml_probe.py: 零全量快照的选中项移动、焦点改向与弹窗隔离探针。
test_motion_qml.py: 双主题与减少动画的桌面短过渡回归。
motion_extended_probe.py: 补位、Toast、封面与共享应用输入的真实 Qt 探针。
test_motion_extended_qml.py: 完整动效的双主题与减少动画回归。
test_motion_measurement.py: 输入屏障、呈现分母、锁存、反向输入、长帧、电源预检和空闲重绘回归。
dialog_motion_continuity_probe.py: 加载退出内容、请求替换与尺寸中途关闭的真实 Qt 探针。
test_dialog_motion_continuity.py: 双主题与减少动画的弹窗连续性回归。

app_forwarding_probe.py: 独立进程探针，验证 app_forwarding 流程。
app_input_handoff_probe.py: 首次窗口等待交接、真实会话注册和默认可见回归。
app_lazy_surface_probe.py: 独立进程探针，验证 app_lazy_surface 流程。
app_settings_device_probe.py: 独立进程探针，验证 app_settings_device 流程。
apps_games_probe.py: 独立进程探针，验证 apps_games 流程。
apps_ipc_probe.py: 独立进程探针，验证 apps_ipc 流程。
apps_native_probe.py: 独立进程探针，验证 apps_native 流程。
audio_qml_probe.py: 等待弹窗过渡结束，校验音频菜单布局、焦点和设备选择。
battery_qml_probe.py: 等待弹窗几何终态，验证电池测量刷新、文字与边界。
browser_interaction_probe.py: 独立进程探针，验证 browser_interaction 流程。
conftest.py: 共享离屏 QApplication 与 Qt 对象回收夹具。
console_qml_probe.py: 独立进程探针，验证 console_qml 流程。
cursor_qml_probe.py: 独立进程探针，验证 cursor_qml 流程。
debian_package_probe.py: 独立进程探针，验证 debian_package 流程。
emulator_save_daemon_probe.py: 独立进程探针，验证 emulator_save_daemon 流程。
file_icons_probe.py: 独立进程探针，验证 file_icons 流程。
files_qml_probe.py: 独立进程探针，验证 files_qml 流程。
game_fixtures.py: 测试夹具，为 game_fixtures 提供隔离数据。
games_device_probe.py: 独立进程探针，验证 games_device 流程。
games_inventory_probe.py: 独立进程探针，验证 games_inventory 流程。
games_qml_probe.py: 游戏菜单、标题、封面身份保留与坏图回退的 Qt 探针。
home_qml_probe.py: 独立进程探针，验证 home_qml 流程。
hotspot_device_probe.py: 独立进程探针，验证 hotspot_device 流程。
hotspot_nm_profile_probe.py: 独立进程探针，验证 hotspot_nm_profile 流程。
hotspot_qml_probe.py: 等待弹窗尺寸稳定，验证热点边界、密码输入与显示、图标和按键。
i18n_qml_probe.py: 独立进程探针，验证 i18n_qml 流程。
input_prompts_qml_probe.py: 独立进程探针，验证 input_prompts_qml 流程。
interface_sounds_qml_probe.py: 音效开关、快捷设置与离屏零播放线程的 QML 探针。
launch_qml_probe.py: 独立进程探针，验证 launch_qml 流程。
libretro_fixtures.py: 测试夹具，为 libretro_fixtures 提供隔离数据。
media_takeover_probe.py: 独立进程探针，验证 media_takeover 流程。
mobi_fixture.py: 测试夹具，为 mobi_fixture 提供隔离数据。
native_shell_forward_probe.py: 独立进程探针，验证 native_shell_forward 流程。
native_terminal_appearance_probe.py: 独立进程探针，验证 native_terminal_appearance 流程。
native_terminal_probe.py: 独立进程探针，验证 native_terminal 流程。
network_files_web_probe.py: 独立进程探针，验证 network_files_web 流程。
reader_mobi_probe.py: 独立进程探针，验证 reader_mobi 流程。
settings_icons_probe.py: 独立进程探针，验证 settings_icons 流程。
settings_qml_probe.py: 等待过渡完成，校验设置、系统信息和按键测试布局。
sharing_qml_probe.py: 独立进程探针，验证 sharing_qml 流程。
test_sharing_daemon_polling.py: 关闭时零网络发现、启用后撤销检查和按需状态回归。
shortcuts_qml_probe.py: 等待弹窗几何终态，验证快捷键录制、冲突与边界。
system_device_probe.py: 独立进程探针，验证 system_device 流程。
terminal_appearance_probe.py: 独立进程探针，验证 terminal_appearance 流程。
terminal_application_probe.py: 独立进程探针，验证 terminal_application 流程。
terminal_default_device_probe.py: 独立进程探针，验证 terminal_default_device 流程。
terminal_device_audit_probe.py: 独立进程探针，验证 terminal_device_audit 流程。
terminal_device_probe.py: 独立进程探针，验证 terminal_device 流程。
terminal_font_probe.py: 独立进程探针，验证 terminal_font 流程。
terminal_input_device_probe.py: 独立进程探针，验证 terminal_input_device 流程。
terminal_ipc_probe.py: 独立进程探针，验证 terminal_ipc 流程。
test_app_default_sources.py: pytest 回归入口，验证 app_default_sources 边界。
test_app_menu_icons.py: pytest 回归入口，验证 app_menu_icons 边界。
test_app_performance.py: pytest 回归入口，验证 app_performance 边界。
test_build_info.py: 构建来源冻结、内容哈希与运行时读取回归。
test_session_supervisor.py: 独立桌面进程的崩溃预算、终止与重启回归。
test_suite_runner.py: 逐文件测试调度、超时清理与证据保留回归。
test_app_settings.py: pytest 回归入口，验证 app_settings 边界。
test_apps_core.py: pytest 回归入口，验证 apps_core 边界。
test_apps_native.py: 首次窗口交接、应用引擎、菜单和翻译的集成回归。
test_apps_review.py: 应用启动、游戏暂停确认与异步取消的回归测试。
test_apps_routing.py: 真实手柄队列的到期轮转、代次隔离与断线回退回归。
test_apps_saves.py: pytest 回归入口，验证 apps_saves 边界。
test_audio.py: 音频状态去重、设备切换与服务错误恢复回归。
test_audio_qml.py: 双尺寸、双语言和双主题的音频菜单回归。
test_backend.py: pytest 回归入口，验证 backend 边界。
test_battery.py: pytest 回归入口，验证 battery 边界。
test_battery_qml.py: pytest 回归入口，验证 battery_qml 边界。
test_browser_interactions.py: pytest 回归入口，验证 browser_interactions 边界。
test_cli.py: pytest 回归入口，验证 cli 边界。
test_compatibility.py: 冷启动交接、激活超时恢复、错误来源与菜单身份隔离回归。
test_console.py: pytest 回归入口，验证 console 边界。
test_console_qml.py: pytest 回归入口，验证 console_qml 边界。
test_core.py: pytest 回归入口，验证 core 边界。
test_cursor.py: pytest 回归入口，验证 cursor 边界。
test_directions.py: 方向连接筛选、启动按住隔离与修饰键释放回归。
test_emulator_engine.py: 真实 QProcess 协议回归，覆盖背压、通知、读档屏障与重启。
test_emulator_game_info.py: pytest 回归入口，验证 emulator_game_info 边界。
test_emulator_migration.py: pytest 回归入口，验证 emulator_migration 边界。
test_emulator_platforms.py: pytest 回归入口，验证 emulator_platforms 边界。
test_emulator_playlist_browser.py: pytest 回归入口，验证 emulator_playlist_browser 边界。
test_emulator_playlist_library.py: 列表保留、封面工作线程、修订冲突和关闭后禁止重启回归。
test_emulator_playlists.py: pytest 回归入口，验证 emulator_playlists 边界。
test_emulator_save_daemon.py: pytest 回归入口，验证 emulator_save_daemon 边界。
test_emulator_save_management.py: pytest 回归入口，验证 emulator_save_management 边界。
test_emulator_save_sync.py: pytest 回归入口，验证 emulator_save_sync 边界。
test_emulator_save_ui.py: pytest 回归入口，验证 emulator_save_ui 边界。
test_emulator_thumbnails.py: 批量探测次数、封面更新、符号链接和下载重试边界回归。
test_file_icons.py: pytest 回归入口，验证 file_icons 边界。
test_files_controller.py: 文件交互、轻量视图与完整诊断的边界回归。
test_files_features.py: pytest 回归入口，验证 files_features 边界。
test_files_jobs.py: pytest 回归入口，验证 files_jobs 边界。
test_files_locations_trash.py: pytest 回归入口，验证 files_locations_trash 边界。
test_files_model_preview.py: pytest 回归入口，验证 files_model_preview 边界。
test_files_qml.py: pytest 回归入口，验证 files_qml 边界。
test_fonts.py: pytest 回归入口，验证 fonts 边界。
test_games_catalog.py: pytest 回归入口，验证 games_catalog 边界。
test_games_management.py: pytest 回归入口，验证 games_management 边界。
test_games_qml.py: pytest 回归入口，验证 games_qml 边界。
test_games_regressions.py: pytest 回归入口，验证 games_regressions 边界。
test_home.py: 首页固定入口、Console 名称与焦点恢复回归。
test_home_qml.py: pytest 回归入口，验证 home_qml 边界。
test_hotspot.py: pytest 回归入口，验证 hotspot 边界。
test_hotspot_qml.py: pytest 回归入口，验证 hotspot_qml 边界。
test_hotspot_ui.py: pytest 回归入口，验证 hotspot_ui 边界。
test_i18n.py: pytest 回归入口，验证 i18n 边界。
test_i18n_qml.py: pytest 回归入口，验证 i18n_qml 边界。
test_input.py: 焦点前事件保留、启动按键隔离、交接重试与断线重连回归。
test_input_prompts.py: pytest 回归入口，验证 input_prompts 边界。
test_interface_sounds.py: 语义音效限频、前台取消与播放线程连续性回归。
test_interface_audio.py: 单流复用、空闲暂停、PCM 短写和设备恢复回归。
test_interface_sounds_qml.py: pytest 回归入口，验证 interface_sounds_qml 边界。
test_key_test.py: pytest 回归入口，验证 key_test 边界。
test_key_test_device.py: sysfs 扫描筛选、设备路径复用、读取回退与按键去重回归。
test_key_test_full.py: pytest 回归入口，验证 key_test_full 边界。
test_launch.py: pytest 回归入口，验证 launch 边界。
test_launch_controller.py: pytest 回归入口，验证 launch_controller 边界。
test_launch_qml.py: pytest 回归入口，验证 launch_qml 边界。
test_login.py: pytest 回归入口，验证 login 边界。
test_media_takeover.py: pytest 回归入口，验证 media_takeover 边界。
test_network_files.py: pytest 回归入口，验证 network_files 边界。
test_network_files_client.py: pytest 回归入口，验证 network_files_client 边界。
test_network_files_edges.py: pytest 回归入口，验证 network_files_edges 边界。
test_network_files_lifecycle.py: pytest 回归入口，验证 network_files_lifecycle 边界。
test_network_files_ui.py: 共享菜单、后台查询边界与重复状态去重回归。
test_network_files_web.py: pytest 回归入口，验证 network_files_web 边界。
test_performance_tools.py: pytest 回归入口，验证 performance_tools 边界。
test_pointer.py: 指针归属、sysfs 预筛选、错误回退与设备路径复用回归。
test_preflight.py: pytest 回归入口，验证 preflight 边界。
test_qml.py: pytest 回归入口，验证 qml 边界。
test_reader_layout.py: pytest 回归入口，验证 reader_layout 边界。
test_reader_mobi.py: pytest 回归入口，验证 reader_mobi 边界。
test_release.py: 稳定版本、包元数据、构建环境边界和安装入口回归。
test_qml_cache.py: 相同时间戳的源码更新、缓存复用和环境覆盖回归。
test_safety.py: pytest 回归入口，验证 safety 边界。
test_samba_install_guard.py: pytest 回归入口，验证 samba_install_guard 边界。
test_screenshot.py: pytest 回归入口，验证 screenshot 边界。
test_session_config.py: pytest 回归入口，验证 session_config 边界。
test_session_shortcuts.py: pytest 回归入口，验证 session_shortcuts 边界。
test_settings_menus.py: pytest 回归入口，验证 settings_menus 边界。
test_settings_qml.py: pytest 回归入口，验证 settings_qml 边界。
test_sharing_controls.py: pytest 回归入口，验证 sharing_controls 边界。
test_shortcut_controls.py: pytest 回归入口，验证 shortcut_controls 边界。
test_shortcut_session.py: pytest 回归入口，验证 shortcut_session 边界。
test_shortcuts.py: pytest 回归入口，验证 shortcuts 边界。
test_shortcuts_qml.py: pytest 回归入口，验证 shortcuts_qml 边界。
test_smb_dbus.py: pytest 回归入口，验证 smb_dbus 边界。
test_smb_files.py: pytest 回归入口，验证 smb_files 边界。
test_sound_interactions.py: pytest 回归入口，验证 sound_interactions 边界。
test_system_info.py: pytest 回归入口，验证 system_info 边界。
test_terminal_activation.py: pytest 回归入口，验证 terminal_activation 边界。
test_terminal_appearance.py: pytest 回归入口，验证 terminal_appearance 边界。
test_terminal_controller.py: pytest 回归入口，验证 terminal_controller 边界。
test_terminal_core.py: pytest 回归入口，验证 terminal_core 边界。
test_terminal_defaults.py: pytest 回归入口，验证 terminal_defaults 边界。
test_terminal_fonts.py: pytest 回归入口，验证 terminal_fonts 边界。
test_terminal_launchers.py: pytest 回归入口，验证 terminal_launchers 边界。
test_terminal_native.py: pytest 回归入口，验证 terminal_native 边界。
test_terminal_routing.py: pytest 回归入口，验证 terminal_routing 边界。
test_terminal_system_defaults.py: pytest 回归入口，验证 terminal_system_defaults 边界。
test_theme.py: pytest 回归入口，验证 theme 边界。
test_theme_qml.py: pytest 回归入口，验证 theme_qml 边界。
test_timezone.py: pytest 回归入口，验证 timezone 边界。
test_trackball.py: pytest 回归入口，验证 trackball 边界。
test_ui.py: pytest 回归入口，验证 ui 边界。
test_ui_interactions.py: pytest 回归入口，验证 ui_interactions 边界。
test_video_playback.py: pytest 回归入口，验证 video_playback 边界。
test_video_subtitles.py: pytest 回归入口，验证 video_subtitles 边界。
test_virtual_input.py: pytest 回归入口，验证 virtual_input 边界。
test_wifi.py: pytest 回归入口，验证 wifi 边界。
test_wifi_management.py: pytest 回归入口，验证 wifi_management 边界。
test_wifi_management_qml.py: pytest 回归入口，验证 wifi_management_qml 边界。
test_wifi_management_ui.py: pytest 回归入口，验证 wifi_management_ui 边界。
test_wifi_qml.py: pytest 回归入口，验证 wifi_qml 边界。
test_wifi_ui.py: pytest 回归入口，验证 wifi_ui 边界。
test_windows.py: pytest 回归入口，验证 windows 边界。
test_wireless_status.py: pytest 回归入口，验证 wireless_status 边界。
test_wireless_status_qml.py: pytest 回归入口，验证 wireless_status_qml 边界。
theme_qml_probe.py: 稳定布局后的跨窗口主题、字体与滚动保留探针。
timezone_device_probe.py: 独立进程探针，验证 timezone_device 流程。
ui_interaction_probe.py: 独立进程探针，验证 ui_interaction 流程。
video_subtitle_probe.py: 独立进程探针，验证 video_subtitle 流程。
wifi_device_probe.py: 独立进程探针，验证 wifi_device 流程。
wifi_management_device_probe.py: 独立进程探针，验证 wifi_management_device 流程。
wifi_management_qml_probe.py: 等待弹窗几何稳定，验证网络菜单边界、密码输入与显示和焦点恢复。
wifi_qml_probe.py: 独立进程探针，验证 wifi_qml 流程。
wireless_status_qml_probe.py: 独立进程探针，验证 wireless_status_qml 流程。

进程协议测试使用隔离前端，不连接运行中的游戏。
设备探针需单独确认会话与内容边界。

[PROTOCOL]: Update this header on change, then check AGENTS.md
