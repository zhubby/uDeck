# Reader 原生 MOBI 支持与验证

Reader 可直接从 `~/Books` 或用户添加的来源打开 `.mobi`（包括大小写扩展名），使用原文件的稳定标识保存阅读进度与书签。Files 将 MOBI 识别为电子书，Reader 的桌面入口声明 `application/x-mobipocket-ebook`，可用于“打开方式”。不需要先转换成 EPUB，也不依赖 Calibre。

正文沿用现有 Foliate 阅读界面，支持目录跳转、左右／L/R 翻页、搜索、书签和 CFI 进度恢复。`Y 设置 → 阅读排版` 可调整字体、行距、正文宽度和背景；字号设置同样适用于 MOBI。

## 实现边界

- 新增的 `foliate/mobi.js` 来自现有 Foliate 固定提交 `78914aef4466eb960965702401634c2cb348e9b1`，保持上游文件原样，许可为 MIT。模块 SHA-256 为 `016526df13a9f11ee6671a8c74346e1cf41fe6bdfe50165fdcbf744f015694f3`。来源与集成说明见 `src/udeck/apps/reader/web/UPSTREAM.md`。
- 上游实现 MOBI6、KF8，以及未压缩、PalmDOC、HUFF/CDIC 解压；本次实书验收覆盖 MOBI6/PalmDOC，原创夹具覆盖未压缩与 PalmDOC 的容器读取。KF8、HUFF/CDIC 和压缩嵌入字体未用独立实书验收。
- Python 校验 PDB 记录表、MOBI 头和加密标志；损坏文件、未知压缩类型与 DRM 加密书籍给出可恢复错误。DRM 加密书籍无法读取。
- 浏览器通过带会话令牌的本机端点请求所需记录。只保留选中文件的打开描述符，拒绝符号链接、扫描后改变的文件及读取期间的变更。书籍上限为 512 MiB，单条记录／请求为 64 MiB，文件头声明的正文上限为 128 MiB。
- 保留原有 CSP、书籍脚本与网络隔离，以及浏览器／阅读器独立 profile；没有增加书籍执行脚本或访问任意本地文件的权限。

## 自动验证

`tests/test_reader_mobi.py` 覆盖索引与稳定标识、Files 分类、实际桌面 MIME 声明、会话隔离、逐记录原字节读取、大于 TXT 限额的稀疏文件、错误记录表／文件头、加密标志、压缩类型、正文大小、符号链接、关闭会话与文件变更。

`tests/apps_native_probe.py reader` 使用原创 PalmDOC MOBI，在真实 QtWebEngine 中验证正文、翻页、字号／字体／行距／宽度／背景、书签、搜索与重新打开。书中的恶意脚本与外部请求被 CSP 拦截。相同流程同时回归 TXT、EPUB 和 QtPdf。

本次运行结果：格式／Reader／Files／来源与路由相关 82 项通过，Reader 原生 Qt 流程 1 项通过；翻译、首页与阅读排版相关 49 项通过。干净目录构建 wheel 成功，逐字节确认包含本次 Python、JS 模块与来源说明，未混入旧目录结构的 Reader 模块。

## 用户实书与设备验证

2026-11-10 使用用户提供的《战锤·荷鲁斯之乱.mobi》原件：

| 项目 | 结果 |
| --- | --- |
| 文件大小 | 73,068,980 字节 |
| SHA-256 | `58058cf06e32c8b35029e4551e7a8a08be2c44a4b18e74ccce35ec282d7d7126` |
| 格式 | 未加密 MOBI6、PalmDOC 压缩、UTF-8 |
| 解析结果 | 237 个目录项、264 个内容分段 |
| 本机 | macOS、Qt 6.8.3、真实 QtWebEngine 离屏渲染 |
| 实机 | `clockworkpi`、Debian arm64、Qt 6.8.2、已安装模块 |
| 功能 | 目录跳转、翻页、实际 CSS 字体／字号／行距／宽度／背景、书签、全文搜索、原文件进度恢复通过 |
| 搜索 | “荷鲁斯”命中阅读器的 200 条结果上限 |
| QML 错误 | 本机与实机均为空 |

可用独立状态重跑实书验证，命令不会改变书籍或用户 Reader 设置：

```sh
QT_QPA_PLATFORM=offscreen QT_QUICK_BACKEND=software PYTHONPATH=src \
  python tests/reader_mobi_probe.py /path/to/book.mobi /path/to/evidence
```

设备以现有 uDeck 0.2.3 为基础定向更新 Reader 相关模块，备份位置为 `~/udeck-mobi-20261110-01/backup`。设备的来源索引实现与当前仓库不同，因此只在它的原文件中增加 `.mobi` 扩展名，保留其他实现；未整包覆盖。只通过 compositor 正常关闭、重新启动 Reader，保留桌面 shell、登录会话、compositor 和模拟器。

设备测试报告、部署清单、备份、真实屏幕截图和实际进程诊断保存在 `~/udeck-mobi-20261110-01/`；本地证据保存在忽略目录 `artifacts/reader-mobi/`。完整电子书未加入仓库。
