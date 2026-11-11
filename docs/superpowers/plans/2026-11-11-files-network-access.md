# Files 网络访问实施记录

已确认：网页完整文件管理、默认共享 ~/、无需访问码、多选网络；永久默认且开机恢复，限时 1/6/12 小时且 uDeck 重启关闭。网页遵循现有 Classic/Dark、字体、Logo 和文件图标。

- [x] 独立目录边界、流式上传下载与批量任务，先验证失败用例再实现
- [x] 网络发现、精确监听、时长与永久用户服务、会话 D-Bus
- [x] Files 设置入口与真实运行状态、菜单图标、翻译
- [x] 简约响应式网页、拖拽、多选、任务和错误状态
- [x] HTTP/目录/生命周期/GUI 回归与真实浏览器截图
- [x] Wheel 资源与 Debian 服务集成检查、设备隔离传输和服务恢复验证，记录实际验收范围

实施在独立工作树 codex/files-network-access；不带入 main 中其他未提交修改。

实现和验收说明见 [Files 网络访问](../../udeck/files-network-access.md) 与 [验收记录](../../udeck/files-network-access-validation.md)。尚未构建、安装完整 Debian 包或重启整机；全量测试的既有 QML 退出告警已用未修改基线复现，详见验收记录。
