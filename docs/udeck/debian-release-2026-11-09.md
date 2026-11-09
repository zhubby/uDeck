# Debian 0.2.2 构建验证记录

统一安装包为 `udeck`，通过严格同版本依赖安装 `udeck-shell`、`udeck-terminal`、`udeck-apps`。目标环境与迁移方式见 [发行文档](debian-distribution.md)。本记录区分软件验证、GitHub 托管执行和物理设备验收。

## 原生构建

在原生 Linux arm64 的 Debian 13 容器中执行：

```sh
DEB_BUILD_OPTIONS=parallel=4 python3 tools/build-release --tag v0.2.2 --output dist/release
```

最终全量测试为 **1097 passed，13 条 dbus-next 既有弃用警告，325.61 秒**，没有跳过原生终端测试。随后 `dpkg-buildpackage --build=full --no-sign` 成功生成四个二进制包、匹配源码包、构建信息和套件压缩包。

本地构建器为 `udeck-debian-release-builder:20261109`，镜像 ID 为 `b24fef98a86f9af2cfa955a4b5a1f64a29a5e2c90e1ae50ac7bbfce5e7da1392`。安装验证镜像从 Debian 13 slim 开始构建，镜像 ID 为 `91155abae978b28a25cb87fe944442c6598470aa48d3b6c01c0e8c00ed9ae0f3`，已确认架构为 arm64；关闭容器自带的文档裁剪规则，以核对完整的许可证、文档及 man page。

APT 使用签名 Debian Trixie 与官方 Raspberry Pi Trixie 源。Raspberry Pi keyring 2025.1+rpt1 的下载校验和固定于测试 Dockerfile；旧公钥的 SHA-1 自签名会被当前 APT 策略拒绝，测试没有关闭仓库签名验证。实际候选包括 PySide6 6.8.2.1-4、labwc 0.20.2-1~bpo13+1、wpasupplicant 2:2.10-24+rpt3。

## 安装生命周期

探针入口为：

```sh
python3 tests/debian_package_probe.py dist/release
```

它仅允许在一次性 root Docker 容器中运行，通过临时本地 APT 索引只请求安装 `udeck=0.2.2`，并关闭推荐包安装。系统依赖可以预缓存，APT 仍校验签名索引和包校验和。

最终探针以退出码 0 完成：`packageLifecycle=passed`，逐字节核对 **315 个已安装 Python、QML、字体及资源文件**。验证包含：

- 只安装元包即可获得完整套件，四个包版本均为 0.2.2；包括 wpasupplicant 的必需依赖无需推荐包补齐。
- 包间文件归属无重叠，载荷不写入 `/etc`、主目录或启动分区；SHA-256 与安装后的 `dpkg --verify` 无异常。
- 已安装的桌面壳及五个应用离屏启动成功，QML 错误为空；已安装终端通过独立 D-Bus 会话启动真实 PTY 并执行程序。
- 私有插件的实际 ELF 哈希匹配构建信息；独立 PTY 探针验证参数、环境隔离、中文选区、输入法提交和光标查询、括号粘贴、窗口调整及进程组退出。
- 从受控旧 `udeck` 文件归属模型升级到新元包及 `udeck-shell` 成功；重装、卸载和再次安装成功。
- 每轮安装、升级、卸载后，预设的 LightDM、原 labwc、用户设置文件及默认终端的实际选择和模式均保持一致。

本地完整日志保留于 `/tmp/udeck-debian-release-build-20261109-r3.log` 与 `/tmp/udeck-debian-lifecycle-20261109-r3.log`。

## 静态与兼容性检查

`ruff check src tests tools`、Actionlint、修改过的 shell 脚本 ShellCheck、`git diff --check` 均通过。兼容检查、版本拒绝及 CLI 相关的 17 项测试通过；独立 preflight 可用 Python 3.9 语法解析，不需要安装 Qt 或 uDeck。

顺序审阅发现并修复：dh_python3 将 QML 插件误改为 Python 扩展文件名、精简安装缺失 wpasupplicant、旧 Raspberry Pi 公钥失效。安装探针还检查默认终端的实际选择和模式，并把 dpkg 校验输出作为失败条件。

## 本地产物

产物保留于 `dist/release/`，不提交二进制到 Git。

| 文件 | SHA-256 |
| --- | --- |
| `udeck_0.2.2_arm64.tar.xz` | `815a1a53be8ed18f7ddf04cfda7974e0377c0118b8ae9f19bdf0d288f51566b9` |
| `udeck_0.2.2.tar.xz`（源码） | `9457312dd168cf488dcf4eb9cf44264d6f550dbfd0368f0c27911fc453c472cb` |
| `udeck_0.2.2_all.deb` | `323a6a164de0cb9650539ff2662dbd34c1a0ef2892ad58e6afc910f4aab7a14d` |
| `udeck-shell_0.2.2_all.deb` | `181471c19c2c52175ba0591e1d257e8735cf5ae7367262256cc152f1d1e468db` |
| `udeck-terminal_0.2.2_arm64.deb` | `54aa40b55e329b24c66e48fd3564e5b792a589fd130348d68be88a757dd7f490` |
| `udeck-apps_0.2.2_all.deb` | `091548a82fbb8f3f2954035ad231f24fe33db1e6a50941eff2e629700fbdd507` |

本地工作树的 `.git` 指向挂载范围外，因此本地构建清单的 Git 字段为 null；源码对应性由源码包校验和与安装文件逐字节比对验证。构建器允许在没有 Git 元数据的解包源码目录中工作；GitHub 的普通 checkout 使用当前仓库记录提交信息，并为容器挂载目录显式设置单次 Git 安全目录。

## 尚未建立的验收

工作流只监听 `release: published`，不监听 push、PR、普通 tag push 或手工调度。本轮没有创建或发布 Release，因此 **尚未执行 GitHub 托管的 Release 工作流**；本地已执行其构建与安装验证步骤。

官方 v3.1 镜像下载未完成，未建立原始 SD 镜像的完整哈希、解包与安装证据。旧 v0.1b XFCE 仅支持检测和备份迁移。CM4 登录/退出、方向与物理按键、真实中文候选框、蓝牙音频、亮度、电源、存储卸载及原桌面恢复仍需实机验收。
