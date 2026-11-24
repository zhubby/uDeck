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

实机安装与持久化复验另行记录。
原始证据位于 artifacts/reader-wenkai-20261124/。

[PROTOCOL]: Update this header on change, then check AGENTS.md
