# uDeck 0.1.5 多无线网卡

日期：2026-11-06，Asia/Shanghai。

## 使用

设置 → Wi-Fi，或 Y → Wi-Fi，先选择“内置无线网卡”或“USB 无线网卡”，再管理对应的网络。接口名始终显示，总线信息无法确认时使用通用“无线网卡”名称。

- 网卡列表展示每张卡的连接状态；状态栏汇总网卡数和已连接数。
- 单张网卡可搜索网络、选择兼容的已保存网络、输入密码连接，以及断开连接。
- “关闭全部 Wi-Fi”影响所有网卡，需要确认；开启后仍分别选择网卡管理。
- B 逐层返回并恢复网卡选择。连接确认、扫描和连接后的状态刷新保留当前菜单。
- USB 网卡拔出时移除相关网卡和确认/密码弹层，返回网卡列表；其他网卡和菜单保留。

同名 SSID 按网卡分别展示。另一张网卡正在使用且只允许单处激活的配置会标注占用原因并禁用；从扫描列表连接时可以创建独立配置，按原密码流程获取凭据。不会主动断开另一张网卡，也不更改路由优先级。企业网络、VPN 和热点仍不属于本次支持范围。

## 验证方式

- 后端测试覆盖两张网卡、同名 SSID、目标校验、设备/AP 消失、局部错误、兼容配置过滤、防配置抢占和密码期间移除设备。
- 控制器测试覆盖逐层返回、焦点保持、确认目标、扫描后留在菜单、总开关确认、密码层取消及已连接但暂时读不到 SSID。
- QML 使用真实界面和安全 Mock，分别在 1280×720、960×600 检查双网卡、单网卡、无网卡、关闭、网卡详情、已保存网络、连接确认、移除和超长网络名。检查弹层边界、真实 Escape 路由和 QML 警告。
- 截图探针：`PYTHONPATH=src QT_QPA_PLATFORM=offscreen QT_QUICK_BACKEND=software .venv/bin/python tests/wifi_qml_probe.py adapters artifacts/wifi-adapters.png`；将 `adapters` 替换为 `networks`、`confirm`、`saved`、`off`、`single`、`empty`、`unplug`、`long-name` 可复现对应场景。

## 实机记录

已连接用户提供的 uConsole，系统为 Debian arm64、NetworkManager 1.52.1、Qt/PySide6 6.8.2.1。更新前安装版本为 uDeck 0.1.4。

初始状态：`wlan0` 为 brcmfmac 内置网卡，未连接；`wlan1` 为 rtl8xxxu USB 网卡，已连接。SSH 使用 `wlan1`。后续验证保留该网络通路。

真实扫描、安装、运行截图和现场验收分别记录；模拟测试不替代物理插拔或现场按键验收。

### 自动化结果

| 检查 | 结果 |
| --- | --- |
| 本地完整 pytest（审查修复后） | **242 通过、2 跳过**；跳过项为开发机未安装的原生终端插件测试 |
| uConsole 定向 pytest（审查修复后） | **57 通过**，包含 Wi-Fi 后端、控制器和原有后端/界面测试 |
| Ruff：`ruff check src tests tools` | 通过 |
| QML Wi-Fi 渲染 | 9 个场景 × 2 种尺寸，共 **18 项通过**；弹层边界、Escape 返回及 QML 警告检查通过 |
| 完整壳 QML 冒烟 | `--mock --windowed --smoke-test` 通过，`qmlErrors: []` |
| 代码检查 | `git diff --check` 通过；逐项核对设备目标、配置占用、密码后校验和菜单栈 |

两处 pytest 均有 dbus-next 的 13 条既有 Python 弃用警告。额外覆盖 NetworkManager `DeviceAdded` / `DeviceRemoved` 信号触发刷新，以及查看内置网卡时插入 USB 网卡仍保留原菜单和焦点。

完整测试复现命令（项目测试环境）：

```sh
QT_QPA_PLATFORM=offscreen QT_QUICK_BACKEND=software QT_QUICK_CONTROLS_STYLE=Basic \
  PYTHONPATH=src .venv/bin/python -m pytest -q --tb=short
.venv/bin/ruff check src tests tools
QT_QPA_PLATFORM=offscreen QT_QUICK_BACKEND=software PYTHONPATH=src \
  .venv/bin/python -m udeck.main --mock --windowed --smoke-test --quit-after 2
```

### 实际设备与界面

2026-11-06 在 `192.168.11.59` 检查：

| 网卡 | 实际设备总线 / 驱动 | 界面状态 | 通过界面菜单扫描后的 LastScan |
| --- | --- | --- | --- |
| `wlan0` | 内置 / brcmfmac | 未连接，0 个兼容配置 | `79851963 → 79864879` |
| `wlan1` | USB / rtl8xxxu | 已连接，1 个兼容配置 | `79378748 → 80050760` |

通过原有 `VirtualInput` 向 Wayland 合成器发送方向键、Enter 和 Escape，再用 `grim` 截取实际 1280×720 屏幕；未安装额外输入工具。已检查两张卡的详情、已保存网络、连接确认、单卡断开确认、全部 Wi-Fi 关闭确认和逐层返回。所有确认均取消。扫描后菜单保留，USB 活动连接路径仍为 `/org/freedesktop/NetworkManager/ActiveConnection/2`，SSH 仍走 `wlan1`。

普通 SSH 进程首次扫描被 NetworkManager 权限检查拒绝；在与桌面一致的用户服务上下文中，两张网卡扫描均完成，随后实际界面菜单扫描也完成。没有修改 polkit 规则。保留最初失败与后续成功的探针结果，避免将 root 扫描结果当作普通桌面权限的验证。

本地截图和原始记录位于当前工作树的 `artifacts/`（不随源码包提交）：

- [实机网卡列表](../../artifacts/wifi-live-adapters-final.png)、[内置网卡网络列表](../../artifacts/wifi-live-builtin.png)、[USB 网卡网络列表](../../artifacts/wifi-live-usb.png)。
- [实机连接确认](../../artifacts/wifi-live-connect-confirm.png)、[单卡断开确认](../../artifacts/wifi-live-disconnect-confirm.png)、[全局关闭确认](../../artifacts/wifi-live-power-confirm.png)。
- [Mock 网络列表](../../artifacts/wifi-networks.png)、[Mock 连接确认](../../artifacts/wifi-confirm.png)、[超长 SSID](../../artifacts/wifi-long-name.png)。
- `wifi-device-scan.json`：普通 SSH 权限失败；`wifi-device-scan-user-session.json`：用户服务扫描成功；`wifi-live-menu-scans.json`：实际界面菜单扫描与连接路径保持记录。
- `wifi-installed-verification.json`：安装版本、运行健康、文件哈希、配置保持和 SSH 路由；`wifi-real-ui-probe.py`：本次实际界面导航探针。

### 首次安装与回退（审查前）

已在 CM4 原生构建 `dist/udeck_0.1.5_arm64.deb`，通过 apt 将 **uDeck 0.1.4 升级到 0.1.5**，未新增或移除依赖包。仅重启既有 `udeck-fullscreen.service`，未重启合成器或登录会话。

安装包 SHA-256：

```text
09244d7c02a13d7bd2e526f8ba5825e348673cd0c059bc521d1a8243eb4deacd
```

`udeckctl doctor --json` 确认安装版本与运行壳均为 **0.1.5**，`mock: false`、`ready: true`，五项服务可用，`serviceErrors: {}`。`dpkg -V udeck` 无差异；安装后的 Wi-Fi、后端、控制器、Mock 和 QML 文件哈希与当次工作树源文件一致。uDeck 设置、LightDM 配置及 labwc 的 `rc.xml` / `autostart` / `environment` 与升级前哈希一致，输入校准和原桌面配置保留。工作区既有输入、终端及会话源码也保留在基线中。

远端回退文件位于 `/home/zhubby/.cache/udeck-multi-wifi-20261106/backup/`，包含原 `udeck_0.1.4_arm64.deb`、设置副本和升级前清单；目录为 0700、设置副本为 0600。需要回退时安装此旧包，再重启同一用户服务。

### 代码审查与修复

按用户 AGENTS.md 在主线程顺序审查，覆盖后端、控制器、QML、Mock、测试和文档；合并基线为 `0eb3101`。审查确认以下问题并全部修复：

| 级别 | 位置 | 问题与影响 | 修复及验证 |
| --- | --- | --- | --- |
| P1 | `NetworkAgent.GetSecrets` | 共享或未映射的配置可打开没有 `deviceId` 的密码层，网卡拔出时无法正确归属，输入后也未复核配置归属 | 输入前后解析实际网卡并检查存活；优先使用唯一正在激活的设备，无法确定时拒绝请求；覆盖普通请求、多连接配置、读取失败和输入期间归属变化 |
| P2 | `NetworkAgent.CancelGetSecrets` | 旧配置的取消回调会取消同一网卡上另一条密码输入 | 按配置分组取消，另存弹层的网卡归属用于拔插处理；测试确认同卡新密码和另一张卡的密码保留 |
| P2（继承问题） | `_saved_wifi` | 热点、Ad-hoc 或 Mesh 配置可因 SSID 和认证方式相同而被当作普通连接复用 | 只纳入 infrastructure 客户端配置；三种模式均验证创建独立客户端连接 |

先补回归测试：密码相关的 6 个用例和三种非客户端模式用例均在修复前失败；修复后连同正常多连接密码流程全部通过。最终没有未处理的代码审查问题，现场验收项目继续单独保留。结构化记录见 [findings.json](../../.context/compound-engineering/ce-review/2026-11-06-multi-wifi/findings.json)。

审查后的构建仍为首次主线提交前的 **0.1.5**，已原生重建并通过 `apt-get --reinstall` 更新 uConsole，仅重新安装 uDeck、重启原用户服务。最新本地包 `dist/udeck_0.1.5_arm64.deb` 的 SHA-256：

```text
c841b08f83b2e78e45b3c57c11f905767888c8d67d6de1f995c7e64317945105
```

重新核对安装后的五个文件与当前源码哈希一致，`dpkg -V udeck` 无差异，运行壳 `ready: true`，五项服务正常，全部已核对配置哈希保持。已用安装后的后端再扫描两张真实网卡：`wlan0` 的 LastScan 为 `81424963 → 81479404`，`wlan1` 为 `80050760 → 81483253`；USB 连接及 SSH 路由保留。原始记录在 `artifacts/wifi-review-installed-verification.json` 和 `artifacts/wifi-review-device-scan.json`。

审查前的 0.1.5 包另存为远端 `backup/udeck_0.1.5_before_review_arm64.deb`，原 0.1.4 回退包和设置备份也保留。

### 尚待现场验收

- [ ] 分别真实连接、断开两张网卡，观察另一张卡连接及实际上网路由。
- [ ] 拔出正在查看的 USB 网卡，确认退回列表并关闭对应确认/密码层；重新插入后确认自动出现。
- [ ] 在物理 ABXY 与方向键上确认逐层返回和焦点保持。
- [ ] 实际关闭、重新开启全部 Wi-Fi。

本次远程连接唯一通路为 USB 网卡，内置网卡没有可直接使用的已保存配置，也未取得其网络密码。因此没有执行会切断该通路的断开、全局关闭或物理拔插，也没有取出已有 Wi-Fi 密钥代替现场输入。相应逻辑已由自动化覆盖，以上现场项目仍未通过实物验收。
