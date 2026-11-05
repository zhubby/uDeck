# uDeck 0.1.0 实机验证与现场验收

记录日期：2026-11-06，Asia/Shanghai。**实现与软件部署已完成，整机交互验收尚未完成。** 不以设备枚举、模拟事件、单元测试或 D-Bus 请求成功代替物理验收。

## 当前设备与部署

| 项目 | 实测 |
| --- | --- |
| 设备 | uConsole / Raspberry Pi CM4 / aarch64 |
| 内存 | MemTotal 约 3790 MiB |
| 系统 | Debian GNU/Linux 13.5 / Python 3.13.5 |
| 图形 | labwc 0.9.2，Wayland，Qt/PySide6 6.8.2.1 |
| 屏幕 | DSI-1 原生 720×1280，transform 270，scale 1，即横向 1280×720 |
| 窗口协议 | 实际公布 `zwlr_foreign_toplevel_manager_v1` v3 |
| 输入接口 | VID/PID 1eaf:0024；独立手柄、Keyboard、Mouse、Consumer Control 均可枚举 |
| 运行服务 | NetworkManager、BlueZ、PipeWire/WirePlumber；现有背光接口可由该用户写入 |
| 软件包 | `udeck 0.1.0 arm64` 已安装；构建产物保存在项目 `dist/` |
| 默认登录 | 未修改；原 Raspberry Pi Desktop on Wayland 保留 |

只新增运行依赖及 uDeck 包，没有执行系统升级、autoremove、固件刷写、显示管理器重启或默认登录切换。SSH 凭据没有写入仓库、软件包、部署脚本或日志。

## 已通过的软件检查

| 检查 | 结果与边界 |
| --- | --- |
| 本地测试 | 67 项通过；包含导航边界、配置、desktop entry、文件安全与 staging 权限、文件服务错误原因、输入状态、提示取消与 QML 冒烟 |
| CM4 同组测试 | 67 项通过；不能代替物理按键操作 |
| Ruff | `src tests tools` 通过 |
| Shell 语法 | `udeck-session`、会话监督脚本和 Debian 构建脚本通过 `sh -n` |
| Python wheel | 成功构建，包含 Python 模块及 QML |
| Debian 包 | arm64 构建、检查及安装成功；无用户配置覆盖或登录变更脚本；无 AppleDouble / pycache 污染 |
| QML | 五页、快捷设置、搜索和电源确认已渲染并检查截图；冒烟无 QML 引擎警告 |
| 安装版启动 | 在原桌面中以 `--windowed --no-input` 运行并自动退出，退出码 0 |
| 会话 IPC | `udeckctl home`、`switcher`、`quick-settings` 与 `doctor --json` 实际调用通过 |
| 系统只读状态 | Wi-Fi、蓝牙、音频、背光、电池五项 available，serviceErrors 为空 |
| 原生 Wayland 窗口 | 仅对自建测试窗口完成真实枚举、激活、请求关闭；窗口自行正常退出 |
| Xwayland 窗口 | 同样完成真实枚举、激活、请求关闭；不是进程列表替代 |
| 安装版文件操作 | 仅在自建临时目录验证中文新建/重命名、复制、0600 权限保留、同文件系统原子移动，以及回收站中实际数据与元数据 |
| 安装一致性 | 12 个 Python/QML 源文件与安装版逐字节一致；`dpkg --verify udeck` 无差异 |

最终软件包：`dist/udeck_0.1.0_arm64.deb`，SHA-256 为 `7e91d5dd40199556ee94ff3cab4614f8f45a8aac45fe254cd12c88382664a620`。原始软件检查记录位于 `artifacts/final-local-tests.log`、`artifacts/final-device-tests.log`、`artifacts/installed-windows.json`、`artifacts/installed-files.json` 和 `artifacts/installed-doctor.json`；这些本机产物未纳入 Git。

设备 `/tmp` 是独立 tmpfs；Gio 明确返回 `Trashing on system internal mounts is not supported`。主目录所在文件系统的回收站操作通过。界面现在保留系统错误原因；失败时源文件不动，跨文件系统移动在回收失败时保留两份副本，不做永久删除兜底。测试只清理自己创建的临时文件和对应回收站记录，没有修改用户回收站权限。

测试输出中的 13 条 DeprecationWarning 来自发行版/PyPI 的 dbus-next 对 `typing.no_type_check_decorator` 的使用；不是 QML 警告。当前支持的 Python 范围固定为 3.11–3.13，未修改第三方依赖源码。

测试期间未主动切换 Wi-Fi、配对真实蓝牙设备、改变音量/背光、锁屏、熄屏、注销、重启或关机。

## CM4 性能记录

使用安装版、真实后端、原桌面上的窗口化壳，禁用手柄输入；不是 mock，也不是完整登录/冷启动测量。`firstFrameSeconds` 是主函数内部计时到首个 `frameSwapped`，不含前置 Python 导入。额外记录 `launchToReadySeconds`：父进程启动壳到首次通过 D-Bus 观察到首帧，包含 Python 导入、进程启动及轮询开销，以这个较保守值检查启动目标。两者都不是图形登录耗时。

最终安装版 60 秒采样：

| 指标 | 目标 | 实测 |
| --- | --- | --- |
| 启动至首帧可见报告 | ≤ 5 s | 2.173 s，内部首帧计时 1.226 s |
| 壳进程 RSS | ≤ 250 MiB | 194.36 MiB，采样峰值 194.41 MiB |
| 空闲 CPU | ≤ 3% | 0.716% |
| 测量时段 | — | 60.060 s |
| 退出码 / 警告 | — | 0 / 空 |

CPU 以**单逻辑核心百分比**计算 `/proc/PID/stat` 的 user+system ticks，不除以四核。RSS 是 Python 壳进程，不是整机内存，也不包含原桌面、应用或所有共享服务。60 秒样本覆盖周期性硬件/时钟刷新，原始记录见 `artifacts/installed-performance-60s.json`。

复现：

```sh
python3 tools/measure-shell.py --seconds 60 --output artifacts/performance.json
```

完整 uDeck 登录会话、开机冷缓存、长时间运行、目录规模及真实按键连续操作的性能仍需现场记录。

## 明确未通过或未确认的部分

### 最大化几何仍未验收

额外运行 `tools/verify-windows.py --check-maximized` 时，原 rpd-labwc 会话中的 foreign-toplevel 状态报告 maximized，但测试 Qt 窗口仍渲染为 420×240，并出现 maximized/fullscreen configure 宽高为 0 的警告。**这不是最大化验收通过。** 原因尚未确定；没有把“状态位成功”当作“实际窗口几何成功”。

独立于 uDeck 窗口协议客户端，另一个自建 Qt 窗口直接调用 `showMaximized()` 也复现 420×240；Wayland 调试记录显示 `xdg_toplevel.set_maximized()` 后合成器返回 `xdg_toplevel.configure(0, 0, ...)`，而屏幕逻辑尺寸为 1280×720。证据保存在 `artifacts/direct-maximize-wayland.log`。因此问题并不只出现在 uDeck foreign-toplevel 请求路径；合成器为何给出零尺寸仍待定位，没有修改或替换合成器来绕过。

普通窗口默认最大化已经写入隔离的 labwc 规则，但独立会话下的真实尺寸、全屏优先级和模态对话框必须另行验证。默认窗口探针只检验枚举/激活/关闭，其输出明确包含 `maximizationChecked: false`。

### 无法用嵌套/无头模式替代独立登录

尝试在当前桌面旁运行独立 headless / nested labwc 验证配置，遇到 output mode test failed，退出阶段出现 139。使用不含 uDeck rc.xml 的最小对照配置也复现。因此没有宣称独立会话已通过，也没有重启或替换当前运行的 labwc 来绕过问题。

这些实验只操作额外 compositor 进程，当前桌面仍运行；真正的登录、退出及返回原桌面需要现场保存工作后验收。

### 物理与外部服务仍需人参与

当前没有人手实际按下方向键/ABXY，因此没有保存猜测映射，也没有通过模拟事件宣称校准成功。真实 Wi-Fi 切网、蓝牙配对/重连、蓝牙音频播放、中文输入、轨迹球混用与电源动作均未完成物理验收。

## 原配置与资料保护

以下文件部署前后 SHA-256 相同：

| 文件 | SHA-256 |
| --- | --- |
| `~/.config/labwc/autostart` | `5e40c3a5c12675fe659232b065bed382a750ac3eaed3a269f3468740eb8f9ea2` |
| `~/.config/labwc/environment` | `f9ed2b9465062959ce26d3247fd52d3a42c2d1e1e342a5a5c0572fbc1fd35499` |
| `~/.config/labwc/rc.xml` | `e1400ca3fa74c21a4ba7e17a0a51e05cd69890777ab1032cca0c31979ed4e0df` |
| `~/.config/labwc/themerc-override` | `6e3b7c39e9b353106a2f9a6121a8fa839b385405b7458fbabb3a85dff212e33c` |
| `/etc/lightdm/lightdm.conf` | `8db14749508a5cb8500e67a3f0bffbdd39f6f2bcecd2d1b35bb607f78796fb52` |

硬件参考原件与原 `docs/uconsole` 保留。硬件资料清单共有 215 项；由于根 README 加入项目使用说明，仅更新清单中 README.md 对应的摘要，其他摘要不变。更新前完整清单保存在 `artifacts/SHA256SUMS.before-udeck`；旧 README 摘要为 `d6381e3a3a6a737272bcd9db4f3435dcc52ab9742eea98b200ebdf1461637788`。

没有创建 Git 分支、提交或推送，也没有暂存现有未提交内容。

## 现场验收清单

### 1. 原桌面上的非破坏性检查

- [ ] 启动 `udeck --windowed`，用键盘进入设置，完成上/下/左/右/A/B/X/Y 八步实按校准。
- [ ] 记录实际事件节点、key/axis code 与方向；检查长按方向重复、ABXY 不重复确认。
- [ ] 普通 j/k/u/i 字母正常输入，不触发全局按钮；切出 uDeck 后第三方应用可接收独立手柄。
- [ ] 五页、空列表、滚动底部、目录返回、弹层关闭和切页的焦点恢复正确。
- [ ] 实体键盘输入中文；Esc 取消输入法候选与取消弹层不互相误触；轨迹球单击/双击混用。
- [ ] 启动普通应用与终端应用，切换真实窗口，关闭带未保存内容的应用时保留其自身确认。
- [ ] 在自建测试目录中验证新建、中文重命名、复制、移动、覆盖取消、回收站及权限失败。

### 2. 独立登录会话

- [ ] **用户确认当前工作全部已保存**，具备本机屏幕/键盘操作和 SSH 回退条件。
- [ ] 从登录界面选择 uDeck，不通过 SSH 重启 LightDM 或强改默认会话。
- [ ] 横屏保持 1280×720；没有重复的原面板/桌面管理器；fcitx5 与权限认证正常。
- [ ] `Ctrl+Alt+Esc` 从原生 Wayland / Xwayland 应用返回桌面；窗口切换器真实切换焦点。
- [ ] 实际检查普通主窗口最大化后的像素尺寸，全屏应用和模态对话框不被错误最大化。
- [ ] 退出 uDeck 后可从登录界面返回原 Raspberry Pi Desktop on Wayland。

### 3. 无线与电源：单独现场安排

- [ ] 另有可恢复网络/现场输入通路后，才测试 Wi-Fi 开关、扫描、已保存网络和新密码连接。
- [ ] 真实蓝牙设备完成发现、确认/PIN/passkey 配对、连接、断开、移除及重新连接。
- [ ] 分别记录 Paired、Connected、ServicesResolved；蓝牙音频另测实际播放，不以连接成功替代。
- [ ] 音量、静音、输出切换与亮度实测；电池容量/充电状态与设备实际一致。
- [ ] 锁屏后可用登录密码解锁；熄屏后按键/轨迹球可恢复，且不误称系统休眠。
- [ ] 保存工作后分别验证注销、重启、关机与再次进入原桌面；不在唯一 SSH 通路上自动执行。

只有这些现场项目完成后，才能把本记录升级为“整机日常桌面验收通过”。
