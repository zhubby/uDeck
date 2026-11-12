# 网络文件回归剩余失败修复

日期：2026-11-12。本轮承接 [网络文件完整回归](files-network-access-completion-2026-11-12.md)，处理首次全仓库运行中剩余的两项失败，以及重新完整回归时暴露的视频探针卡死、设置页分钟切换竞态。网络文件此前的功能修复全部保留。

**最终全量：1473 passed、0 failed、0 errors、5 skipped，735.80 秒。网络文件 50 项全部通过。**

## 根因与修复

原两项均确认是测试同步和故障注入的竞态，不需要修改产品的热点恢复逻辑或图片预览逻辑。

| 问题 | 确定性复现 | 修复 |
| --- | --- | --- |
| Files 图片预览测试过早读取尺寸 | 让本机 HTTP 图片响应延迟 350 毫秒，原测试等待 80 毫秒后断言 `implicitWidth > 0`，稳定失败；此时图片还未完成加载 | 在持续处理 Qt 事件的同时等待图片实际具有尺寸，最多等待 5 秒；保留宽度断言，并增加高度断言，不通过固定延长休眠掩盖问题 |
| 热点启动失败测试误伤 Wi-Fi 恢复 | 在热点轮询中注入一次 60 毫秒调度停顿，超过测试配置的 30 毫秒超时；原测试尚未来得及将全局 `auto_activate` 恢复为真，恢复 Wi-Fi 的请求也被测试替身置为连接中，导致首个指示仍为 `hotspot` | 故障只注入选中网卡的 AP 激活，不影响原客户端连接的激活；删除依赖 10 毫秒休眠来切换全局开关的逻辑 |

热点用例现覆盖三种情况：AP 一直连接中直至超时、同样场景叠加 60 毫秒调度停顿，以及设备明确进入失败状态。均要求原 Wi-Fi 的设备状态为 100、模式为 infrastructure、配置 UUID 为 `known`、连接名称为 Workshop、指示恢复为 Wi-Fi，同时另一张网卡的热点保持 active 且连接未被替换。

### 视频原生探针卡死

第一遍重新完整回归中，原两项失败均已通过，但 `tests/test_apps_native.py::test_real_engines_with_original_content_and_qml_workflows[video]` 超过 120 秒超时。结果为 **1470 passed、1 failed、5 skipped、13 warnings，847.15 秒**，保留在 `full-suite.log` / `.xml`，不将其记为全量通过。

随后在隔离目录连续诊断三次，第一次在 65 秒诊断截止时仍卡住，另外两次通过。`faulthandler` 多次将主线程定位在 `QTest.qWait`；macOS `sample` 显示主线程在 QML 控件无障碍对象创建期间等待 Qt 对象连接锁，音频渲染线程在 `QAudioOutputWrapper::disconnectNotify` 等待 Python GIL。

新增行为回归可确定性区分两种等待方式：Qt 计时器释放后台 Python 工作线程，要求工作在线程等待结束之前完成并被 Qt 观察到。临时提高 Python 字节码切换间隔只在子进程内进行，并在 `finally` 恢复；这使测试不依赖偶然的解释器切换来放行线程。原 `QTest.qWait` 路径失败，使用 `QEventLoop.exec` 的路径通过。

原生探针的八处 `QTest.qWait` 改为有单次 Qt 计时器退出的局部事件循环，等待时既处理 GUI 事件，也允许 Python 工作线程运行。没有增大原生视频测试的 120 秒超时，没有关闭音频、字幕、无障碍或视频解码，也没有更改产品运行时；实际应用仍运行自己的 `application.exec()`。

### 设置页分钟切换竞态

第二遍重新完整回归中，前三处修复均通过，但设置页出现一次 `window.clockText == controller.currentTime()` 断言失败，发生在截图跨分钟时。该次结果为 **1471 passed、1 failed、5 skipped、13 warnings，719.62 秒**，保留在 `full-suite-final.log` / `.xml`。

产品时钟由一秒周期的 Qt 计时器刷新；测试在取截图后立即与新的当前时间比较，跨分钟时会在下一次刷新前错误地判定失败。新增子进程回归仅控制 UTC 时间来源：截图后将 `00:00:59` 推进至 `00:01:00`，确定性复现相同断言失败；没有修改机器时钟，真实时区换算仍由产品执行。

修复后持续处理 Qt 事件，并在最多 3 秒内等待显示与当前时钟一致，保留严格相等断言。受控场景还要求选择东京后最终显示字面值 `09:01`，不能用旧的 `09:00` 通过。原有八组真实时钟、语言、主题及尺寸矩阵保持不变。

本轮只修改七个测试文件：

- `tests/files_qml_probe.py`：图片加载完成条件及仅用于延迟图片用例的源地址参数。
- `tests/test_files_qml.py`：真实回环 HTTP 延迟图片回归，保留原有双语言、双主题、双尺寸矩阵。
- `tests/test_hotspot.py`：按网卡、AP 模式限定的故障注入，以及超时、调度停顿、明确失败的恢复验证。
- `tests/apps_native_probe.py`：原生应用探针的事件等待方式。
- `tests/test_apps_native.py`：后台 Python 工作线程必须在 Qt 等待期间获得运行机会的行为回归。
- `tests/settings_qml_probe.py`：时钟显示同步等待，以及仅用于回归的受控 UTC 来源。
- `tests/test_settings_qml.py`：分钟切换回归，仍验证全部 11 张截图及按键交互。

未移除任何已有断言，未添加跳过或自动重试，没有用更宽松的热点状态判定换取通过。

## 验证记录

- 修改前，延迟图片与调度停顿两个用例 **2 failed，4.00 秒**。
- 修改后，延迟图片与三种热点恢复场景 **4 passed，4.08 秒**。
- 视频等待行为回归修改前 **1 failed，0.49 秒**；采用相同线程观察脚本比较原等待与事件循环，分别退出 1 和 0。
- 事件泵修复后的原生应用模块 **15 passed，59.13 秒**，覆盖真实音乐、视频、阅读器、浏览器内容与空库菜单矩阵。
- 分钟切换回归修改前 **1 failed，2.22 秒**；修复后设置页模块 **9 passed，44.42 秒**。
- 最终全仓库共 1478 项：**1473 passed、0 failed、0 errors、5 skipped、13 warnings，735.80 秒**；进程退出 0，无自动重试，日志和 JUnit 输出分别是 `full-suite-verified.log` 与 `full-suite-verified.xml`。

最终全量中，网络文件 50 项、Files QML 9 项、热点 39 项、原生应用 15 项、设置页 QML 9 项，共 **122 项相关回归全部通过**。相比前轮 1473 项收集数，新增延迟图片 1 项、热点额外场景 2 项、等待期间线程运行 1 项、分钟切换 1 项。

5 项跳过仍是两个需要 Linux session bus 的应用测试，以及三个需要原生终端插件的集成测试；未新增跳过。13 条警告来自 `dbus_next` 对 Python 3.13 弃用装饰器的使用，未屏蔽警告。Ruff、JavaScript 语法及 Git 空白检查均返回 0。

证据目录：`artifacts/network-files-final-fixes-2026-11-12/`。

- `timing-before.log` / `.xml`、`timing-after.log` / `.xml`：原两项竞态的红绿回归。
- `video-diagnostics/`：三次隔离诊断、Python 线程栈和原生线程采样。
- `video-wait-before.log` / `.xml`、`video-wait-comparison.json`：等待期间工作线程运行的确定性行为复现及比较。
- `native-after.log` / `.xml`：15 项真实原生应用回归。
- `full-suite.log` / `.xml`：发现视频超时的第一遍重新全量。
- `full-suite-final.log` / `.xml`：事件泵修复后发现分钟切换竞态的第二遍全量。
- `clock-before.log` / `.xml`、`clock-after.log` / `.xml`：受控分钟切换的红灯证据及设置页回归。
- `full-suite-verified.log` / `.xml`：所有本轮修复后的最终全量。
- `verification-summary.json`：红绿结果、三次全量结果、跳过原因、50 项网络文件与 122 项相关回归分类，以及本轮七个测试文件的 SHA-256。
- `static-checks.json`：Ruff、JavaScript 语法与 Git 空白检查。

专项复现命令：

```sh
rtk proxy env QT_QPA_PLATFORM=offscreen QT_QUICK_BACKEND=software \
QT_QUICK_CONTROLS_STYLE=Basic PYTHONPATH=src \
/tmp/udeck-ui-audit-20261111-venv/bin/python -m pytest -q \
  tests/test_files_qml.py::test_files_preview_waits_for_a_delayed_image \
  tests/test_hotspot.py::test_start_failure_restores_the_original_wifi_and_preserves_the_other_hotspot
```

全仓库命令：

```sh
rtk proxy env QT_QPA_PLATFORM=offscreen QT_QUICK_BACKEND=software \
QT_QUICK_CONTROLS_STYLE=Basic PYTHONPATH=src \
/tmp/udeck-ui-audit-20261111-venv/bin/python -m pytest -q -x \
  --junitxml=artifacts/network-files-final-fixes-2026-11-12/full-suite-verified.xml
```

## 验收边界

图片回归只使用 pytest 临时目录和本机回环地址，HTTP 服务在收尾时关闭；热点回归仅替换外部 NetworkManager D-Bus 边界，真实 uDeck 状态转换和状态指示计算保持运行。

此前全仓库的两项失败和复查记录保持不变，不覆盖历史证据。本轮不创建分支、不提交、不推送、不部署，保留工作区全部既有修改，不更改项目 `.venv`、用户回收站、真实网络或设备配置。

上一轮设备 SSH 认证被拒绝，本轮没有重新尝试登录。真实 Wi-Fi/VPN 切换、设备 systemd/D-Bus 集成、整机重启和物理按键仍需可用的设备授权访问；本地回归不能替代这些实机验收。
