# 网络文件功能测试与修复

日期：2026-11-12。范围为 Files 的“网络访问”功能，包括本机设置菜单、浏览器文件管理、HTTP 传输边界与服务生命周期。

本轮在 macOS 上使用隔离共享目录、配置、数据目录和独立 Chromium 会话测试。服务只监听 `127.0.0.1:18787`，未使用真实用户文件或用户回收站，未部署到设备，也未提交或推送。

## 发现并修复的问题

| 问题 | 复现与影响 | 修复 |
| --- | --- | --- |
| 浏览器前进/后退残留搜索 | 在子目录搜索后返回共享根目录，旧关键词继续过滤新目录，文件看似消失 | 历史导航复用目录切换流程，清空搜索、选择与旧列表，并撤销尚未执行的搜索计时器 |
| 慢网下复制/移动选错目标 | 点击目标目录后立即确认，尚未返回的目录请求使操作继续使用之前的目录；较早请求也可能覆盖较新的选择 | 加载期间禁用确认，Enter 同样不能绕过；用请求序号忽略过期响应 |
| 隐藏目录无法作为目标 | 主列表打开“显示隐藏文件”后，目标选择器仍过滤隐藏目录 | 目标选择器遵循同一隐藏文件设置 |
| 第 501 个目标目录不可达 | 目标选择器只列出前 500 项，没有继续进入后续目录的入口 | 增加按需“加载更多”，使用实际偏移量请求下一页；文件排在目录之后，不继续加载只有文件的页面 |
| 取消上传仍提交文件 | 上传已收完，正在等待变更锁时取消，服务仍返回成功；替换模式会覆盖原文件 | 将取消事件传到原子提交阶段，在同步与目录校验之后、正式提交之前再次检查；取消时清理临时文件并保留原文件 |
| 异常 Host 导致服务错误 | `Host: [` 或 `Host: [invalid]` 使地址解析抛异常，接口返回 500 | 地址解析失败按非法地址处理，返回 JSON 403 |

修改集中在 `src/udeck/network_files/server.py`、`filesystem.py` 和 `web/app.js`，不改变 HTTP API。

## 回归证据

- 修改前既有网络文件测试：**22 passed，2.42 秒**。
- 先新增回归再修复：首组 **8 failed**，分别覆盖异常 Host、三种上传策略的取消、历史导航、慢网目标确认和隐藏目标；目标分页另有 **1 failed** 的独立复现。
- 最终相关回归：**318 passed，159.23 秒，0 failed / 0 errors / 0 skipped**。
- 其中网络文件测试 **35 项全部通过**：基础 3、边界 17、生命周期 6、本机菜单 2、网页交互 7。相比基线新增 13 项。

新增边界回归包含上传等待提交时取消的 `error` / `keep` / `replace` 策略，以及同步阶段取消后保留原文件与清理临时文件。

新增网页回归使用独立 Qt WebEngine 子进程和真实 HTTP 服务，覆盖：

- 历史返回后的搜索清理与根目录文件恢复。
- 慢网加载期间按钮与 Enter 禁止确认，以及过期目录响应不能覆盖新目标。
- 隐藏目标目录和超过 500 个目标目录的分页选择。
- 上传、同名保留两者、中文重命名、复制、移动、回收，以及通过本机 `TrashStore` 读取并恢复内容。
- 205 项列表分页、列表视图、倒序、搜索、全选与 Escape 清除选择。

相关回归还包含 Files 控制器、文件任务/回收站/模型/预览、图标、核心、QML、翻译、主题和界面声音。**这是相关测试集合，不是本轮全仓库测试。**

实际执行命令：

```sh
rtk proxy env QT_QPA_PLATFORM=offscreen QT_QUICK_BACKEND=software \
QT_QUICK_CONTROLS_STYLE=Basic PYTHONPATH=src \
/tmp/udeck-ui-audit-20261111-venv/bin/python -m pytest -q \
  tests/test_network_files*.py tests/test_files*.py \
  tests/test_file_icons.py tests/test_core.py tests/test_qml.py \
  tests/test_i18n_qml.py tests/test_theme_qml.py \
  tests/test_interface_sounds.py tests/test_interface_sounds_qml.py \
  tests/test_sound_interactions.py
```

使用独立 Python 环境，不修改项目原有 `.venv`。`ruff check src tests tools`、`node --check src/udeck/network_files/web/app.js` 和 `git diff --check` 通过。

## 独立浏览器与传输验证

| 项目 | 结果 |
| --- | --- |
| Chromium 实际文件操作 | 文件与文件夹上传、中文路径、新建、重命名、复制、单文件和目录 ZIP 下载通过 |
| 慢网目标确认 | 人为挂起目标目录请求后，确认按钮禁用；按 Enter 对话框保持打开，未发起写请求；恢复请求后复制到正确目录 |
| 键盘操作 | 自动化 Ctrl+A 选择全部 10 个可用项目，不选择符号链接；Escape 清除选择；重启后新建目录可用 Enter 提交 |
| 布局与脚本 | 英文/中文 × Classic/Dark × 1280×800/390×844 共 8 组通过，无横向溢出或未捕获脚本错误 |
| 独立 HTTP 大文件 | 上传并下载 4,194,308 字节，逐字节与 SHA-256 校验一致 |
| Range | `bytes=100-1099` 返回 206，内容与源文件切片一致 |
| ZIP | 大文件、嵌套目录与空目录组成的 ZIP 为 4,195,178 字节，内容与 CRC 校验通过；浏览器下载的目录 ZIP 另行校验通过 |
| 地址与跨站写入 | 两种畸形 Host、非监听域名和外部 Origin 被拒绝，无越权新建文件夹 |
| 浏览器断线恢复 | 浏览器模拟离线后显示断开，恢复网络后状态恢复连接 |
| 独立服务进程恢复 | 停止预览进程后浏览器显示断开；新进程启动后自动更新请求令牌并重载列表，随后成功通过页面新建目录 |

大文件 SHA-256：`ab02be9f60b3cbfd8ac8805a7afada3005d535c74f8dccc16bcdedb097dd1349`。

## 证据与验收边界

本轮证据在 ignored 目录 `artifacts/network-files-audit-2026-11-12/`：

- `baseline.log` / `baseline.xml`：既有测试基线。
- `regressions-before.log` / `.xml`、`picker-before.log` / `.xml`：修复前的失败复现。
- `regression-final.log` / `.xml`：最终 318 项相关回归。
- `browser-layout-report.json`、`web-*.png`：8 组布局报告与截图。
- `back-search-before.png`、`destination-loading-after.png`、`destination-requests-after.json`：导航与慢网操作证据。
- `http-transfer-report.json`、`Documents.zip`、`renamed-download.txt`：传输与实际下载校验。
- `browser-offline.png`、`browser-restart-result.json`、`service-restart-report.json`：模拟断线与独立进程恢复证据。
- `cleanup-report.json`：本轮独立浏览器与预览监听的最终收尾检查。

测试结束后已关闭独立浏览器会话并停止预览服务，确认端口 18787 无监听；仅保留隔离测试数据与证据。

**本轮未验证真实 Wi-Fi/VPN/物理网卡切换、Linux D-Bus/systemd 的设备集成、整机重启、正式桌面部署与物理按键。**生命周期自动化及本地预览进程恢复不替代这些实机验收。未构建或安装 Debian 包；已有未提交的其他界面修复保持原样。
