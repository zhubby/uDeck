# 输入与快捷键

## 按键所有权

桌面使用方向键选择，A 确认、B 返回、X 操作、Y 快捷设置。
L/R 切换页面，弹层打开时不切页，到边界停止。
键盘等价为 Enter、Esc、F10、F1、PageUp/PageDown。
普通 A/B/X/Y 字母只输入文字。
内置应用使用各自的按键表，见[应用说明](../apps/README.md)和[Terminal](terminal.md)。

`Gamepad` 只打开已确认 uConsole 身份的独立手柄接口。
它排除普通键盘、鼠标和 Consumer Control。
已确认固件 `1eaf:0024:20230713` 的映射为
A=289、B=290、X=288、Y=291；已保存的自定义映射优先。
未知固件在设置中按顺序校准方向和 ABXY。
校准不刷写固件，不独占整个键盘。
映射完整不代表实体按键验收通过。

独立会话根据合成器报告的前台窗口交接手柄。
应用先请求桌面释放输入，再确认接管并显示窗口。
Qt 确认前台焦点后才投递准备阶段的排队事件。
交接期间已按住的按钮必须松开后重按。
返回主页不主动最小化应用，避免竞争桌面焦点。
RetroArch 接收原生游戏输入；桌面通过全局快捷键提供返回和暂停。

## 轨迹球与 L/R

`PointerGuard` 在真实全屏模式接管独立鼠标接口。
内置鼠标左右按钮代表 L/R，与光标位置无关。
外接鼠标不成为切页键。
独立 labwc 配置阻止内置鼠标原始事件重复投递。
窗口化、mock 和 `--no-input` 不接管其他窗口的鼠标。

机身轨迹球每个原始计数转换为 4 px 相对位移。
横纵轴按 `SYN_REPORT` 合为一帧，按钮边沿前先刷新位移。
半帧跨读取保留，事件丢失、断开和输入暂停时丢弃。
`TrackballInput` 向 `VirtualInput` 提交完整双轴相对向量。
合成器维护全局坐标；桌面和应用共用这条链路。
方向键指针模式也提交相对移动，切换时不跳回旧坐标。
原始诊断信号仍报告设备计数。

轨迹球中键松开不超过 2 秒产生左键；超过 2 秒产生一次右键。
桌面将这两种点击解释为当前选中项的确认和上下文菜单。
应用按自己的鼠标策略接收点击。
Terminal 仍消费内部点击和滚轮，复制使用历史选择模式。
诊断、校准、窗口交接、锁屏和失活会取消未完成手势。

`PointerCursor` 从 Qt 鼠标事件读取显示坐标，不再累加原始位移。
圆点直径 8 px，外环 20 px；移动不插值、不拖尾。
按下收紧，释放播放一次扩散环，动画结束停止刷新。
静止 3 秒隐藏；按住暂停计时，键盘导航和失焦立即隐藏。
绘制层不截获输入，减少动画模式直接切换状态。
轨迹球实际传感器方向和滚动手感须在设备上实测。

## 应用兼容模式

兼容输入需要经过身份校验的独立 uDeck 会话。
按键模式注入 Enter、Esc、Shift+F10 和 Shift+Tab/Tab。
指针模式以方向键移动，A 左键、X 右键、L/R 滚动。
Y 打开应用控制菜单，模式按 app_id / WM_CLASS 保存。
子对话框继承父窗口配置。
六个内置应用使用自己的原生输入，不切换到全局兼容按键或指针模式。
方向键隔离经 labwc 重载与 F24 代次回执确认后才启用。
失败留在菜单，设备断开、锁屏和失焦释放注入状态。
界面的启动与激活仍遵守[内置应用路由](architecture.md)。

## 全局快捷键

| 动作 | 默认组合键 |
| --- | --- |
| 控制面板 | Ctrl+Shift+Esc |
| 主页 | Ctrl+Alt+Esc |
| Console 窗口列表 | Ctrl+Alt+Tab、Alt+Tab、Alt+Shift+Tab |
| 应用 / 文件 / 设置 | Ctrl+Alt+A / Ctrl+Alt+F / Ctrl+Alt+, |
| 快捷设置 | Ctrl+Alt+S、电源键 |
| 切换输入法 | Ctrl+Alt+空格 |
| Terminal | Ctrl+Alt+T |
| 关闭当前窗口 | Alt+F4 |
| 游戏暂停菜单 | Ctrl+Alt+M |
| 截屏 | Ctrl+Alt+P、PrintScreen |
| 锁屏 / 熄屏 | Ctrl+Alt+L / Ctrl+Alt+B |
| 音量 / 静音 / 亮度 | 对应系统媒体键 |
| 注销 / 重启 / 关机 | 默认未绑定 |

系统设置的快捷键绑定支持录制、别名、清除和恢复默认。
输入法快捷键在 Fcitx 5 当前组的已启用成员间循环，保留应用焦点。
如果旧配置已占用 Ctrl+Alt+空格，输入法快捷键默认留空。
冲突转移需明确确认；危险电源动作仍打开默认取消的确认框。
录制在独立窗口中暂停该窗口的全局绑定。
失焦、关闭或 15 秒超时退出录制，F23/F24 保留给内部协议。

绑定保存到 `$XDG_CONFIG_HOME/udeck/shortcuts.json`。
未设置 XDG 时使用 `~/.config/udeck/shortcuts.json`。
缺少动作使用默认值，显式空数组表示禁用。
首次在真实 labwc 会话运行时备份并接管全部键盘绑定。
这也适用于真实窗口化运行；安装包和 mock 预览不接管。
备份位于 `$XDG_STATE_HOME/udeck/shortcuts/`，默认根为 `~/.local/state`。
XML 原子写入、目标进程重载和代次确认成功后才保存 JSON。
失败回滚本次写入，不覆盖外部修改。

恢复原桌面快捷键时，先退出 uDeck。
从诊断中的 shortcuts 字段确认备份和实际 `rc.xml` 路径。
将匹配备份恢复后，重载对应 labwc。
重新运行 uDeck 会按保存的绑定再次接管。
恢复全部默认只恢复 uDeck 的默认表。

```sh
udeckctl doctor --json
udeckctl bind-console
udeckctl screenshot
```

`bind-console` 请求运行中的壳重载，不离线修改配置。
截屏通过 grim 验证 PNG，再保存到 XDG 图片目录的 Screenshots。
输入诊断和设备验收见[验证规范](validation.md)。

[PROTOCOL]: Update this header on change, then check AGENTS.md
