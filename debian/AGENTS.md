# debian/
> L2 | Parent: ../AGENTS.md

成员清单：

changelog: Debian 包版本与变更记录。
control: arm64 构建依赖、运行依赖与单包声明。
copyright: 源码、字体与上游资源的许可证清单。
rules: 原生终端编译、隔离测试与 Debian 载荷生成。
udeck.install: Python 模块、QML、资源与会话入口的安装路径。
udeck.docs: 随包分发的操作说明。
udeck.links: 桌面、终端和 Agent 图标的符号链接。
udeck.manpages: 终端命令的手册入口。
udeck.postinst: 安装后应用系统终端默认项。
udeck.prerm: 移除前恢复原系统终端默认项。
udeck.postrm: 移除后清理终端注册项。
source/: Debian 原生源码格式与归档排除规则。

Python 模块清单必须覆盖 src/udeck 的全部包。
tests/test_release.py 校验模块安装路径。

[PROTOCOL]: Update this header on change, then check AGENTS.md
