# 未提交改动审查与交付记录（2026-11-12）

## 结论与范围

本次检查 `main` 上以 `c6e41b7871ece599b7666154a35cea549cc4a689` 为基线的全部 38 个未提交文件，包括 27 个已跟踪改动和 11 个新增文件。按主线程顺序复核输入框及动作路由、媒体指针与布局、文件任务队列、HTTP 边界、上传取消、配置持久化、服务关闭、网页导航与恢复，以及对应测试和历史审计记录。

发现并补齐 1 处目录恢复遗漏；修复后没有发现需要继续实现的代码项。连同本记录，交付文件共 39 个。既有审计文档中的“未提交、未推送”描述保留其当轮历史含义；本次是在这些修复之上统一验证并提交交付。

## 本次补齐的问题

| 级别 | 文件 | 触发与影响 | 修复与证据 |
| --- | --- | --- | --- |
| P2 | `src/udeck/network_files/web/app.js` | 通过 `/#Documents` 打开共享子目录，首次配置请求返回 503；恢复连接时页面加载根目录，地址栏仍指向子目录 | 首次请求前读取 URL fragment，使恢复流程保留目标目录。新增真实 HTTP / Qt WebEngine 回归，验证子目录文件、面包屑与地址一致，且不展示根目录文件 |

修复前，根目录恢复用例通过，新增子目录用例稳定失败：`1 failed, 1 passed`，失败信息为 `Reconnection opened the root instead of the linked folder`。修复后整个网页交互模块 `12 passed`，保留既有 11 项回归。

## 最终验证

运行环境为 macOS、Python 3.13.18、PySide6 6.8.3，Qt offscreen / software / Basic。使用既有独立环境 `/tmp/udeck-ui-audit-20261111-venv`，没有修改项目原有 `.venv`。

| 检查 | 结果 |
| --- | --- |
| 全仓库 pytest | 共 1479 项：**1474 passed、5 skipped、0 failed、13 warnings，773.43 秒**；进程退出 0 |
| 网络文件回归 | 51 项全部通过：基础 3、客户端 2、边界 22、生命周期 10、本机菜单 2、网页 12 |
| 界面交互回归 | 68 项全部通过 |
| Ruff | `ruff check src tests tools` 通过 |
| JavaScript | `node --check src/udeck/network_files/web/app.js` 通过 |
| 依赖锁 | `uv lock --check` 通过 |
| Git 空白检查 | `git diff --check` 通过 |
| 构建 | `uv build` 成功生成 wheel 和源码包；两份产物中的全部 18 个改动产品源文件均与工作区逐字节一致 |
| 源码一致性 | 最终全量测试前后，全部 38 个审查文件的 SHA-256 一致；之后仅新增本记录 |

5 项跳过分别为 2 项依赖 Linux session bus 的应用转发测试，以及 3 项依赖原生终端插件的 PTY、会话生命周期、ANSI / Nerd 字形测试。13 条警告均来自 `dbus_next` 对 Python 弃用装饰器的使用；没有新增跳过或屏蔽警告。

首次启动的全量运行在发现子目录恢复遗漏后主动用 SIGINT 结束，退出码 2，原始日志保留。最终验收使用修复后的独立完整运行，没有自动重试或用专项通过替代全量结果。

复现最终完整验证：

```sh
rtk proxy env QT_QPA_PLATFORM=offscreen QT_QUICK_BACKEND=software \
QT_QUICK_CONTROLS_STYLE=Basic PYTHONPATH=src \
/tmp/udeck-ui-audit-20261111-venv/bin/python -m pytest -q \
  --junitxml=artifacts/uncommitted-delivery-2026-11-12/full-suite-final.xml
```

## 提交分组与证据

按文件分成三笔提交：

1. 界面交互：输入框身份与组合态、确认键连发、Browser 指针、视频拖动生命周期、音乐布局、GUI 文件任务反馈，以及对应回归和两轮界面记录。
2. 网络文件：上传取消与资源清理、共享持久化和关闭、目标目录选择、断线恢复、首次连接失败后的子目录恢复，以及对应回归和两轮网络记录。
3. 测试稳定性：图片异步加载、热点失败与恢复夹具、原生事件等待、时钟跨分钟，以及最终修复记录与本次交付记录。

证据保存在 ignored 目录 `artifacts/uncommitted-delivery-2026-11-12/`：`initial-state.json`、`verified-source-state.json`、`review.json`、`reconnect-before.*`、`web-after.*`、`full-suite.*`、`full-suite-final.*`、`verification-summary.json`、`static-checks.json`、`build.log`、`package-verification.json` 和 `commit-groups.json`。历史审计证据保持原样。

## 验收边界

本次完成本地软件审查、修复、自动化验证和构建。真实实体按键、Wayland / fcitx、硬件解码与音频、物理网卡 / VPN 切换、设备 systemd 集成、Debian 包安装和整机重启仍属于实机验收范围；本地通过结果不替代这些验收。既有 linked worktree 和参考档案保持原样。
