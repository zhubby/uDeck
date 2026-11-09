# uDeck 0.2.3 模块化与单包发行

按已确认方案实施；开发阶段不兼容旧分包、不迁移旧状态，安装前卸载旧包。

- [x] 整理 common/media/music/video/browser/reader/emulator 模块及资源。
- [x] 统一 Emulator/模拟器、Reader/阅读器入口、标识和菜单。
- [x] 合并为一个 arm64 udeck 包；安装时自动设置系统默认终端。
- [x] 更新 Release 构建、安装器、软件包生命周期检查和文档。
- [x] 完成原生测试、资源及界面检查、Debian 构建与安装验证。
- [x] 审查、提交、合并 main、推送并验证远端 SHA。

发行目标：CM4 v3.1 / Debian 13 Trixie arm64，Python 3.11–3.13，Qt 6.8，labwc >= 0.9。
GitHub Actions 仅在 release: published 构建；本次不创建 Release。
保留原桌面与登录方式；默认终端切换无需验收 JSON。实机验收独立记录。
