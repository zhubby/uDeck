# Games 代码审查修复验证

日期：2026-11-09。修复版本：uDeck 0.1.23、udeck-apps 0.1.7。

## 修复范围

1. 无内容核心的临时存档名改用 libretro 实际 `library_name`，完整保留大小写、空格和句点。原生 `Mr.Boom` 使用 `Mr.Boom.state`，不再按核心 ID 或文件扩展名规则推算。
2. Games 启动时不存在的 ROM 根目录，在用户创建后可通过刷新注册并扫描。保留已有来源身份，不自动接纳替换 inode 的来源。
3. 核心目录被替换时，同步刷新平台、搜索、详情及其父级菜单，移除旧回调；保留搜索草稿和有效操作的焦点，后台检查完成不会把“返回”焦点移到其他操作。
4. 直接运行多平台核心时保留入口平台；从全局搜索进入时选择一个已启用的平台，避免被同核心关联的首个平台错误阻止。
5. 光盘入口解析只读取每个描述文件一次，并限制 512 个不同依赖、8,192 次引用、单文件 2 MiB、合计 8 MiB。扫描、启动检查及内容哈希传递取消请求。
6. Genesis Plus GX、GX Wide 和 PicoDrive 的 Sega CD 内容必须具备至少一份区域 BIOS；同核心的 Mega Drive 卡带不受此要求影响。

## 自动化

新增回归共 **19 项**，覆盖上述六项及目录刷新后的来源稳定性、核心搜索草稿、父菜单失效回调、焦点、描述文件工作量与大小限制。先复现失败再修复，包括实机发现的 `Mr.Boom` 句点边界。

相关测试共 **80 passed**，包含英文/简体中文 × Classic/Dark 的真实 QML 输入检查。Ruff 和 `git diff --check` 通过。

最终全仓回归：**1025 passed、3 skipped、2 deselected**，347.24 秒。两项排除用例为已经在未修改 main 基线复现的 Reader 排版 Qt 对象构造失败，本次未修改 Reader；另有 13 条现有依赖弃用警告。

```sh
rtk proxy env PYTHONPATH=src:tests PYTHONDONTWRITEBYTECODE=1 QT_QPA_PLATFORM=offscreen \
  .venv/bin/python -m pytest -q -p no:cacheprovider \
  tests/test_games_catalog.py tests/test_games_management.py tests/test_games_regressions.py \
  tests/test_games_qml.py tests/test_apps_saves.py tests/test_apps_review.py
rtk proxy env PYTHONPATH=src:tests PYTHONDONTWRITEBYTECODE=1 QT_QPA_PLATFORM=offscreen \
  .venv/bin/python -m pytest -q -p no:cacheprovider \
  -k 'not test_reader_layout_menu_hides_reflow_controls_for_pdf and not test_reader_layout_menu_exposes_reflow_controls_for_epub'
```

## uConsole 原生验证

使用 ClockworkPi uConsole、Debian arm64、实际 Wayland/labwc 会话和真实 RetroArch。所有状态、原创测试 ROM 和存档位于独立证据目录，没有修改正常游戏库或用户存档。

| 内容 | 核心 | 已验证流程 |
| --- | --- | --- |
| 原创 GB | Gambatte | 启动、修改核心设置保留 PID、暂停、保存、读取、保存返回、恢复已关闭核心、进程重启续玩 |
| 原创 NES | Nestopia | 同上 |
| 原创 GBA | mGBA | 同上 |
| 无内容 2048 | 2048 | 启动、暂停、保存、读取、保存返回、进程重启续玩、正常退出 |
| 无内容 Mr.Boom | mrboom | 同上，实际状态名为 `Mr.Boom.state` |

默认原生探针完整运行通过，错误列表为空，结束后没有遗留 RetroArch 进程。GB/NES/GBA 状态大小分别为 26,672 / 5,096 / 528,472 bytes。探针先写入隔离根目录偏好，避免把设备现有 `~/Games` 一并统计。

额外尝试 The Powder Toy：核心 API 可加载，但原生启动后未在超时前报告已运行，尚未进入存档验证。该失败日志与默认通过结果分别保留，不代表其游戏兼容性或存档能力已验收。`tests/games_device_probe.py` 支持在证据目录之后附加核心 ID，以单独重现额外平台检查。

## 打包

wheel 中 **311** 个源码/资源逐项核对一致；两个 arm64 Debian 包中 **278** 个源码/资源及指南逐项核对一致。

| 产物 | SHA-256 |
| --- | --- |
| `udeck-0.1.23-py3-none-any.whl` | `69d717a94d96e41ea274b2a1b062505c99d1a69a867a527a7f26f398796c4bd6` |
| `udeck_0.1.23_arm64.deb` | `39c18e14e378fdd4d07825cc0ccdeda26c59663e0f3c6fd0c729c8ed5b58e49e` |
| `udeck-apps_0.1.7_arm64.deb` | `d35b1bfaa09fe9177c312afd88645fc1e02751f3afc10be8f6faaee289535d3d` |

## main 与 uConsole 部署

修复提交 `5c68587dd8c17fd02881f83d083ca7ae7b12825e` 已快进合并并推送 main，远端引用独立核对一致。uConsole 安装上述两个 Debian 包后，正常启动器报告 0.1.23、Games 报告 0.1.7、242 个核心、零个待检查核心，实际服务为非 Mock，无 QML 或启动器服务错误。再次核对全部 **278** 个安装资源一致。

部署只重启启动器并重开空闲 Games。Terminal PID 381833、Reader PID 3911312、Video PID 3911863 及被保护的子进程，其 PID 和启动时间均保留。Terminal 包仍为 0.1.5；输入、收藏、最近记录、语言/主题偏好及桌面配置核对保留。没有重启 compositor 或登录会话。

重启启动器期间临时设置 `KillMode=process` 保留应用，完成后恢复 `control-group`。最终没有运行中的 RetroArch。旧版两个安装包及配置备份保留于设备 `~/.local/state/udeck/deployments/games-fixes-5c68587-20261109/`，安装清单、原生报告、失败诊断及实际 Wayland 截图保留在本次任务附件中。

## 验收边界

本次确认上述原生流程及六项回归，不把已安装核心的 API 加载检查等同于所有平台可玩。实体按键、音频听感、其他核心的游戏兼容性和长时间运行仍需分别验收。
