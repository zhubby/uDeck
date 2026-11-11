# 系统与应用设置图标

## 行为与范围

- Music、Video、Browser、Reader、Emulator 的设置菜单移除“语言”。Terminal 原本没有该入口。
- 全局语言继续由系统设置管理；应用继续跟随系统语言和主题。
- 系统设置列表、快捷设置及各级菜单显示与选项含义对应的图标。状态刷新后继续保留图标、当前选项和键盘导航。
- 应用设置及其子菜单使用相同的图标接口，覆盖 Reader 字体/字号/行距/宽度/背景、Browser 缩放/交互模式、媒体输出、Emulator 目录/核心管理及 Terminal 字号。

## 图标来源与呈现

共享 `udeck.icons.IconProvider` 保留既有的 `QIcon.fromTheme` 优先级，系统主题提供合适图标时直接使用。主题缺少对应图标时，沿用系统原有的圆角底色、暖色线条、线宽和绘制方式，补齐相应的矢量图形。本次没有引入外部图标库或第三方素材。

实机 `qt6ct.conf` 配置的主题为 PiXtrix，但当前 uDeck 会话的 Qt 查询返回 hicolor，常见设置图标未能命中主题，因此本次同时验证了自带绘制图标的效果。没有修改 Qt 系统主题配置。

系统选项根据稳定的 action/id 分配图标，不依赖翻译后的文字。应用可为选项明确指定图标，子菜单中的数值或字体选择沿用对应设置类别的图标。

## 本地验证

- 先复现 6 项失败：五个应用仍显示语言入口，系统语言子菜单缺少图标；实现后 6 项全部通过。
- 菜单范围、应用行为、Terminal、文件图标与主题回归：183 passed。
- Wi-Fi/热点/音频及 Emulator 管理回归：92 passed。13 条警告来自既有 dbus-next 对 Python 3.13 弃用接口的使用。
- 系统设置、主题切换、Terminal、原生应用及 Emulator QML 回归：37 passed。
- 图标界面矩阵：28 组、152 次截图。覆盖系统及六个应用，1280×720 / 960×600、英文 / 简体中文、Classic / Dark。每次检查图标加载状态、显示边界和 QML 错误，并实际执行缩放、字号调整、菜单进入/返回及滚动。
- Ruff、`git diff --check` 通过。
- 最终检查将图标补充限定于系统设置菜单，相关菜单/网络/音频回归 64 passed，系统 4 组界面矩阵再次通过。

本地证据位于 `artifacts/settings-icons-20261111/`。截图使用隔离数据，系统控制由 MockBackend 提供；不代表实际更改了 Wi-Fi、音频或设备电源。

## 设备端验证

- uConsole：`zhubby@192.168.11.59`，Qt/PySide6 6.8.2。
- 临时源码目录：`~/udeck-settings-icons-20261111-01/`。使用 `QT_QPA_PLATFORM=offscreen`、软件渲染及临时配置运行，未安装到系统目录，未重启当前桌面或正式应用。
- 系统、Music、Video、Browser、Reader、Emulator、Terminal 共 7 组 / 38 次渲染通过，所有已显示图标均为 Ready，QML 错误为空。
- 最终系统菜单检查再次通过，并核对设备临时目录中 119 个 Python/QML 源码文件与本地 SHA256 清单一致。
- 设备报告与截图保存在 `artifacts/settings-icons-20261111/device/results/`，对比预览为 `artifacts/settings-icons-20261111/preview.png`。

这些是设备端隔离渲染与菜单行为证据，当前实机正式安装版本尚未替换。

## 行高约束追加验证

根据确认的设计约束，系统列表、系统菜单、应用设置与 Terminal 设置的图标高度改为相邻文字块的实际高度，标题、副说明及自动换行均计入。图标维持正方形，与文字块顶部、底部对齐；行内留白独立计算，弹层与设置行随内容高度调整。

设计约束记录在 `docs/design/system-settings.md`。图形检查从实际 Text 几何计算文字边界，验证图标高度、顶部对齐及正方形比例，未依赖生产尺寸表达式计算预期值。修改前复现 Reader 图标为 32px、文字为 26px，修改后通过。

- 本地 28 组 / 152 次渲染，检查 686 个已显示图标；包含标题和副说明组成的两行文字，以及实际自动换行，高度误差为 0。
- 设备端 7 组 / 38 次渲染，检查 185 个已显示图标，高度误差为 0，QML 错误为空。
- 设置、主题、Terminal、Wi-Fi、热点和音频界面回归 43 passed；Ruff、`git diff --check` 通过。
- 设备验证继续使用临时源码、离屏渲染和隔离配置，未替换正式安装。
- 追加证据保存于 `artifacts/settings-icons-20261111/line-height/`。

## 合入 main 前的独立快照验证

从 Git 暂存区导出只含设置改动的源码快照，排除尚未提交的 MOBI、首页 Browser 入口和浏览器交互修改，验证本次提交可独立运行。

- 22 个相关测试文件共 341 项。初次 337 passed、2 failed、2 skipped；两项 Reader 布局测试仍按二元菜单项解包，调整为兼容附加图标字段后，Reader 布局 4 项复测全部通过。累计 339 项通过，2 项 Linux 会话总线测试在 macOS 跳过。
- 系统及六个应用共 7 组、38 次实际 Qt 渲染，检查 150 个已显示图标，高度误差为 0，QML 错误为空。
- 暂存源码及测试的 Ruff、`git diff --cached --check` 通过。
- 验证报告、原始测试 XML 及截图保存于 `artifacts/settings-icons-20261111/main-integration/`。
