# Games 多平台验证记录

日期：2026-11-09。版本：uDeck 0.1.22、udeck-apps 0.1.6。使用方式见 [Games 指南](games.md)。

## 自动化与界面

- Games 目录、核心选择、固件组合、存档迁移、扫描取消和目录切换竞争，以及现有存档/应用回归：**61 passed**。
- QML 以真实 Qt 键盘事件覆盖英文/简体中文 × Classic/Dark，检查目录选择取消、核心开关、长列表滚动、确认键消费及焦点恢复；没有 QML 警告。使用与启动器一致的 Basic 控件样式。
- 全仓回归：**1005 passed、3 skipped、2 deselected**，335.90 秒，13 条现有依赖弃用警告。两项 Reader 排版测试因 `object.__new__(ReaderController) is not safe` 在相同 Python/Qt 环境下失败，已在未修改的 main 基线复现，本次不修改 Reader。新增的不可读目录回归另包含在上述 61 项中。
- 原始全量运行还出现一次文件图标子进程缺少 `PYTHONPATH`；显式传入 `PYTHONPATH=src` 后 98 项文件图标测试通过，修正后的全仓命令也通过该部分。
- 所有变更 Python 文件的 Ruff 检查及 `git diff --check` 通过。

```sh
rtk proxy env PYTHONPATH=src QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest \
  tests/test_games_catalog.py tests/test_games_management.py tests/test_games_qml.py \
  tests/test_apps_saves.py tests/test_apps_review.py -q
rtk proxy env PYTHONPATH=src QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q \
  -k 'not test_reader_layout_menu_hides_reflow_controls_for_pdf and not test_reader_layout_menu_exposes_reflow_controls_for_epub'
```

## uConsole 原生检查

目标设备为 ClockworkPi uConsole、Debian 13 arm64、Wayland/labwc，实际输出为 1280×720。

实际安装的 **242 个核心全部完成独立子进程 libretro API 加载检查**，映射为 **149 个平台/引擎分组**，未映射核心为零。该结果仅代表加载检查，不代表全部核心的游戏兼容性。检查使用与 RetroArch 相同的延迟本地加载方式，并提供前端全局库；不运行 `retro_init`，因此也不在探针退出时运行依赖初始化的静态析构。

| 原创测试内容 | 核心 | 即时存档大小 | 原生流程 |
| --- | --- | --- | --- |
| GB 条纹程序 | Gambatte | 26,672 bytes | 启动、修改设置保留 PID、暂停、保存/读取、保存返回、恢复已关闭核心、进程重启续玩 |
| NES 图块程序 | Nestopia | 5,096 bytes | 同上 |
| GBA 红色画面程序 | mGBA | 528,472 bytes | 同上 |
| 无内容 2048 | 2048 | 已生成状态 | 直接运行核心、暂停、保存、正常退出 |

测试内容由 `tests/game_fixtures.py` 生成，不包含商业 ROM、BIOS 或主机标志。`tests/games_device_probe.py` 在指定证据目录中运行真实 RetroArch，并记录进程、存档元数据及实际 Wayland 输出；结果错误列表为空。探针结束后没有遗留 RetroArch 会话。

## 打包

wheel 构建完成，**311** 个包内源码/资源与工作树一致。两个 Debian 包中共 **277** 个安装资源与构建源码一致，包括所有新模块、平台注册表、中英文、QML 和 Games 指南。

| 产物 | SHA-256 |
| --- | --- |
| `udeck-0.1.22-py3-none-any.whl` | `ce17902ccf790b999fcfb597b63c14608f5af4208cf5bba1c61d006cd4edb873` |
| `udeck_0.1.22_arm64.deb` | `80a7e01832e9d731b134383adcecd755d23b7c012d3d11a1b9693cc6ec9a8cb7` |
| `udeck-apps_0.1.6_arm64.deb` | `fd0ad63e3ffa998418682bd13d404cfcf4c0cbdb5de2d2290edb78ebd7b74658` |

## 部署与实际界面

功能提交 `e90e79a967f7123aa3da8bab523dd2f1ca4585a3` 已快进合并并推送 main，远端引用独立核对一致。uConsole 已安装上述两个 Debian 包，实际启动器报告 0.1.22、Games 报告 0.1.6，无 QML 错误；277 个安装资源再次逐项核对一致。Terminal 包保持 0.1.5。

部署后的正常 Games 进程通过真实 Wayland 虚拟键盘逐一进入 **149 个分组、242 个核心的详情页**，每个核心均有可操作的开关入口。实际菜单还完成了平台目录创建、GBA 备用核心启用后关闭、目录选择取消、鼠标进入父目录后取消，以及长列表滚动。事件自动化等待菜单状态变化后再继续；这些是软件输入检查，不替代实体按钮验收。

三份原创程序已放入 `~/Games/gb`、`~/Games/nes`、`~/Games/gba`，实机正常库能识别三个平台。平台目录由设置中的显式创建操作生成；已有文件保留。

只关闭并重开了空闲 Games。Terminal PID 381833、Reader PID 3911312、Video PID 3911863 及四个 Reader 子进程的 PID/启动时间均保持，结束时没有运行中的 RetroArch。启动器重启期间临时使用 `KillMode=process` 保留应用，随后恢复 `control-group`；没有重启 compositor 或登录会话。输入、收藏、最近记录、English/Classic 偏好与桌面配置均核对保留，屏幕恢复原来的关闭状态。

旧版两个包及配置备份位于设备 `~/.local/state/udeck/deployments/games-e90e79a-20261109/`。完整安装清单、原生测试、核心入口遍历报告和截图原图保留在本次交付附件中。

以下为设备实际 Wayland 输出，英文/Classic、1280×720，保留原始 PNG，没有裁剪或重绘：

| 页面 | 实机截图 |
| --- | --- |
| 多平台库 | [GB、GBA、NES 原创程序](screenshots/games-multiplatform-library-uconsole.png) |
| 设置 | [ROM 根目录、平台目录、核心与固件设置](screenshots/games-multiplatform-settings-uconsole.png) |
| 核心管理 | [242 个核心的平台分组与滚动选择](screenshots/games-multiplatform-core-management-uconsole.png) |
| 平台核心 | [GBA 推荐与备用核心状态](screenshots/games-multiplatform-gba-cores-uconsole.png) |

## 验收边界

本次没有将 242 个核心的 API 加载成功描述为全平台实测。其他平台的实际游戏、不同区域/型号的 BIOS、具体图形后端及性能仍需按平台验证。实体方向键/ABXY/肩键、音频听感、长时间运行和物理存储拔插也需要现场验收。原创程序与自动化输入证明相应启动/存档流程，不替代这些现场项目。
