# 网络文件遗漏问题修复与完整回归

日期：2026-11-12。本记录接续 [首轮网络文件测试与修复](files-network-access-audit-2026-11-12.md)，保留首轮 6 类问题的修复，继续测试取消、故障关闭和断线恢复。

后续两项全量失败的确定性复现、根因修复及重新回归记录见 [剩余回归失败修复](files-network-access-final-fixes-2026-11-12.md)。本记录保留首次全量与复查的原始结果。

## 本轮追加修复

| 问题 | 复现 | 修复 |
| --- | --- | --- |
| 停读或排队上传无法及时取消 | 客户端发送 PUT 请求头后停读，或仅发送一个字节；取消接口返回成功，但上传会话、临时文件和并发名额继续保留 | 取消信号主动中断接收任务，包括等待并发名额的任务；收尾仍等待正在使用文件描述符的后台写入完成，重复取消不重复打断该等待 |
| 异常关闭仍留下共享服务 | 保存关闭配置时模拟磁盘满，监听器没有关闭；远程 Stop 或 systemd disable 出错时，也不会继续执行 systemd stop | 监听器关闭和 systemd stop 放到必经收尾路径；根目录被替换时同样不因保存失败跳过撤销；错误继续报告给用户，不伪装为保存成功 |
| 未保存的配置自动生效 | 开启共享时保存失败，但内存已经标记启用；下一次网络轮询会启用未保存的共享，重新配置失败还会丢失原监听 | 先持久化候选配置，再替换正在运行的配置；保存失败不启用新共享，也不影响原有已保存的共享 |
| 连接恢复但目录不恢复 | 首次配置请求失败后恢复连接仍无文件；同一进程短暂断线后，连接状态恢复但列表不刷新 | 初次故障恢复或原服务重连时重新读取目录，清理错误状态，不再只依赖服务令牌变化 |
| 读取失败保留旧的危险操作 | 已选中文件后目录读取失败，旧列表和删除/移动按钮仍可操作 | 读取失败时清理列表与选择，隐藏旧文件操作、分页和旧容量信息，重试成功后再展示新数据 |
| 目录错误被误报为断网 | 打开已不存在的目录返回 404，但页面显示“设备连接已断开” | HTTP 错误携带状态码，区分目录/权限错误和真实连接或服务故障 |

本轮只扩展网络文件相关代码，没有改动此前其他界面修复，不创建分支、不提交、不推送、不部署。

## 失败复现与专项测试

- 新增第一组 11 个回归用例，修改前 **11 failed**。
- 补充“重新配置失败保留旧共享”和“根目录撤销保存失败仍关闭”，修改前 **2 failed**。
- 修复后网络文件测试 **48 passed，49.32 秒**；再补充“等待并发名额时取消”和“写线程未结束时重复取消”，**2 passed，0.27 秒**。
- 网络文件测试现共 50 项：基础 3、边界 22、生命周期 10、本机菜单 2、网页交互 11、服务客户端 2。

网页回归在独立 Qt WebEngine 子进程中连接实际本地 HTTP 服务。首连失败由服务返回一次 503；断线与故障分支使用受控请求失败模拟。systemd 客户端测试替换命令执行器，不操作本机或设备真实 unit。

## 独立 HTTP 故障验收

在 ignored 目录下创建独立共享目录、配置和数据目录，服务只绑定本机 loopback，使用原始 TCP 连接构造慢上传：

| 验证 | 结果 |
| --- | --- |
| 8 个停读上传会话 | 同时覆盖正在接收与等待并发名额的上传；全部取消并返回 400，上传会话清空 |
| 取消后的文件状态 | 无残留 `.udeck-web-*` 临时文件，也未提交被取消的目标文件 |
| 取消后的继续使用 | 随后成功上传、下载 4,194,322 字节，逐字节一致；未被旧会话占满名额 |
| 停止共享时配置写入失败 | 故障注入 `OSError`，错误正常上报；监听、已有连接均关闭，未产生上传目标文件或残留临时文件 |
| 收尾 | 验收程序的两个服务实例及所有客户端连接均在 `finally` 中关闭 |

继续传输的 SHA-256：`1127416ce3064ceeffb1caf0bd5c4b15d0e8524c1ef585b02db091f8c19a1678`。

## 全仓库回归

全仓库共收集 1473 项，结果为 **1466 passed、2 failed、5 skipped、13 warnings，817.50 秒**。其中全部 **50 项网络文件测试通过**，没有失败或跳过。

两项首次全量失败均不在本轮修改的网络文件模块中：

| 测试 | 全量运行时的失败 | 精确用例复查 |
| --- | --- | --- |
| `tests/test_files_qml.py::test_files_workspace_renders_with_controller_navigation[size0-classic-en]` | 图像预览显示后等待 80 毫秒，`filePreviewImage.implicitWidth > 0` 断言未满足；后续 controller 空引用日志出现在断言失败退出之后，并非首个错误 | 通过 |
| `tests/test_hotspot.py::test_start_failure_restores_the_original_wifi_and_preserves_the_other_hotspot` | Wi-Fi 恢复后的首个状态指示仍为 `hotspot`，预期为 `wifi` | 通过 |

上述两个精确用例单独复查 **2 passed，3.32 秒**，证据为 `full-failures-recheck.log` 与 `.xml`。这只能证明单独复查未重现，不能据此将首次全仓库结果改记为通过，也不能确定两项失败的最终根因。本轮没有修改热点实现或相关测试，也没有为绕过断言而放宽测试。

随后将全部网络文件测试、整个 `tests/test_files_qml.py` 和整个 `tests/test_hotspot.py` 一起复查，结果为 **95 passed、13 warnings，75.37 秒**。其中网络文件 50 项、Files QML 8 项、热点 37 项均通过，无失败、无跳过。证据为 `final-modules-recheck.log` 与 `.xml`；首次全量的两项失败在这次整模块复查中也未重现，但首次全量记录仍保留为失败。

5 项跳过分别是两个需要 Linux session bus 的应用测试，以及三个需要原生终端插件的 PTY、会话生命周期和 ANSI/Nerd 字形测试；当前 macOS 隔离环境不满足这些条件。

执行命令：

```sh
rtk proxy env QT_QPA_PLATFORM=offscreen QT_QUICK_BACKEND=software \
QT_QUICK_CONTROLS_STYLE=Basic PYTHONPATH=src \
/tmp/udeck-ui-audit-20261111-venv/bin/python -m pytest -q \
  --junitxml=artifacts/network-files-completion-2026-11-12/full-suite.xml
```

## 证据与设备边界

本轮证据目录为 `artifacts/network-files-completion-2026-11-12/`，与首轮证据分开：

- `regressions-before.log` / `.xml`：11 项失败复现。
- `persistence-before.log` / `.xml`：两项持久化错误分支失败复现。
- `network-after.log` / `.xml`、`cancellation-workers.xml`：修复后的专项回归。
- `runtime-acceptance.json`：8 会话取消、继续传输和异常停止的独立 HTTP 验收。
- `device-access.json`：设备 SSH 访问结果。
- `full-suite.log` / `.xml`：全仓库回归记录。
- `full-failures-recheck.log` / `.xml`：两项首次全量失败的精确用例复查。
- `final-modules-recheck.log` / `.xml`：网络文件、Files QML 和热点整模块共 95 项复查。
- `static-checks.json`：`ruff check src tests tools`、JavaScript 语法与 Git 空白检查，均返回 0。

对既有设备地址 `192.168.11.59` 进行了只读 SSH 探测，返回 `Permission denied (publickey,password)`，退出码 255；未取得会话，也未修改设备。**真实 Wi-Fi/VPN 切换、设备 systemd/D-Bus 集成、整机重启与物理按键仍未验收。**这些是访问条件限制，不是已复现的软件故障；不能用本地故障注入或回环连接测试替代。

未修改项目原有 `.venv`、用户文件、用户回收站、SSH 配置、真实网络配置或设备电源状态。
