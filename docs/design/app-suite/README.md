# 应用套件设计

当前套件包含 Music、Video、Browser、Reader 和 Emulator。
Terminal 的交互契约单独见[Terminal 指南](../../udeck/terminal.md)。
这些应用已使用原生 PySide6 / Qt Quick 实现。
本目录描述现行产品规则，运行入口见[应用说明](../../apps/README.md)。

## 共同设计

目标为 1280×720 横屏，960×600 保留紧凑布局。
内容库采用应用标识、集合标签、内容区和底部按键提示。
焦点、当前集合和正在播放使用独立标记。
列表、网格和弹层随焦点滚动，刷新后按稳定身份恢复选择。
选中长标题的阅读动效见[动效规范](../../motion/README.md)。

方向键选择，A 确认、B 返回、X 操作、Y 设置、L/R 切换集合。
文字输入、网页和游戏分别拥有自己的输入边界。
普通键盘字母不转换为游戏按钮。
按键素材及提示遵循[全局规范](../input-prompts.md)。

默认英文，支持简体中文与 Classic/Dark 主题。
切换只更新界面，不重建播放器、网页、文档或 PTY。
文件名、内容标题、URL 和游戏原名保留原文。

## 应用职责

| 应用 | 内容与主路径 | 连续性 |
| --- | --- | --- |
| Music | 专辑、曲目、队列、文件夹与播放 | 返回库继续播放，退出确认 |
| Video | 继续观看、视频库、字幕与章节 | 恢复确认，返回暂停并保存位置 |
| Browser | 标签、地址、历史、书签与网页 | 各标签保留页面与交互模式 |
| Reader | 书库、PDF 与重排文档 | 保存逻辑位置，布局改变保持锚点 |
| Emulator | 列表、平台、核心与游戏 | 游戏输入释放，暂停和存档受控 |

- [交互规范](interaction-spec.md)：输入、主路径、确认和异常。
- [原生架构](native-integration.md)：当前引擎、状态与安全边界。
- [系统设置](../system-settings.md)：单行设置、状态、焦点和诊断。
- [验证规范](../../udeck/validation.md)：源码、安装与物理验收的区分。

[PROTOCOL]: Update this header on change, then check AGENTS.md
