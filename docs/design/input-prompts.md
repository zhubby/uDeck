# uDeck 按键图标规范

适用于启动器、系统设置与弹层、五个原生应用、独立终端和应用交互原型。中英文、经典与黑暗主题使用同一组按键图标；动作文字按语言切换。英文界面字体为 Saira Semi Condensed，中文界面为 LXGW WenKai Screen，图标内部的字母保留素材原样。

## 素材来源与组合

按键提示统一使用 [Kenney Input Prompts](https://kenney.nl/assets/input-prompts) 的 **Keyboard & Mouse** 与 **Nintendo Gamecube** 两组。手柄图例使用 GameCube 的 A、B、X、Y、L、R；键盘快捷键和鼠标操作使用 Keyboard & Mouse。不得混入其他主机平台的字母排列，也不再手绘圆圈字母或用 Emoji 充当按键图标。

使用原始 `Double` PNG（128×128、透明画布）。A 为原始绿色、B 为原始红色，X/Y 和 L/R 为原始实心白色。颜色用于识别按键；焦点、选中、错误与禁用状态仍由所属控件和动作文字表达，不把 A 的绿色当成当前焦点。

下载归档为 `kenney_input-prompts_1.5.zip`，原始许可标为 `Input Prompts (1.5A)`，许可为 **CC0-1.0**。项目保留原始 `License.txt`，并在 `src/udeck/assets/input-prompts/manifest.json` 记录归档和各文件的 SHA-256。资源随安装包离线分发，原型使用相同文件的副本，测试校验两者一致。

## 图标与操作映射

GameCube 图例表示 uDeck 的逻辑按钮，按已校准的物理输入映射执行；图标不表示设备接入了 GameCube 手柄。普通键盘的 A/B/X/Y 字母继续用于输入文字。

| 输入 | 素材文件（省略 `.png`） | 界面用途 |
| --- | --- | --- |
| A | `gamecube_button_color_a` | 确认、打开、执行当前控件；动作随所在页面明确标注 |
| B | `gamecube_button_color_b` | 返回上一层、取消当前输入；游戏运行时由模拟器接收 |
| X | `gamecube_button_x` | 当前项操作、更多 |
| Y | `gamecube_button_y` | 应用或快捷设置 |
| L / R | `gamecube_trigger_l` / `gamecube_trigger_r` | 分类、页码、曲目或终端会话；旁边写明当前用途 |
| 方向键 | `keyboard_arrows` | 选择、定位、扩选、PDF 平移；依上下文标注 |
| Enter / Esc | `keyboard_enter` / `keyboard_escape` | 确认与返回/取消；输入框保留原生文字编辑 |
| Ctrl / Alt / Shift | `keyboard_ctrl` / `keyboard_alt` / `keyboard_shift` | 组合键的修饰键，按实际顺序显示 |
| F2 / F3 | `keyboard_f2` / `keyboard_f3` | 支持这些键的界面中，作为 X / Y 的键盘入口 |
| PageUp / PageDown | `keyboard_page_up` / `keyboard_page_down` | 支持这些键的分类或会话切换入口 |
| 鼠标左键 / 右键 | `mouse_left` / `mouse_right` | 只标注该页面实际支持的鼠标操作，不默认等同 A / B |
| 鼠标滚轮 | `mouse_scroll` | 网页滚动等实际滚轮操作 |
| 鼠标模式 | `mouse` | 浏览器虚拟指针模式标识 |

`Ctrl + Alt + Esc` 表示返回桌面；`Ctrl + Alt + M` 表示游戏暂停菜单；`Ctrl + Shift + T` 表示终端新建会话。这些组合键分别使用对应修饰键与 `keyboard_escape`、`keyboard_m`、`keyboard_t`。浏览器地址入口使用 `Ctrl + L`，其中 L 使用 `keyboard_l`，不可误用 GameCube L。

只展示已实现的输入。Start、Z、C Stick 等其他素材没有映射时不出现在产品提示中；图标切换不修改输入路由、校准或模拟器按键。

## 排列、尺寸与文案

- 常驻底栏采用“图标＋动作文字”，按钮型入口在文字前使用相同图标。A/B/X/Y 的排列固定，不能按 GameCube 物理位置重新排列现有菜单。
- 主底栏图标 36px，普通提示和弹层 32px，紧凑提示 28px；终端标题栏可用 24px。保留完整透明画布和原始比例，禁止拉伸、裁切、描边或重绘字母。
- 同一提示内部间距 6px，不同动作组间距 16–24px。`+` 表示必须同时按下，`/` 表示同一动作的可替代按键，不能省略分隔符。
- `A / Enter 确认` 和 `B / Esc 返回` 分别作为完整一组；组合键不能拆成两行。空间不足时按动作组换行，不让提示覆盖内容、其他提示或屏幕边缘。
- 动作文字使用当前字体与语义文字颜色，优先用“确认、返回、翻页、分类、点击”等短文案。长篇操作说明可保留文本快捷键，常驻操作图例必须使用共享图标。
- 图标不作为可点击区域的大小标准。按钮、菜单和可触控入口沿用现有控件边界；禁用态统一作用于整组图标与文字，保留原因说明。

## 组件与无障碍

QML 使用共享 `InputIcon`、`InputPrompt` 和 `InputHints`。调用方传入语言对应的 `fontFamily`、语义 `textColor`、动作文字和图标文件名；`InputHints` 按完整动作组换行。资源路径只指向本地安装目录。

```qml
InputPrompt {
    keys: ["gamecube_button_color_a", "/", "keyboard_enter"]
    label: window.tr("Confirm")
    fontFamily: window.fontFamily
    textColor: window.colors.muted
}
```

屏幕阅读器读取包含按键名称与动作的完整提示，避免逐张图片重复朗读。可交互按钮仍以实际动作为可访问名称；网页原型的图标提供按键名称作为替代文字，按钮保留完整 `aria-label`。图标、动作文字和焦点边框共同表达操作，不能只靠颜色。

## 验收

检查 1280×720、960×600、中英文和两套主题：图标加载完整，图片来源属于指定两组，保留比例；底栏、确认、密码/文字输入、浏览器指针和终端历史提示没有越界。验证方向键、确认、逐层返回和原生文字输入继续工作，语言与主题切换保留页面、焦点、草稿和会话。wheel 与 Debian 包须包含 PNG、许可和清单，新增图标后同步原型副本并运行资源校验。

实现与验证记录见 [Input Prompts 交付记录](../udeck/input-prompts-2026-11-07.md)。
