# Reader 文件关联验收

Files 使用 Reader 的共享格式表。
TXT、PDF、EPUB、MOBI 全部进入内置 Reader。
后缀不区分大小写。
Enter、菜单 Open、预览确认共用同一条路由。
文本预览保留正文，再次确认进入 Reader。
未安装 Reader 时显示内部说明。
目录、回收站和符号链接继续使用原有守卫。

原实现按文件分类选择 Reader。
TXT 属于文本分类，因此未进入 Reader。
本次先查询 `EXTENSIONS["reader"]`，消除分类遗漏。
系统默认文件关联保持原值。

## 源码与专项回归

实现提交为 `e72cd15d896de7f03e0a2a9fb2c5b5a7a5e8b978`。
该提交已推送 main。
回归直接从共享格式表生成四格式用例。
覆盖大小写、Enter、菜单 Open 和预览确认。
系统处理器和桌面启动入口设为禁止调用。

修复前，专项有 7 项失败、85 项通过。
失败均指向 TXT 缺少 Reader 关联。
修复后，四个文件共 126 项通过。
无失败、错误、跳过或超时。
Ruff、空白检查与独立代码审查通过。
早期失败和最终通过日志分别保留。

完整 CI 的 138 个文件收集 2161 项。
2154 项通过，7 项因工具或会话依赖跳过。
无失败、错误或超时。
记录见 [CI 45353821268](https://github.com/zhubby/uDeck/actions/runs/45353821268)。

此前纯文档提交 `f3ec9cb` 的 CI 有两项失败。
一项在监督器测试中读到尚未写入的 PID 文件。
另一项缩略图测试收到 7 次请求，预期 6 次。
后者的产品完成和重试状态断言通过。
原始日志不足以证明额外请求的唯一原因。
本轮上述两项均通过，对应源码和测试未修改。
旧失败与本轮完整通过证据分别保留。

## uConsole 部署

设备为 uConsole CM4，Debian 13 arm64。
在现有 1.0.4 上定向覆盖源码。
本轮没有创建版本、标签或 Release。
冻结来源为干净提交的 `git archive`。
冻结清单包含 1479 个文件。
运行文件共 528 个，逐项核对 SHA-256。
替换 `file_controller.py` 和 `_build_identity.py`。
仅重启桌面，保留 compositor、supervisor 和现有应用。

构建身份为
`fb8dd9b4ddd70f5b51d603ba0dba1c3529d6058b7369043cd66a01665e0addde`。
原始源码和五份配置备份于
`/var/backups/udeck-reader-associations-1795508457352913625`。

## 正式 Wayland 会话验收

使用远程虚拟键盘操作真实安装界面。
没有向产品注入测试接口。
四格式各执行冷 Enter 和暖菜单 Open，共 8 次。
八次均确认 Reader 就绪、路径正确、正文可见。
新 Reader 的构建身份与部署清单一致。
暖打开复用同一 PID 和启动身份。
PDF 正确显示一页。
TXT、EPUB、MOBI 显示原创中英文正文。
八张正文截图逐张检查，并生成汇总图。
MOBI 使用原创、无 DRM 的 PalmDOC MOBI6。
此用例不证明所有 Kindle 格式兼容。

Wayland 窗口事件未出现新增外部窗口。
25 毫秒采样未出现已知默认处理程序。
此观察不等同内核级进程执行追踪。
四个测试 Reader 均正常退出。
Music、Browser、Emulator 的原进程身份保持一致。

## 恢复与边界

Reader 的 JSON 和索引恢复原始字节、属主和权限。
全局配置仅出现最近打开记录变化。
恢复该记录后，重启桌面并核对五份配置。
五份配置的字节、属主和权限与备份一致。
另四份未变化的配置只校验，不重写。
最终 Home 前台，输入映射、抓取和快捷键正常。
服务错误为空，`dpkg --audit` 无输出。

会话 journal 未发现 Python Traceback 或 QML 错误。
日志包含 labwc 窗口几何和 Xwayland 授权消息。
原始日志保留，不能据此宣称全部日志无错误。
本轮没有执行人工物理按键验收。

结构化汇总见 [验收摘要](reader-file-associations-2026-11-24.json)。
本地原始证据位于 `artifacts/reader-associations-20261124/`。
专项证据位于 `artifacts/reader-routing-20261124/`。
设备原始证据位于 `/var/tmp/udeck-reader-associations-20261124/`。

[PROTOCOL]: Update this header on change, then check AGENTS.md
