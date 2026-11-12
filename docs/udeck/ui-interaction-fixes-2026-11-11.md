# 界面交互与按键修复（2026-11-11）

针对本轮界面审计发现的五类问题进行修复，基线为 `0.2.3` / `c6e41b7871ece599b7666154a35cea549cc4a689`。
没有调整系统按键映射、会话配置、设备安装或用户数据，也没有提交、推送或部署。

## 修复范围

| 问题 | 修复 | 回归边界 |
| --- | --- | --- |
| F01：重复 Ctrl+L 叠加地址输入，显示文本和 A 动作提交值不同 | 复用当前地址输入；共用弹窗增加稳定身份，按弹窗身份恢复文本，不再靠标题或焦点判断 | Enter 和 `accept` 动作提交同一地址；一次 Escape 关闭；同标题嵌套输入恢复各自草稿，普通更新不重置光标或组合态 |
| F02：组合态 Enter / Escape 提前提交或关闭输入 | 主壳、共用输入和 Terminal 搜索在组合态阻止业务确认、返回与候选方向键继续触发父级快捷动作；主壳不再直接用 `onAccepted` 提交 | 七种窗口的 Return、数字键盘 Enter、Escape；Terminal 的 Up / Down；组合提交结束后普通确认和返回继续有效 |
| F03：长按 Enter 多次播放 / 暂停 | 共用键盘路由只放行方向动作的 auto-repeat；确认、返回、分页、菜单及快捷键不连发 | 本地原创 WAV / MP4 的实际 `QMediaPlayer` 只切换一次状态；重复方向事件仍改变选中控件 |
| F04：视频控制栏隐藏后鼠标无法唤回 | 以被动指针观察恢复控制栏、重置闲置时间，不抢占按钮和滑块；过滤坐标不变的合成 hover 更新 | 自动隐藏、移动唤回、无移动点击唤回、持续活动延后隐藏、暂停按钮和进度拖动；静止视频帧刷新不会一直重置闲置计数 |
| F05：音乐小窗口控件和状态被裁切 | 按内容高度收紧字号、间距和封面尺寸；详情区支持纵向滚动；键盘切换播放控件时自动显示控件所在区域 | 中英文 800×500、960×600、1280×720；短标题和普通艺人信息直接显示三按钮及随机 / 循环状态；长元数据可滚动，方向选择仍可见 |

音乐布局检查同时核对外层内容面和所有启用裁切的祖先，避免“在窗口内但被内部 Flickable 裁掉”的假通过。
视频鼠标测试同时验证按键点击和 Slider 拖动，不以单纯观察 `controlsVisible` 代替完整交互。

## 自动化验证

使用 macOS、Python 3.13.18、PySide6 6.8.3、Qt offscreen / software / Basic。
保留失效的原项目 `.venv`，使用独立环境 `/tmp/udeck-ui-audit-20261111-venv`；不修改开发机的 Python 链接。

- 新增 `tests/test_ui_interactions.py` 和真实 QML / 事件探针 `tests/ui_interaction_probe.py`，共 36 项回归。
- 修复前验证：35 项失败、1 项通过，保留原始红灯日志；另保留长元数据方向选择不可见的红灯记录。
- 新增回归：36 项通过，QML 错误为空；覆盖七种窗口的组合态及普通提交、两种实际播放器、被动指针、布局和滚动。
- 原始流程复测：19 份报告无失败、QML 错误为空；通用窗口 470 条检查、Terminal 10 条检查通过，5 份实际媒体报告的几何、闲置隐藏、鼠标唤回和单次状态切换均通过。检查包含截图和几何记录，不等同于 480 条独立用户流程。
- 原报告合计 475 条检查、38 条失败；本次复测涵盖全部原检查名称，另执行了旧中文主壳输出未记录的 5 条空窗口列表和组合态检查，未减少原有检查。对比汇总为 `artifacts/ui-interaction-retest-2026-11-11/retest-summary.json`。
- 全量回归：**1407 项通过、5 项跳过、13 条警告**，耗时 639.58 秒；跳过项为 2 项 Linux 会话总线和 3 项原生 Terminal 插件测试，警告来自 dbus-next 的 Python 弃用提示。
- `ruff check src tests tools`、`git diff --check` 通过。
- `ruff check .` 会扫描参考档案，并命中未修改的第三方 `references/uconsole/clockworkpi-uConsole/Code/scripts/audio_3.5_patch.py` 导入排序问题；本次未改参考档案。

可重复执行：

```sh
rtk proxy env UV_PROJECT_ENVIRONMENT=/tmp/udeck-ui-audit-20261111-venv uv sync --locked --extra dev --managed-python
rtk proxy env QT_QPA_PLATFORM=offscreen QT_QUICK_BACKEND=software QT_QUICK_CONTROLS_STYLE=Basic \
  PYTHONPATH=src /tmp/udeck-ui-audit-20261111-venv/bin/python -m pytest -q tests/test_ui_interactions.py
rtk proxy env QT_QPA_PLATFORM=offscreen QT_QUICK_BACKEND=software QT_QUICK_CONTROLS_STYLE=Basic \
  PYTHONPATH=src /tmp/udeck-ui-audit-20261111-venv/bin/python -m pytest -q
```

视频原生样本测试需要 `ffmpeg`；无该命令时，对应两项回归明确跳过。
WAV / MP4 均在测试目录生成，播放显式静音，不访问用户媒体或验证扬声器输出。

## 证据与限制

- 原审计保留于 `artifacts/ui-interaction-audit-2026-11-11/`，包含问题报告、红灯日志、截图和原始探针输出，没有用复测结果覆盖。
- 修复复测保留于 `artifacts/ui-interaction-retest-2026-11-11/`，包含新增回归、全量 JUnit / 日志、原流程 JSON 和截图。
- 复测复制了原探针，仅修正副本中 KeyTestFilter 的销毁顺序：先移除事件过滤器，再销毁窗口和 QML engine；原始证据不变。
- `QInputMethodEvent` 只验证 Qt 组合态及业务路由，不证明真实 fcitx 候选窗、组合输入和平台输入法端到端验收。
- Terminal 使用预览后端；实际终端原生插件、PTY 输入及渲染仍属于单独的平台验收。
- 没有连接或更新 uConsole；真实实体按键、轨迹球、Wayland、fcitx、硬件解码和物理音频仍需设备复核。
