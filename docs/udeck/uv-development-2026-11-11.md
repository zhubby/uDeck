# uv 开发环境接入与验证

本次将 uDeck 的 Python 开发环境统一到 uv 0.13.7 和 uv 管理的 Python 3.13.18，提交依赖锁文件，并在现有 Release workflow 中增加依赖一致性与 Ruff 检查。Debian 构建、原生插件和设备运行继续使用系统 Python 与 APT。

实施基线为 `3087b837284c567ac4d1bd4dce38d74ee631ad98`，工作分支为 `codex/udeck-uv`。工作位于独立工作树；主目录的业务修改及失效的旧 `.venv` 均保留。

## 变更

- `.python-version` 固定开发解释器为 3.13.18；`[tool.uv].required-version` 固定 uv 为 0.13.7。
- `uv.lock` 使用官方 PyPI，锁定 16 个包。已有主要开发依赖版本保持为 PySide6 6.8.3、pytest 9.2.0、Ruff 0.17.3、build 1.6.1 和 dbus-next 0.2.3；Linux evdev 首次解析为 2.0.0。
- 保留 setuptools 后端、现有 `dev` extra、Python `>=3.11,<3.14` 及 Qt/PySide6 `>=6.8,<6.9`。
- 现有 Release workflow 在 Debian 构建前安装固定 uv，检查锁文件、同步开发依赖并执行 Ruff；事件仍仅为 `release: published`。
- `setup-uv` 固定到已核实的 v7 提交 `37802adc94f370d6bfd71619e3f0bf239e1f3b78`。v7 的附注标签对象与最终提交 SHA 不同，workflow 使用最终提交。
- Debian 源码归档加入 `uv.lock` 与 `.python-version`，安装探针增加解包后的字节比对。
- 更新开发、升级、环境备份/恢复及 Debian 边界说明。运行代码、`debian/rules` 和 `debian/control` 与基线一致。

## 日常命令

安装固定 uv 及迁移旧环境的方法见 [开发文档](README.zh-CN.md#开发预览)。在项目根目录执行：

```sh
uv python install
uv sync --locked --extra dev
uv run --locked --extra dev udeck --mock --windowed
uv run --locked --extra dev pytest -q
uv run --locked --extra dev ruff check src tests tools
uv run --locked --extra dev python -m build --wheel
```

日常同步不升级依赖。升级单个包使用 `uv lock --upgrade-package <包名>`，审查锁文件并重新验证。Linux 上 evdev 源码构建需要编译器和 Linux 头文件；显式选用系统 Python 时还需要对应的 Python 开发头文件。

## 已完成验证

| 项目 | 结果与证据 |
| --- | --- |
| 全新 macOS 环境 | uv 管理的 Python 3.13.18 完整同步成功；独立环境见 `artifacts/uv/fresh-venv/` |
| 重复同步 | 连续同步成功，锁文件 SHA-256 保持不变；`artifacts/uv/repeated-sync.json` |
| 过期锁拒绝 | 临时副本改变依赖的平台声明后，`uv lock --check --offline` 退出 1，锁文件未改；`artifacts/uv/stale-lock.json` |
| Linux 固定解释器 | 在原生 arm64 容器中运行 uv 管理的 Python 3.13.18，确认头文件存在，uv 正确识别解释器且离线锁检查通过；`artifacts/uv/linux-managed-python.json` |
| Ruff / workflow / 空白检查 | Ruff、Actionlint、`git diff --check` 通过 |
| 相关测试 | 26 项 CLI、Release 和安全检查通过 |
| 隔离 wheel 构建 | `dist/uv-wheel/udeck-0.2.3-py3-none-any.whl`，405 个成员；元数据保留原 Python、运行依赖和 extra 范围 |
| QML mock 冒烟 | 退出 0，`smoke: passed`、`qmlErrors: []`；截图为 `artifacts/uv/preview-home.png`；曾观察到退出阶段的 null context 警告 |
| Debian 源码归档 | 使用真实 Release 暂存逻辑，再由 `dpkg-source` 打包、解包；三个配置文件逐字节一致。证据在 `dist/uv-source-check/source-check.json`；该检查仅生成源码包 |

锁文件 SHA-256：`79f12e9be2d969e8b234fb019054129ddee63a9a5a9bda987f26eabe19e948d8`。

Wheel SHA-256：`09bb9bb99fff1034c455606c9df7d9e11745fc17952f2f44241a7b876fbe85ae`。

## 全量测试与未完成验收

macOS 首轮全量测试为 **1,310 passed、5 skipped、2 failed**，失败项为 PDF 探针超时和视频 sink；两项定点复测均通过。证据为 `artifacts/uv/baseline-pytest.xml`、`artifacts/uv/macos-baseline-recheck.xml`。

uv 驱动的第二轮全量为 **1,309 passed、5 skipped、3 failed**，耗时 621.18 秒。失败项为两个文件后台任务完成断言，以及 QML 子进程退出阶段的 null context 警告；随后相同三个用例定点复测为 **3 passed**。证据为 `artifacts/uv/macos-uv-pytest.log`、`artifacts/uv/macos-uv-pytest.xml`、`artifacts/uv/macos-uv-targeted.log`。定点通过不替代全量通过；五项跳过为两个 Linux session-bus 用例与三个原生终端插件用例。

Debian arm64 使用 `udeck-debian-release-builder:20261109`，已确认满足当前构建依赖。两次真实发行构建均成功编译 Qt 6.8.2 原生终端插件，但在全量 pytest 约 64% 处，于 `tests/test_reader_layout.py:61` 的 fixture 清理 `application.processEvents()` 中崩溃，Debian 测试步骤退出 139。日志为 `artifacts/uv/debian-build.log`、`artifacts/uv/debian-build-retry.log`。

缩小范围后，Reader 模块 4 项、Files + Reader 42 项、前置 Qt 模块组合 430 项分别通过，尚未确定生命周期问题的根因。另一次全仓库收集后仅保留上述 Qt 模块的实验未使用 session bus，运行停滞后主动终止，不能作为通过或同条件复现证据。

原始提交 `3087b83` 的隔离 Debian 对照构建成功，**1,317 passed**，耗时 436.25 秒，日志为 `artifacts/uv/debian-baseline-build.log`。随后直接使用该原始源码重复同一 QML 冒烟流程，第二次就出现相同的 `viewSnapshotJson` / `translate` / `fileModel` null context 警告，证据为 `artifacts/uv/baseline-qml-repeat.json`。因此已确认 QML 退出警告在原始提交中就存在；Reader 清理崩溃的根因尚未确认。

迁移分支的最后一次完整 Debian 构建完成了全部测试，结果为 **1,316 passed、1 failed**，耗时 456.37 秒；唯一失败为 `tests/test_qml.py::test_all_qml_pages_render_without_engine_warnings` 的退出警告断言，日志为 `artifacts/uv/debian-build-final.log`。该次没有发生 Reader 崩溃，但此前两次崩溃仍保留为未解决记录。

补充的 Linux uv 安装检查先使用 Debian 系统 Python 3.13.5；安装 Python 开发头文件后 evdev 2.0.0 编译成功。随后在宿主机下载 Linux 的 uv 管理解释器，并在原生 arm64 容器中确认 Python 3.13.18 运行、头文件、uv 识别及离线锁检查均正常。容器与宿主机两条下载路径均遇到 PySide/Ruff 包下载超时，未完成 Linux uv 全量同步。

迁移分支的完整 Debian 二进制构建、干净安装/卸载/重装探针及 GitHub 托管 Release 运行尚未通过本轮验收。未使用 `nocheck`、未修改失败断言，也未发布 Release。后续验收需要处理已复现的 QML 退出警告，并确认 Reader 清理及文件后台任务测试的稳定性，再重新构建和运行安装探针。
