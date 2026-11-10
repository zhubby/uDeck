# 首页 Bootstrap 图标与实机更新

日期：2026-11-10。首页的终端、音乐、视频、阅读器、模拟器、设置采用 **Bootstrap Icons 1.13.2**，依次使用 `terminal-fill`、`music-note-beamed`、`play-btn-fill`、`book-fill`、`controller`、`gear-fill`。

图标沿用选型预览的暖金色和彩色底板，保留卡片大小、顺序、选中边框、文字、禁用状态与按键导航。本地工作区的应用启动等待卡复用相同图标。资源、MIT 许可、原始归档校验值与颜色变换记录在 `src/udeck/assets/home-icons/`。

## 本地验证

- 首页状态、QML 导航、启动等待卡和 QML 冒烟共 **67 passed**。
- wheel 包含全部六个 SVG、许可和来源清单；包内资源与当前源码逐字节一致。从解包后的 wheel 启动安全预览，`qmlErrors: []`。
- `git diff --check` 通过；原有不相关工作区修改保持原样。

## uConsole 部署

目标为 `clockworkpi`（`192.168.11.59`），arm64 / uDeck **0.2.3**。本次作为定向界面更新部署，包版本仍为 0.2.3；没有安装工作区中的其他 Python、光标或启动动画改动。

更新范围为安装目录下的 `qml/HomeIcon.qml`、`qml/HomeScreen.qml` 和十个 `assets/home-icons/` 文件。安装前核对两个 QML 文件与当前代码基线一致，并备份原文件。实机没有安装启动等待卡组件，因此没有向设备新增该组件。

部署与回退资料保存在：

```text
/home/zhubby/.local/state/udeck/deployments/bootstrap-home-20261110-01/
```

其中 `before.json`、`backup/`、`device-payload-manifest.json`、`verification.json` 记录原始状态、备份和逐文件校验。需要回退本次界面更新时，在设备用户终端执行：

```sh
python3 ~/.local/state/udeck/deployments/bootstrap-home-20261110-01/deploy-device.py rollback
```

桌面壳重载时临时使用 `KillMode=process`，重载后已恢复原有 `control-group`；终端、视频与模拟器三个既有进程的 PID 和启动时间保持一致。服务定义、用户配置、labwc、LightDM 和默认会话配置保持原样。最终服务 `active/running`，主进程 PID 为 `1538411`，`NRestarts=0`。

实机使用安装目录中的资源完成经典主题 1280×720、黑暗主题 960×600 两组原生 QML 检查：六入口正常、返回后焦点恢复、`qmlErrors: []`。真实 Wayland 桌面已返回首页并通过 `grim` 截图；截图时短暂点亮原本处于省电关闭状态的屏幕，之后恢复原状态。

`dpkg -V udeck` 仅显示上述两个已更新 QML 与原安装包的摘要不同；整个安装目录的校验确认没有其他源文件变化。以后重新安装原 0.2.3 包会覆盖这两个界面文件。

本地交付证据与实机截图位于本聊天的 `bootstrap-implementation/` 可视化目录。本次验证不替代实体按键、轨迹球或游戏操作的人工验收。
