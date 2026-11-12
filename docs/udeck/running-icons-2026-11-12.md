# Running 与首页的内置应用图标统一

日期：2026-11-12。

## 问题与修复

首页通过 `HomeIcon.qml` 显示 Bootstrap SVG，并由 `ThemePalette.artwork()` 提供应用底色；Running 将窗口的 `appId` 交给系统图标主题，Apps 也直接读取桌面主题图标。因此同一个内置应用在不同页面的图形、颜色和底板不一致。

新增 `ApplicationIcon.qml`，按六款内置应用的完整 ID 识别终端、音乐、视频、阅读器、模拟器和浏览器，复用首页的 `HomeIcon`、底色、圆角和图形比例。Running 与 Apps 共用该组件；其他图标沿用桌面图标提供器，设置图标继续按当前主题着色。

## 验证

- 图标对照探针通过 `WindowService.entries()` 构造实际格式的窗口条目，比较首页、Apps 和 Running 的 SVG 来源及底色。修复前六款应用均不一致；修复后经典主题 1280×720、黑暗主题 960×600 均通过，第三方图标来源及 QML 错误检查正常。
- 本地既有首页、QML 导航和设置相关回归 **65 passed，110.93 秒**。
- CM4 / Qt 6.8.2 上候选源码完成上述两组图标对照；系统安装路径另完成经典主题对照，QML 错误均为空。
- `uv build` 成功；wheel 与源码包中的两个 QML 文件均与工作区逐字节一致。
- 已检查实际 Wayland 首页和 Running 截图，Running 显示首页同款图标与底色。

原始探针、截图、JUnit 与部署证据保存在 ignored 目录 `artifacts/running-icons-2026-11-12/`。设备导出归档含 14 份文件，134,058 字节，SHA-256 为 `635cdc920333fe178a226da7e3ea5c35843838eae67688c7df78141012b0a290`；传输后核对归档和全部成员校验值。

## 设备更新与会话中断

在已有 0.2.3 安装上定向更新 `qml/Main.qml`，新增 `qml/ApplicationIcon.qml`，安装前备份原文件并逐项核对哈希。版本仍为 0.2.3；`dpkg --verify udeck` 仅报告本次 `Main.qml` 的预期摘要差异。新组件已包含在后续 wheel / 源码构建中。

本轮重载发生了实际中断：原会话的管理脚本只允许三次 Shell 启动，此前已用完额度；终止第三个 Shell 后，管理器和 compositor 退出，原 Browser、Music、Video、Reader、Emulator 随之关闭。原始 `live-shell.json` 保留失败，不能将原进程保持记为通过。

通过正常 LightDM 登录界面恢复 uDeck，会话为 93，Shell PID 为 2704635；重新打开上述五款应用，验证窗口协议、五项系统服务、已校准输入和全局快捷键，错误为空，Raspberry Pi Connect 的 WayVNC 服务为 `active`。安装前后的 11 个受保护配置哈希一致。原进程及未保存窗口状态未保留，不能以重新打开应用替代这一事实。

设备原文件备份与回退脚本位于 `/var/tmp/udeck-running-icons-20261112/`。需要回退文件时执行：

```sh
sudo python3 /var/tmp/udeck-running-icons-20261112/install-icons.py --rollback
```

本轮实机图标验证不替代实体按键、中文 IME、实际音画和整机重启验收。
