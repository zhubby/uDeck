# 界面交互复测与第二轮修复（2026-11-11）

本轮在第一轮五类修复的基础上，继续测试七种窗口的原生动作路由、长按、反复编辑、窗口缩放、视频拖动生命周期和文件任务反馈，新增五类修复。第一轮结果保留在 `ui-interaction-fixes-2026-11-11.md`，没有用本轮结果覆盖历史记录。

测试于 2026-11-11 开始，最终全量回归于 **2026-11-12（北京时间）**结束；文件和证据目录沿用开始日期，便于追溯连续测试过程。

## 新复现并修复的问题

| 编号 | 复现与原因 | 修复 | 回归边界 |
| --- | --- | --- | --- |
| R2-01 | 输入法组合期间，原生 A/B 动作直接调用 `dispatch("accept"/"back")`，绕过 QML 键盘防护；Terminal 的原生上下动作也会开始搜索 | 共用 `composing_action_blocked()` 检查实际前台焦点的组合态及 `inputController` 所有权，在 Shell、共用应用和 Terminal 的动作入口拦截确认、返回及导航 | 七种窗口分别测试确认和返回；Terminal 测试上下动作；组合提交后普通动作有效；后台的其他 controller 不受前台编辑器影响 |
| R2-02 | Terminal 快捷键和模态确认接受 auto-repeat；一次长按 Ctrl+Shift+T 新增六个会话，历史选区的长按 Enter 提前复制退出，字体设置一次长按从 20 降到 14 | 六个快捷键禁止 auto-repeat；模态及历史键盘路由只放行连续导航动作，不连发确认和返回 | 每次独立确认仍有效；方向和历史翻页仍可连续移动；历史复制需要第二次有意按下；字体一次只减少一档 |
| R2-03 | Browser 方向动作直接赋值虚拟指针 x/y，破坏原有绑定；指针移至右下角后将 1280×720 缩至 800×500，指针留在可见区域外 | 方向动作只更新独立 `location`，x/y 始终通过声明式绑定限制在当前 viewport 内 | 中英文 × classic/dark，缩小、继续移动、再放大均可见；几何探针只修改模型中的保留 `.invalid` 地址，不发起该地址导航 |
| R2-04 | 视频滑块按住不动时仍触发闲置隐藏，打断拖动；继续测试发现按住时退出播放，已隐藏页面的被动 PointHandler 仍保持 active | 按压期间禁止闲置隐藏，释放重置闲置时间；指针观察器由可见性控制的 Loader 持有，离开播放页卸载观察器并释放 controller 状态，而非仅禁用仍然 active 的 handler | 实际静音 MP4、真实 Slider press/release；按住保持可见、释放后正常隐藏、退出时卸载观察器且滑块不再 pressed、重新播放后继续正常隐藏；原有按钮和拖动不被观察器抢占 |
| R2-05 | 全量回归及单独复测发现，小文件任务可能在注册 Future 回调前完成，回调在启动交互中同步执行，完成反馈之后又发出打开面板反馈，任务状态也提前离开异步边界 | 文件进度和完成信号显式使用 GUI 事件队列，保证当前启动交互先结束，再按序发布结果 | 使用实际临时文件及已完成 Future 稳定复现；启动时仍为活动任务，事件循环完成后反馈顺序为 open → success，文件内容正确；完成后晚到的进度不会恢复 running；文件控制、任务和声音 62 项相关测试通过 |

R2-01 的防护只检查属于当前 controller 的前台输入，不依赖全局组合态布尔值，避免另一个窗口的输入影响后台动作。保留 `QCoreApplication` 路径，不为无 GUI 场景引入 QWidget 初始化要求。

R2-04 的加速边界测试调用正常 `poll()` 推进闲置计数；原流程媒体矩阵另外保留实际播放和定时隐藏检查。重新进入播放页后先执行一次明确的鼠标移动，再观察静止闲置边界，避免把新观察器的首次 hover 初始化误当成持续静止。

## 反复操作与验证

- 当前 `tests/test_ui_interactions.py` 共 68 项真实 Qt/QML 事件回归，较第一轮新增 32 项。
- 加上文件任务的确定性回归，本轮共新增 33 项测试；第一轮回归均继续保留。
- 七种窗口各执行四轮输入、选区、语言和主题切换、组合态保护及取消，共 28 轮编辑循环；焦点、选区、光标和草稿保持一致。
- 视频拖动、退出、重新播放及原指针按钮测试连续运行五轮，每轮 2 项通过，保留各轮 JUnit 和日志。
- 文件任务增加 1 项确定性时序回归，并保留既有晚到进度保护的检查；对已有异步任务测试改为等待 GUI 完成队列，再明确注入晚到进度，而不是依赖完成回调恰好同步执行。
- 原有文件完成反馈测试和新增确定性测试一起连续运行十轮，每轮 2 项通过。
- 最终原流程矩阵 19 份报告全部通过：470 条通用检查、10 条 Terminal 检查，以及 5 份实际媒体报告；所有已记录的 QML 错误为空。媒体报告包含小窗口几何、视频定时隐藏、鼠标唤回及一次长按只产生一次 PausedState 转换，不将这些观察合计伪称为独立用户流程数量。
- `ruff check src tests tools` 和 `git diff --check` 通过。
- 最终全量回归：**1440 项通过、5 项跳过、0 项失败、13 条警告**，共收集 1445 项，耗时 **837.16 秒**；68 项界面交互回归全部通过。跳过项为 2 项需要 Linux 会话总线的路由测试和 3 项需要原生 Terminal 插件的测试；警告来自 dbus-next 的 Python 弃用提示。

运行环境为 macOS、Python 3.13.18、PySide6 6.8.3，Qt offscreen / software / Basic。原项目 `.venv` 保持不动，使用 `/tmp/udeck-ui-audit-20261111-venv`；视频样本需要 `ffmpeg`，音视频播放显式静音。

```sh
rtk proxy env QT_QPA_PLATFORM=offscreen QT_QUICK_BACKEND=software QT_QUICK_CONTROLS_STYLE=Basic \
  PYTHONPATH=src /tmp/udeck-ui-audit-20261111-venv/bin/python -m pytest -q tests/test_ui_interactions.py
rtk proxy env QT_QPA_PLATFORM=offscreen QT_QUICK_BACKEND=software QT_QUICK_CONTROLS_STYLE=Basic \
  PYTHONPATH=src /tmp/udeck-ui-audit-20261111-venv/bin/python -m pytest -q
rtk proxy /tmp/udeck-ui-audit-20261111-venv/bin/python \
  artifacts/ui-interaction-round2-final-2026-11-11/run_matrix.py
```

## 证据记录

- `artifacts/ui-interaction-round2-2026-11-11/` 保留本轮红灯、逐项绿灯、编辑循环和五次指针复测。`red.xml`、`red-directions.log`、`red-boundaries.xml`、`red-settings.log`、`red-hold.xml`、`red-held-lifecycle.xml` 对应实际复现。
- `red-held-lifecycle.log` 记录退出时 `surface visible=False`，但 `QQuickPointHandler` 仍为 active，确认为观察器生命周期而非返回动作未生效。
- `red-file-completion.xml` 稳定复现了已完成 Future 绕过 GUI 完成队列；首次全量回归的文件完成反馈失败和单独重复复测的失败也保留，最终全量使用独立的 `pytest-final.log` / `pytest-final.xml`，不把中间失败改写为通过。
- 视频修复后的中间全量运行完整结束，结果为 1437 通过、2 失败、5 跳过、13 警告，耗时 862.11 秒：一项揭示 R2-05，另一项是地址探针把发出导航请求后的固定 50ms 等待误当成 WebEngine 必已回写 URL。探针改为同时断言唯一导航请求的实际草稿、输入面板关闭，并等待实际 URL 回写；没有改变 Browser 的异步导航架构。
- 曾在发现视频长按问题前启动全量测试；确认该新问题后主动用 SIGINT 结束该次运行，结果为 652 通过、2 跳过、13 警告，退出码 2。这不是最终验收，也不是超时失败；原日志和 JUnit 保留为 `pytest-interrupted-for-held-pointer.*`。
- 最终源代码的全量日志、JUnit、19 份原流程报告和截图独立保留在 `artifacts/ui-interaction-round2-final-2026-11-11/`，不覆盖中间或第一轮证据。矩阵运行器同时验证进程退出码和 JSON 中的实际检查，不以零退出码代替检查通过。
- 最终验收以 `pytest-final.xml` / `pytest-final.log` 为准；`final-acceptance.json` 从最终 JUnit 和 `matrix-summary.json` 提取测试数量、实际跳过原因及矩阵结果，并断言 68 项界面回归均通过，不复用中间运行或第一轮的全量计数。
- 原媒体探针在 800×500 的“唤回点击”坐标会落在下一章节按钮上，可能先改变播放状态，使后续长按测试失去正在播放的基线。只修正最终探针副本：点击视频空白中心，并在长按前断言仍在播放；错误坐标的脚本、矩阵和媒体报告保留在 `probe-diagnostics/`。实际按钮与滑块仍由专门的真实事件回归验证，没有为探针改变生产逻辑。
- 复核 Browser 缩放截图后加强几何探针：等待初始 about:blank 加载完成，再设置只用于几何动作的模型地址，并明确断言缩小前指针已到 viewport 右下边界，避免迟到的初始加载事件重置模型、使“未实际移动”也通过边界检查。四种语言/主题组合均通过加强后的检查，截图保留在 `regression-screenshots/`。
- 第一轮红灯与复测继续保留在 `artifacts/ui-interaction-audit-2026-11-11/`、`artifacts/ui-interaction-retest-2026-11-11/`。

## 验收限制

Qt 事件与合成 `QInputMethodEvent` 验证的是组合态和业务动作所有权，不证明实体按键、真实 fcitx 候选窗或 Wayland 输入行为。Terminal 使用 mock 预览后端，不能代替原生插件、PTY 和原生渲染验收。视频使用实际 QMediaPlayer/MP4，不能代替硬件解码、扬声器或轨迹球实机验收。

本轮没有连接或更新 uConsole，没有部署、提交、创建分支或推送。未修改与本轮无关的第三方参考档案；全仓库 `ruff check .` 原有的 `references/uconsole/clockworkpi-uConsole/Code/scripts/audio_3.5_patch.py` 导入排序问题不属于本轮修复。
