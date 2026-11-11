# 系统快捷键

系统设置的「快捷键绑定 / Shortcut bindings」管理 23 个系统全局动作。按桌面导航、窗口、截屏、电源、声音和亮度分组，包含未绑定动作；每项显示当前组合键与默认、自定义、未绑定及功能不可用状态。应用内部快捷键、ABXY 校准和固件 Fn 功能仍在各自位置管理。

选择动作后可录制已有组合键、添加另一组组合键、清除全部绑定或恢复该项默认。分组首页提供恢复全部默认。每次确认后立即应用并保存，当前菜单与焦点保留。组合键冲突会列出占用动作；默认取消，明确确认后仅转移冲突的那一组，其他别名保留。

## 默认按键

| 动作 | 默认组合键 |
| --- | --- |
| 打开控制台 | Ctrl+Shift+Esc |
| 返回主页 | Ctrl+Alt+Esc |
| 打开运行中列表 | Ctrl+Alt+Tab |
| 打开应用列表 | Ctrl+Alt+A |
| 打开文件管理 | Ctrl+Alt+F |
| 打开系统设置 | Ctrl+Alt+, |
| 打开快捷设置 | Ctrl+Alt+S、电源键 |
| 打开终端 | Ctrl+Alt+T |
| 全屏截屏 | Ctrl+Alt+P、PrintScreen |
| 下一个 / 上一个窗口 | Alt+Tab / Alt+Shift+Tab |
| 关闭当前窗口 | Alt+F4 |
| 暂停模拟器 | Ctrl+Alt+M |
| 锁屏 / 熄屏 | Ctrl+Alt+L / Ctrl+Alt+B |
| 音量增加 / 减少 / 静音 | 对应系统媒体键 |
| 亮度增加 / 减少 | 对应系统亮度键 |
| 注销 / 重启 / 关机 | 未绑定，可自行设置 |

注销、重启、关机只打开现有确认框，默认选中取消。注销沿用现有系统后端的独立 uDeck 会话限制。音量与亮度通过现有系统后端调整，每次 5%，不会调用额外的 wpctl 或 rpi-backlight 命令。

## 录制

录制使用独立窗口；labwc 通过仅匹配该窗口的 F23 动作执行 `ToggleKeybinds`。隔离确认后才接受输入，Alt+F4、终端或截屏等现有组合键只被录制。释放全部按键后按 Enter、A 或确认按钮保存，Esc、B 或取消按钮取消。失焦、关闭和 15 秒超时会销毁窗口并恢复快捷键；失焦时不抢回外部窗口。

纯修饰键、未搭配 Ctrl/Alt/Super 的字符与导航键、内部 F23/F24 及多段组合键会被拒绝。系统媒体键、PrintScreen 和 F1–F22 可以单独绑定。

## 配置与接管

配置独立保存到 `${XDG_CONFIG_HOME:-~/.config}/udeck/shortcuts.json`，格式版本为 1。缺少动作表示默认，显式空数组表示禁用；重新生成会话配置和切换手柄模式都会使用该文件。

```json
{"version": 1, "bindings": {"console": ["C-A-q"], "screenshot": []}}
```

这表示控制台改为 Ctrl+Alt+Q、截屏快捷键被禁用，其余动作采用默认。手工编辑须保证键名有效、无跨动作冲突；非法文件保留原样并显示错误，不静默重置。

首次在真实图形会话启用时，核对当前用户的 labwc 进程及其配置目录；原始 rc.xml 字节以 0600 权限备份至 `${XDG_STATE_HOME:-~/.local/state}/udeck/shortcuts/labwc-before-udeck-<sha256>.xml`。替换所有 keyboard keybind 并移除 keyboard default 继承，保留主题、鼠标、窗口规则、命名空间、注释和文件权限。独立 uDeck 会话和原 labwc 桌面共用此逻辑，包括真实窗口化运行；安装软件包和 `--mock` 预览不会接管桌面。

编辑通过原子替换 XML、向目标进程发送重载、F24 配置代次回执及磁盘内容核对确认，成功后再保存 JSON。重载超时或持久化失败会恢复本次事务前的 XML 与绑定；外部同时修改的文件不会被回滚覆盖。方向隔离请求与改键串行，不覆盖用户自定义。启动失败只尝试一次，可通过 `udeckctl bind-console` 显式重试；该兼容命令输出 pending/applied/error，不在没有运行中壳时修改离线配置。`udeckctl doctor --json` 的 shortcuts 字段提供状态、当前绑定和本次接管备份路径。

要恢复原桌面快捷键，先退出 uDeck，再把匹配的备份复制回实际 labwc 配置目录的 rc.xml，然后重载对应 labwc。重新启动 uDeck 会再次按 shortcuts.json 接管；单纯恢复全部默认仍会使用 uDeck 默认表。以上操作不修改默认登录项或自动登录设置。

## 截屏与命令

`udeckctl screenshot` 调用 grim 捕获真实 Wayland 桌面，解码确认 PNG 后，以唯一文件名保存到 XDG 图片目录的 Screenshots 子目录，成功提示完整路径。失败清理临时文件；`--mock` 只显示预览提示。Debian 运行依赖包含 grim。

新增固定命令：`apps`、`files`、`settings`、`screenshot`、`blank`、`logout`、`reboot`、`poweroff`，媒体键使用 `volume-up`、`volume-down`、`mute`、`brightness-up`、`brightness-down`。已有 `home`、`switcher`、`console`、`quick-settings`、`lock`、`input-mode`、`input-ack` 等保持兼容。

## 验证

- 单元回归覆盖归一化、Qt 媒体键、多绑定、清除/恢复、精确冲突转移、持久化、XML 命名空间/多 keyboard 节点、原始字节备份、失败回滚、外部编辑保护与模式切换。
- Qt 界面矩阵覆盖中英 × 两主题 × 1280×720/960×600，检查面板与录制区域边界、真实键事件、取消、超时、失焦及冲突确认；输出路径见 `artifacts/system-shortcuts/`。
- `dbus-run-session -- python3 tools/verify-system-shortcuts.py` 启动独立真实 labwc，使用分别启动的 Wayland 和 Xwayland 客户端与 udeckctl 进程，检查全局默认、改键、旧键失效、焦点恢复、录制隔离、15 秒超时、模式切换和配置服务重建后的持久化。grim 真实桌面 PNG 检查尺寸及独立客户端画面。电源只检查确认流程。

自动化不代表实体键/Fn、设备重新登录或重启、显示硬件与实际电源操作验收；这些保留为实机检查。验证环境的 labwc 版本与回归、Debian 打包结果记录在同目录验证报告中。
