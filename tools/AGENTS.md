# tools/
> L2 | Parent: ../AGENTS.md

benchmark-app-state.py: 控制器状态更新基准；不计 QML 解析和渲染。
build-deb: shell 构建入口；委托 build-release 输出完整套件。
build-release: 稳定版本门禁、上一稳定包选择、构建身份环境隔离和发布归档。
test-suite: 逐文件隔离 pytest；记录超时、JUnit 和汇总数据，不重试。
build-terminal-plugin: 用匹配的 Qt 6.8 编译私有终端 QML 插件。
configure-login.py: 登录配置的备份、应用与恢复。
debian-build.Dockerfile: Debian 13 arm64 编译依赖与原生测试环境。
debian-test.Dockerfile: 干净安装容器；启用签名 Raspberry Pi 源。
measure-applications.py: 隔离应用进程和状态，测量启动与切换。
measure-motion.py: 全屏独立探针；电源预检、Qt 事件循环等待和连续呈现测量；UDECK_MOTION_TRACE=1 开启线程诊断。
measure-shell.py: 桌面启动与资源占用测量。
performance-wayland-bridge.py: 为私有测试总线提供桌面激活。
terminal-acceptance: 记录已安装终端的性能；保留人工验收状态。
terminal-build.Dockerfile: 原生终端插件与交互探针依赖。
update-terminal-build-info: Debian strip 后更新插件哈希。
verify-application-input.py: 独立应用的输入路由探针。
verify-input-isolation.py: 桌面与独立应用的输入隔离探针。
verify-system-shortcuts.py: 私有 labwc 显示发现、快捷键、IPC 与截屏探针。
verify-trackball-console.py: 私有会话的合成轨迹球与 Console 输入探针。
verify-windows.py: 窗口发现、激活与关闭探针。

发布构建必须执行完整测试。
版本读取 src/udeck/__init__.py，不维护第二版本源。

[PROTOCOL]: Update this header on change, then check AGENTS.md
