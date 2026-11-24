# Reader 默认霞鹜文楷屏幕阅读版

Reader 的 TXT、EPUB、MOBI 正文默认使用
LXGW WenKai Screen（霞鹜文楷屏幕阅读版）1.530。
PDF 保留文档自身的字形与排版。

字体沿用 src/udeck/fonts/LXGWWenKaiScreen.ttf。
它与上游 v1.530 发布文件的 SHA-256 一致：
abd13364163e3cd84372b333f2fdcee9efb848634668f1c0ce5788dcd059ee61。
上游来源与 SIL OFL 1.1 许可证随包保留。
见 [上游发布](https://github.com/lxgw/LxgwWenKai-Screen/releases/tag/v1.530)。

新增字体偏好键 wenkai，并设为缺省值。
无效或缺失的字体偏好回落到文楷。
已有的无衬线、衬线和等宽选择保持有效。
阅读布局菜单提供中英文文楷选项。
正文优先读取系统文楷，否则读取随包字体。
字体资源只在随机会话路径内开放固定文件名。
正文不依赖运行时下载或 Qt 界面字体注册。
未修改 Foliate 上游文件。

## 源码验证

修复前，默认偏好与字体资源回归分别失败。
修复后，四个专项文件共 61 项通过。
真实 WebEngine 检查三种格式的正文与 FontFace 加载状态。
检查翻页后字体、保存选择和再次启动后的选择。
字体原始哈希、资源路径隔离和本地化校验通过。
全源码 Ruff 和空白检查通过。
全量 CI 验证 139 个文件、2614 项。
2607 项通过，7 项环境跳过。
无失败、错误或超时。
见 [CI 45399488107](https://github.com/zhubby/uDeck/actions/runs/45399488107)。

## uConsole 安装与复验

设备为 uConsole CM4，Debian 13.5 arm64。
Reader 源码提交为 5474e66776b6952e13e50aa6e33da239a066947c。
该提交已推送 main，并覆盖到现有 1.0.4。
载荷来自干净提交，共替换 9 个文件。
529 个运行文件的 SHA-256 全部匹配。
构建身份为
b9184d71746630784d64b47083031e6e20882cd20fc265919d08baf13c95b861。
本轮未创建版本、标签或 Release。

系统字体安装到
/usr/local/share/fonts/truetype/udeck/LXGWWenKaiScreen.ttf。
同目录保留原始 SIL OFL 许可证。
刷新 Fontconfig 后，fc-match 命中该文件。
安装文件与随包字体、上游摘要完全一致。

用户原 Reader 字体为 serif，现按要求改为 wenkai。
修改前备份完整状态，只变更字体偏好。
Reader 正常保存并退出后，重新打开原 MOBI。
传给分页器的续读位置与保存值完全一致。
书籍元数据、内容源、书签、收藏和其他排版偏好保留。
原书籍与三格式测试截图均已复核。

安装版 WebEngine 验证 TXT、EPUB、MOBI。
三种格式的正文 CSS 均选择 LXGW WenKai Screen。
三种格式的 FontFace 状态均为 loaded。
翻页后仍使用文楷，保存的其他字体选择仍有效。
Reader 无 QML 错误，最终保持原文档打开。

五份全局配置与本轮备份完全一致。
Music、Browser、Emulator 及期间新增的 Video 保留进程身份。
监督器和合成器保留进程身份。
服务错误为空，dpkg 审计通过。

首轮校验误把 Reader 的父进程变化当成进程替换。
源码回退后，重新启动基线桌面并核对文件与进程。
修正部署工具的身份比较后重试成功。
比较 PID 与启动时间，允许父进程正常变化。
首轮失败与恢复证据均保留。
最终备份位于
/var/backups/udeck-reader-wenkai-1795525952308857086。

结构化摘要见 [实机记录](reader-wenkai-2026-11-24.json)。
原始证据位于 artifacts/reader-wenkai-20261124/。

[PROTOCOL]: Update this header on change, then check AGENTS.md
