# Bootstrap 设置图标

来源：[Bootstrap Icons](https://icons.getbootstrap.com/) · [官方仓库](https://github.com/twbs/icons) · `bootstrap-icons` **1.13.2** · **MIT**。完整许可和来源署名分别见 `LICENSE.txt` 与 `NOTICE`。

| 设置项 | 图标 |
| --- | --- |
| 音量 / 静音 | `volume-up-fill.svg` / `volume-mute-fill.svg` |
| 屏幕亮度 | `brightness-high-fill.svg` |
| 音频输出 / 麦克风 | `headphones.svg` / `mic-fill.svg` |
| Wi-Fi 与热点 / 蓝牙 | `wifi.svg` / `bluetooth.svg` |
| 电池 | `battery-half.svg` |
| 按键与控制器 | `controller.svg` |
| 按键测试 | `keyboard-fill.svg` |
| 快捷键绑定 | `command.svg` |
| 语言 / 主题 / 时区 | `translate.svg` / `palette-fill.svg` / `clock-fill.svg` |
| 锁屏 / 熄屏 | `lock-fill.svg` / `display.svg` |
| 注销 / 重启 / 关机 | `box-arrow-right.svg` / `arrow-clockwise.svg` / `power.svg` |
| 子菜单操作与状态 | 同套资源中的连接、扫描、编辑、信息、警告等图形 |

33 个 SVG 来自与 C 方案相同的固定版本官方 npm 归档，文件字节保持原样。最初确认的手柄、键盘和快捷键图形不变，系统设置列表、快捷设置以及相关子菜单统一使用这套资源。图标映射集中在 `menu_icons.py`，其他页面继续使用原来的桌面图标逻辑。

`udeck-setting:` 标识优先读取内置资源，不受桌面图标主题影响；绘制时用 QML `ThemePalette.artText` 替换 `currentColor`，颜色随主题更新。沿用现有图标尺寸、文字对齐、选中反馈及禁用状态。

归档：[bootstrap-icons-1.13.2.tgz](https://registry.npmjs.org/bootstrap-icons/-/bootstrap-icons-1.13.2.tgz)，SHA-256：`7b5960145e1ab14a49a117f96a9e5a54a94fdf07f21e302d9e4f88d73dd19f9c`。`manifest.json` 保存归档及每个原始文件的校验和与字节数；许可与资源随软件包离线分发。
