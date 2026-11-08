# 按键测试迟到事件去重修复

日期：2026-11-08。基于 `main` 的 `8a4f07b`，主程序保持 **0.1.19**。

## 审查问题与修复

之前仅在按住期间合并原生 evdev 与 Qt 事件。当原生或 Qt 的完整按下／松开批次先到达时，一次点按会计为两次。原生已松开后，迟到且没有对应松开的 Qt 按下还会残留高亮；Esc 会重新启动长按退出计时。

观察器现在根据实际打开的 uConsole Keyboard／Consumer 接口能力报告可读键位。只要对应接口仍可读，这些键位持续由原生报告处理，包括两次按压之间；相同键位的 Qt 影子事件被忽略。更新覆盖范围时只清除对应键位的 Qt 按住状态，保留其他键位的输入。

接口拔出、读取失败或停止观察时释放其覆盖范围；未被覆盖及权限不足时的键位继续使用 Qt。主程序接入覆盖状态信号，观察范围仍由前台诊断页控制。

## 自动化验证

- 新增 **13 项回归**，覆盖六种合法事件顺序、连续快速点按、缺少松开的迟到 Qt Esc、部分键位覆盖、Qt 影子状态清理、Reader → 控制器 → Qt 事件过滤器集成、拔出与能力读取失败。
- 完整测试：**714 passed、2 skipped**，耗时 278.17 秒。两个跳过项需要原生 QMLTermWidget 插件；另有 13 条 `dbus_next` 弃用警告。
- Ruff 与 `git diff --check` 通过。
- `--mock --windowed --no-input --smoke-test` QML 冒烟通过，`qmlErrors` 为空。
- 隔离环境 wheel 构建通过。容器内 arm64 Debian 构建与包元数据检查通过。
- wheel 的 **199** 个源码／资源文件、Debian 主包的 **157** 个源码／资源文件均与工作区逐字节一致。

完整测试命令：

```sh
rtk proxy .venv/bin/python -B -m pytest -q -p no:cacheprovider --junitxml=artifacts/key-test-event-fix-2026-11-08/pytest.xml
```

包校验结果位于忽略目录 `artifacts/key-test-event-fix-2026-11-08/package-verification.json`。

```text
udeck-0.1.19-py3-none-any.whl
 6c4a290e45d05ac488e9802a10c06cdb3284dd34e56aa765edceb21d2e6f881d
udeck_0.1.19_arm64.deb
 454b5029ed09cd44b2ddfbfee5b74b09ee77edbd5b8e16c079d0567d843b00dc
```

## 现场验收边界

本次完成软件回归与打包检查，未重新安装设备或进行实体逐键按压。此前 0.1.18 的截图、安装与只读设备核对保留在 `full-key-test-2026-11-08.md`；这些记录不代表本次修复的现场验收。
