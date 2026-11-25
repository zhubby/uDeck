# 语言、主题与字体

首次使用默认英文，支持 English / 简体中文。
系统设置和快捷设置修改同一语言与主题偏好。
界面翻译来自 `src/udeck/locales/`，内容标题、文件名和 URL 保留原文。
保存失败保留当前值；跨进程写入保留其他进程刚更新的偏好。

Classic 与 Dark 由 `ThemePalette.qml` 提供语义颜色。
`preferences.theme` 只接受 `classic` / `dark`，非法值回落到 Classic。
原生应用和 Terminal 同步全局偏好，不重建内容与会话。
主题改变保留焦点、滚动、输入草稿、播放器、文档和 PTY。
网页内容、视频与游戏画面不强制重新配色。
Reader 正文布局和 Terminal ANSI 色遵循各自契约。

英文界面使用 Saira Semi Condensed，中文使用 LXGW WenKai Screen。
字体随包提供，缺字回落到系统字体。
Reader 默认正文使用文楷，PDF 保留原文档字形。
Terminal 使用等宽正文和 Nerd 图标，见[终端指南](../udeck/terminal.md)。

焦点、选中、播放、错误和禁用使用独立语义。
错误必须有文字，必要边界不只依赖透明度。
正文对比度目标至少 4.5:1，焦点与必要边界至少 3:1。
固定图标使用离线资源；来源、版本、哈希和许可证随资源保留。
不能用 Emoji 替代文件、设置或按键图标。

产品标识见[品牌规范](branding/README.md)，
按键布局见[按键提示](input-prompts.md)，
连续过渡见[动效规范](../motion/README.md)。
验证覆盖双语言、双主题、1280×720 和 960×600。
自动截图不能代替实机屏幕观感和物理输入验收。

[PROTOCOL]: Update this header on change, then check AGENTS.md
