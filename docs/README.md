# uDeck 文档

这里描述当前产品和源码契约。
按日期记录的旧计划、发布流水和验收附件由 Git 历史追溯。
文档中的检查步骤不代表当前设备已经通过验收。

## 使用与维护

- [使用指南](udeck/README.zh-CN.md)：运行环境、桌面操作与会话恢复。
- [安装与发行](udeck/debian-distribution.md)：Debian 单包、升级、卸载与 Release。
- [输入与快捷键](udeck/input.md)：物理按键、轨迹球、校准和快捷键恢复。
- [文件工作区](udeck/files.md)：浏览、格式关联、传输与回收站。
- [共享](udeck/sharing.md)：SMB 服务与网络授权。
- [网页文件访问](udeck/files-network-access.md)：目录、传输和开放时长。
- [内置应用](apps/README.md)：Music、Video、Browser、Reader 和 Emulator。
- [模拟器](apps/emulator.md)：列表、核心、RetroArch 原生存档和 rclone。
- [Terminal](udeck/terminal.md)：PTY、输入、默认终端和原生插件。
- [Console](console/README.md)：应用身份、资源统计和退出。

## 产品设计

- [应用交互](design/app-suite/README.md)：应用结构、交互规范和原生接入。
- [语言、主题与字体](design/appearance.md)：跨窗口偏好和视觉资源。
- [系统设置](design/system-settings.md)、[Wi-Fi](design/wifi-management.md)、[无线状态](design/wireless-status.md)。
- [电池与音频](design/power-audio.md)、[按键提示](design/input-prompts.md)、[交互音效](design/interface-sounds.md)。
- [品牌标识](design/branding/README.md)：正式 Logo 与主题配色。
- [动效与响应](motion/README.md)：短过渡、输入连续性和后台负载约束。

## 技术与验证

- [架构](udeck/architecture.md)：模块、服务、应用路由与数据边界。
- [开发](udeck/development.md)：固定工具链、依赖和测试入口。
- [验证](udeck/validation.md)：源码、安装包与物理验收的证据边界。
- [uConsole 硬件概览](uconsole/硬件概览.md)与[资料索引](uconsole/资料索引.md)：上游资料快照及来源。

## 文档维护

功能说明使用稳定文件名，并随实现更新。
跨模块规则由架构文档说明，模块文件清单由各级 `AGENTS.md` 说明。
许可证、上游固定版本和正式截图的来源记录随资源保留。
构建身份、测试日志和设备采样写入本次 `artifacts/` 目录。
不要用旧测试数字或旧设备状态描述当前验收结果。

[PROTOCOL]: Update this header on change, then check AGENTS.md
