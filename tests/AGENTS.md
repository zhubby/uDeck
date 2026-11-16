# tests/
> L2 | Parent: ../AGENTS.md

成员清单：

test_runtime_console_processes.py: proc 快照、资源聚合和 pidfd 终止身份回归。
test_runtime_console_apps.py: 轻量应用状态与原生存档退出回归。
test_runtime_console.py: 身份查询失败、应用聚合、详情和有序退出回归。
runtime_console_qml_probe.py: 单行尺寸、滚动悬停与详情鼠标按键的 QML 探针。
test_runtime_console_qml.py: Console 详情交互、中英文与双主题尺寸回归。

app_forwarding_probe.py: 独立进程探针，验证 app_forwarding 流程。
app_lazy_surface_probe.py: 独立进程探针，验证 app_lazy_surface 流程。
app_settings_device_probe.py: 独立进程探针，验证 app_settings_device 流程。
apps_games_probe.py: 独立进程探针，验证 apps_games 流程。
apps_ipc_probe.py: 独立进程探针，验证 apps_ipc 流程。
apps_native_probe.py: 独立进程探针，验证 apps_native 流程。
audio_qml_probe.py: 独立进程探针，验证 audio_qml 流程。
battery_qml_probe.py: 独立进程探针，验证 battery_qml 流程。
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
games_qml_probe.py: 独立进程探针，验证 games_qml 流程。
home_qml_probe.py: 独立进程探针，验证 home_qml 流程。
hotspot_device_probe.py: 独立进程探针，验证 hotspot_device 流程。
hotspot_nm_profile_probe.py: 独立进程探针，验证 hotspot_nm_profile 流程。
hotspot_qml_probe.py: 独立进程探针，验证 hotspot_qml 流程。
i18n_qml_probe.py: 独立进程探针，验证 i18n_qml 流程。
input_prompts_qml_probe.py: 独立进程探针，验证 input_prompts_qml 流程。
interface_sounds_qml_probe.py: 独立进程探针，验证 interface_sounds_qml 流程。
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
settings_qml_probe.py: 独立进程探针，验证 settings_qml 流程。
sharing_qml_probe.py: 独立进程探针，验证 sharing_qml 流程。
shortcuts_qml_probe.py: 独立进程探针，验证 shortcuts_qml 流程。
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
test_app_settings.py: pytest 回归入口，验证 app_settings 边界。
test_apps_core.py: pytest 回归入口，验证 apps_core 边界。
test_apps_native.py: pytest 回归入口，验证 apps_native 边界。
test_apps_review.py: 应用启动、游戏暂停确认与异步取消的回归测试。
test_apps_routing.py: 输入归属、会话恢复与原生命令窗口激活的回归测试。
test_apps_saves.py: pytest 回归入口，验证 apps_saves 边界。
test_audio.py: pytest 回归入口，验证 audio 边界。
test_audio_qml.py: pytest 回归入口，验证 audio_qml 边界。
test_backend.py: pytest 回归入口，验证 backend 边界。
test_battery.py: pytest 回归入口，验证 battery 边界。
test_battery_qml.py: pytest 回归入口，验证 battery_qml 边界。
test_browser_interactions.py: pytest 回归入口，验证 browser_interactions 边界。
test_cli.py: pytest 回归入口，验证 cli 边界。
test_compatibility.py: pytest 回归入口，验证 compatibility 边界。
test_console.py: pytest 回归入口，验证 console 边界。
test_console_qml.py: pytest 回归入口，验证 console_qml 边界。
test_core.py: pytest 回归入口，验证 core 边界。
test_cursor.py: pytest 回归入口，验证 cursor 边界。
test_directions.py: pytest 回归入口，验证 directions 边界。
test_emulator_engine.py: 真实 QProcess 协议回归，覆盖背压、通知、读档屏障与重启。
test_emulator_game_info.py: pytest 回归入口，验证 emulator_game_info 边界。
test_emulator_migration.py: pytest 回归入口，验证 emulator_migration 边界。
test_emulator_platforms.py: pytest 回归入口，验证 emulator_platforms 边界。
test_emulator_playlist_browser.py: pytest 回归入口，验证 emulator_playlist_browser 边界。
test_emulator_playlist_library.py: pytest 回归入口，验证 emulator_playlist_library 边界。
test_emulator_playlists.py: pytest 回归入口，验证 emulator_playlists 边界。
test_emulator_save_daemon.py: pytest 回归入口，验证 emulator_save_daemon 边界。
test_emulator_save_management.py: pytest 回归入口，验证 emulator_save_management 边界。
test_emulator_save_sync.py: pytest 回归入口，验证 emulator_save_sync 边界。
test_emulator_save_ui.py: pytest 回归入口，验证 emulator_save_ui 边界。
test_emulator_thumbnails.py: pytest 回归入口，验证 emulator_thumbnails 边界。
test_file_icons.py: pytest 回归入口，验证 file_icons 边界。
test_files_controller.py: pytest 回归入口，验证 files_controller 边界。
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
test_home.py: pytest 回归入口，验证 home 边界。
test_home_qml.py: pytest 回归入口，验证 home_qml 边界。
test_hotspot.py: pytest 回归入口，验证 hotspot 边界。
test_hotspot_qml.py: pytest 回归入口，验证 hotspot_qml 边界。
test_hotspot_ui.py: pytest 回归入口，验证 hotspot_ui 边界。
test_i18n.py: pytest 回归入口，验证 i18n 边界。
test_i18n_qml.py: pytest 回归入口，验证 i18n_qml 边界。
test_input.py: pytest 回归入口，验证 input 边界。
test_input_prompts.py: pytest 回归入口，验证 input_prompts 边界。
test_interface_sounds.py: pytest 回归入口，验证 interface_sounds 边界。
test_interface_sounds_qml.py: pytest 回归入口，验证 interface_sounds_qml 边界。
test_key_test.py: pytest 回归入口，验证 key_test 边界。
test_key_test_device.py: pytest 回归入口，验证 key_test_device 边界。
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
test_network_files_ui.py: pytest 回归入口，验证 network_files_ui 边界。
test_network_files_web.py: pytest 回归入口，验证 network_files_web 边界。
test_performance_tools.py: pytest 回归入口，验证 performance_tools 边界。
test_pointer.py: pytest 回归入口，验证 pointer 边界。
test_preflight.py: pytest 回归入口，验证 preflight 边界。
test_qml.py: pytest 回归入口，验证 qml 边界。
test_reader_layout.py: pytest 回归入口，验证 reader_layout 边界。
test_reader_mobi.py: pytest 回归入口，验证 reader_mobi 边界。
test_release.py: pytest 回归入口，验证 release 边界。
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
theme_qml_probe.py: 独立进程探针，验证 theme_qml 流程。
timezone_device_probe.py: 独立进程探针，验证 timezone_device 流程。
ui_interaction_probe.py: 独立进程探针，验证 ui_interaction 流程。
video_subtitle_probe.py: 独立进程探针，验证 video_subtitle 流程。
wifi_device_probe.py: 独立进程探针，验证 wifi_device 流程。
wifi_management_device_probe.py: 独立进程探针，验证 wifi_management_device 流程。
wifi_management_qml_probe.py: 独立进程探针，验证 wifi_management_qml 流程。
wifi_qml_probe.py: 独立进程探针，验证 wifi_qml 流程。
wireless_status_qml_probe.py: 独立进程探针，验证 wireless_status_qml 流程。

进程协议测试使用隔离前端，不连接运行中的游戏。
设备探针需单独确认会话与内容边界。

[PROTOCOL]: Update this header on change, then check AGENTS.md
