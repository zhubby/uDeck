# 用户内容默认目录

2026-11-10 的最终目录约定：

| 应用 | 默认目录 |
| --- | --- |
| Music | `~/Music` |
| Video | `~/Video` |
| Reader | `~/Books` |
| Emulator | `~/Games` |

Music、Video、Reader 没有已配置来源时，启动或刷新会自动添加相应目录并递归扫描。已有来源继续使用原配置。目录尚不存在时保持空库；创建目录并放入文件后刷新即可发现。来源和文件身份沿用现有机制，重复刷新和重新启动不会生成重复条目。

Emulator 沿用 `~/Games` 及平台子目录规则，如 `~/Games/gba/`、`~/Games/psx/`。自定义 ROM 根目录和现有游戏不变。

## 验证

- 本地相关回归、实际媒体引擎、Qt/QML 界面测试：127 项通过。
- uConsole 上运行 `tests/test_app_default_sources.py`：12 项通过，覆盖默认目录扫描、晚创建目录、来源身份恢复、自定义来源保留。
- 设备原生 Music、Video、Reader 中文界面检查通过，来源分别为 `/home/zhubby/Music`、`/home/zhubby/Video`、`/home/zhubby/Books`，QML 错误均为空。
- 正式运行的 Video、Emulator 诊断通过，模拟器仍指向 `/home/zhubby/Games`，保留原有 3 个游戏条目。
- 相关代码通过 Ruff，工作区通过 `git diff --check`。

## 实机交付

设备：`zhubby@192.168.11.59`，主机名 `clockworkpi`。保留已安装的 `udeck 0.2.3`，仅更新 `apps/common/library.py`，并为三个媒体应用保存默认来源。缺少的 `~/Video`、`~/Books` 已创建。

空闲的 Video、Emulator 正常关闭后重新启动；桌面 shell 和终端的 PID、启动时间不变。已校验其他安装文件、桌面配置及原有 `~/Games` 文件内容保持不变。

设备上的备份、部署脚本及证据位于：

```text
/home/zhubby/.local/state/udeck/deployments/content-folders-20261110-01/
  backup/package/
  backup/state/
  verification.json
  native-verification.json
  pytest.log
```

本地证据副本：

```text
/Users/zhubby/.codex/visualizations/2026/11/10/01a1c384-5855-7093-986b-878debed1b59/content-folders/
```
