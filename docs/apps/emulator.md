# Emulator：目录、核心与存档

适用于完整的 uDeck 0.2.16 Debian 单包。

## 平台与游戏

“所有平台”先显示平台卡片，按 A 进入该平台的游戏列表，按 B 返回并恢复平台焦点。“最近游玩”和“收藏”直接显示游戏，独立保留选择与搜索。

平台可见性与设置 → 核心管理中的启用状态一致。至少启用一个对应核心就显示平台，无游戏也显示“0 个游戏”；仅安装但未启用的核心不增加入口。同一平台的多个核心共用卡片，FC／NES 等目录别名合并计数。关闭最后一个启用核心后，入口立即隐藏；核心或游戏目录检查中的变化会同步更新列表。

平台层搜索名称、简称和目录别名，游戏层只搜索当前平台游戏。返回时恢复各层查询；空平台提示应放置游戏的目录。平台页的操作菜单提供搜索、清除搜索、浏览 ROM 根目录和刷新；游戏收藏操作只用于游戏条目。

平台图标来自固定版本的 RetroArch Monochrome，统一使用 `#e8cc9f` 暖金色并随包内置。所有注册平台均有本地映射，未知平台使用同套通用手柄。授权、作者署名、上游版本及文件校验值随图标打包，见资源目录中的 `COPYING`、`NOTICE`、`manifest.json`。

## 放置游戏

默认根目录是 `~/Games`。在 Y／设置 → ROM 根目录中选择其他目录，或者使用“创建平台目录”创建已启用平台的目录。创建操作保留已有文件。选择失败或取消选择会保留原路径。

```text
Games/
  gb/Original.gb
  gba/Original.gba
  nes/Original.nes
  psp/Game.iso
  psx/Game/Game.m3u
  dreamcast/Game/Game.gdi
  arcade/romset.zip
  scummvm/Game/Game.scummvm
```

平台目录内可以嵌套游戏目录。`ps1` 对应 `psx`，`sfc` 对应 `snes`，`md/genesis` 对应 `megadrive`，`dc` 对应 `dreamcast`。目录名称不区分大小写。根目录散放文件和未知目录会给出整理提示，识别不会根据 ISO、CHD、CUE、PBP 等共享扩展名猜测平台。

平台注册表位于 `src/udeck/apps/emulator/resources/platforms.json`。除常见平台与多系统核心的关联外，其他核心按规范化的 `.info` `systemid` 生成目录；没有平台信息时使用核心 ID。核心管理会显示每个平台的准确目录。

ZIP／7z 是一个库条目，启动时交给 RetroArch 处理。CUE、GDI、M3U 是光盘入口，引用的轨道和光盘不重复入库。引用必须留在同一平台目录，禁止绝对路径、循环引用和符号链接。

解析同一入口时，每个描述文件只读取一次；最多包含 512 个不同依赖、8,192 次引用和合计 8 MiB 的描述文件，每个描述文件最多 2 MiB。扫描与启动准备中的取消会传递到依赖解析。启动时根目录尚不存在的，创建目录并放入游戏后可直接刷新入库。

ScummVM 仅扫描 `.scummvm` 文件。DOS 默认扫描 `.dosz`、ZIP／7z、`.conf`／`.dosbox` 入口；其他可执行入口可手动添加。其他游戏引擎通过设置 → 添加引擎入口选择启动文件，不会把素材文件批量列为游戏。具备无内容启动能力的核心在核心详情中提供“直接运行核心”。

## 管理核心

核心管理按平台分组，支持搜索、开启／关闭、版本与加载状态、平台默认核心。初次使用时，每个平台启用一个已安装的推荐核心；其他核心可以手动开启。多平台核心按当前平台计算默认启用状态。用户显式开关作用于该核心关联的所有平台。

核心名称、格式、固件和即时存档能力来自实际安装的 `.so`、`.info`；核心目录和固件目录可在设置中选择。加载检查在独立子进程进行，并缓存至应用数据目录的 `emulator-core-cache.json`。核心文件、系统环境或检查器版本变化会重新检查；“刷新核心列表”强制检查。检查失败的核心显示原因并禁止启用。较大的核心允许最多 45 秒完成加载与哈希检查，界面不会等待在主线程。

“加载检查通过”只证明 libretro API 可以读取，不代表具体游戏、性能、图形后端或所有指令路径已实测。固件缺失会在游戏详情或启动检查中列出。必需、可选资源分开；区域 BIOS 和机器型号的替代组合由注册表表达。不同游戏区域或机器模式仍可能要求相应固件。本应用不下载 ROM、BIOS 或修改 shell 配置。

Sega CD 的 Genesis Plus GX、GX Wide 和 PicoDrive 至少需要一份区域 CD BIOS；该要求仅作用于 Sega CD 平台，不阻止 Mega Drive 卡带启动。刷新核心列表会同步更新各层平台、搜索和详情菜单，移除失效入口，并保留有效操作的焦点和搜索草稿。

游戏详情 → 选择核心，只显示已启用且支持当前格式的核心。启动顺序是：单游戏指定核心 → 平台默认核心 → 注册表推荐顺序中的已开启兼容核心。未配置推荐顺序时按核心 ID 稳定排序。单游戏显式指定的核心不可用时会提示处理，不会静默换核。

## 运行与存档

RetroArch 在独立进程运行，使用私有 stdin 控制通道，关闭网络命令通道，并保留用户原有 RetroArch 配置。游戏中按 Ctrl+Alt+M 打开暂停菜单，Ctrl+Alt+Esc 返回桌面。真实按钮、音频和游戏兼容性需另行实测。

手动槽 1–3 与自动续玩点独立。存储位置：

```text
~/.local/share/udeck/apps/emulator-saves/<game-id>/cores/<core-id>/<core-sha256>/
~/.local/share/udeck/apps/emulator-saves/<game-id>/cores/<core-id>/sram/
```

即时存档同时校验游戏内容（包括光盘依赖）、核心哈希与存档校验和。切换核心或核心版本不会覆盖另一套状态。相同核心不同版本共享该核心的 SRAM。旧 Games 存档和 SRAM 不读取、不复制到新目录。恢复已关闭或变更核心的自动存档时，提供恢复原核心、重新开始或取消；若原二进制版本已不在设备上，不能恢复该状态。核心不支持即时存档时，暂停菜单提供正常退出。

修改设置不会终止正在运行的游戏，也不会切换它的存档所有者。准备启动时打开设置、切换目录、返回或切换标签会取消该启动请求。

无内容运行保留入口所属的平台；从搜索进入时选择该核心已启用的平台。临时状态文件与 RetroArch 使用相同的完整原生 `library_name`，因此核心名称中的大小写、空格、句点和连字符不会造成存取档路径不匹配。

Emulator 配置使用独立的 `emulator.json`，共享状态格式版本为 1，专属偏好标记为 `emulatorSchema: 2`。不读取或迁移 `games.json`、旧来源、收藏、最近记录或旧存档。旧文件保留在磁盘；新应用只扫描 ROM 根目录下的平台目录，散放文件不会自动入库。

## 原生存档与历史备份

游戏详情 → 存档管理提供导入、导出、备份当前游戏、历史与恢复；需要先选择可用核心。设置 → 备份与云同步可备份全部已有游戏。已有的本地存储目录继续使用。

导入支持 RetroArch 原生 `.state`、`.stateN`、`.state.auto`、`.srm` 与配套 `.rtc`，保留文件字节；即时存档可以带有同名 `.png` 缩略图。选定游戏和核心后，为即时存档选择目标槽位并确认。外部文件不能证明来源游戏、核心及核心版本，确认页会列出目标与文件路径。导出使用当前 ROM 文件名；手动槽 1–3 分别导出为 `<ROM>.state1`–`<ROM>.state3`，自动续玩点导出为 `<ROM>.state.auto`。SRAM 与 RTC 一起导出，不使用 uDeck 专有归档格式。

导入与历史恢复前，自动备份已有进度。导出遇到同名文件时要求确认，并先把目标目录中的原文件保存到 `.retroarch-save-backups/<独立版本>/`，再替换。存档校验失败或备份失败会停止操作。游戏运行期间，存档文件操作暂缓，避免覆盖正在使用的 SRAM。

本地自动备份默认开启：即时存档得到 RetroArch 保存确认后记录历史；SRAM 从上次提交的版本复制到运行时私有目录，仅在游戏正常退出并完成落盘后提交和备份。异常退出保留此前提交的 SRAM。重启时会恢复被中断的 SRAM 目录替换。

每份历史快照保存原生文件、SHA-256 校验值、平台、内容哈希、核心、槽位、设备、保存时间和父版本。快照发布后不再修改。历史中的即时存档仍要求核心二进制哈希匹配；不兼容版本保留并显示“需要原核心版本”。SRAM 继续由同一核心的不同版本共享。

## rclone 云同步

云同步默认关闭，需要 Debian／Linux 用户会话、用户 D-Bus、systemd 用户服务和支持 `bisync --recover --resilient` 的 rclone。Debian 包推荐安装 rclone；应用在启用时检查命令能力。使用“配置 rclone”会运行 `udeck-terminal -- rclone config`，完成账户配置后在云存储列表中选择已有 remote、填写云端目录并测试连接。账户凭据和令牌始终由 rclone 管理，uDeck 只保存 remote 名称与目录。加密配置必须能在后台无交互访问。

启用后，`udeck-emulator-saves.service` 随用户会话运行，关闭模拟器窗口后继续同步；关闭云同步会取消当前任务并取消下次会话自动启动。服务通过用户 D-Bus `io.github.zhubby.uDeck.EmulatorSaves` 提供 `Status`、`Configure`、`SyncNow`、`Remotes`、`TestConnection` 与 `Changed` 状态通知，不依赖图形窗口。

远端快照位于 `<remote>:<目录>/uDeck/Emulator/v1/`。首次连接合并两端完整快照并建立基线，之后用独立工作目录执行可恢复的 `rclone bisync`。访问标记为 `RCLONE_TEST`；已经建立基线的目标丢失标记时会报错。不要直接修改或移除云端快照与标记。同步的替换备份位于同级 `recovery/` 下，工作副本与本地历史分开，长时间传输不会持有游戏存档锁。

启动游戏前检查云端进度；失败、发生冲突或等待超过 30 秒时，提供重试、继续等待、离线游玩与取消。即时存档保存后、正常退出后触发同步，空闲时每 60 秒检查，失败后自动重试。游戏运行期间可以上传历史，下载的进度在游戏退出后才允许应用。

跨设备匹配依据平台、游戏内容哈希、核心与存档类型／槽位，不依赖本地目录或 ROM 文件名，恢复时重建目标文件名。同一槽位或 SRAM 有并行进度时，进入“处理进度冲突”或游戏历史，根据设备和保存时间选择要继续的版本；选择结果记录全部竞争父版本，原始历史继续保留。时间只用于显示，不参与进度取舍。内容相同的并行版本可以合并父版本后继续。

当前进度和完整历史都会同步，默认不清理历史，需预留本地与网盘空间。启用云同步前会先备份库中已有的存档，包括只有 SRAM 的游戏；ROM 暂不可用或游戏正在运行时显示暂缓，之后可通过“备份全部游戏”补齐。以默认 XDG 路径为例：

```text
~/.local/share/udeck/apps/emulator-backups/snapshots/<device>/<snapshot>/
~/.local/share/udeck/apps/emulator-backups/local.json
~/.local/share/udeck/apps/emulator-save-registry.json
~/.local/share/udeck/apps/emulator-cloud.json
~/.local/share/udeck/apps/emulator-sync-work/<profile>/
~/.local/share/udeck/apps/emulator-sync-recovery/<profile>/
```

同步状态页显示进度、速度、最近同步时间与错误。服务问题可查看 `systemctl --user status udeck-emulator-saves.service` 和 `journalctl --user -u udeck-emulator-saves.service`。遇到访问标记、校验或锁错误时先检查目标目录、连接和另一同步进程；保留工作目录、历史及恢复备份，不要用强制删除或重新建基线掩盖错误。

## 验证

`tests/test_games_catalog.py`、`test_games_management.py` 覆盖目录、格式、核心选择、固件、存档隔离与旧状态忽略、取消和竞争边界。`test_games_qml.py` 使用真实 Qt 键盘事件验证中英文、Classic／Dark、滚动、焦点和确认键。

`test_emulator_save_management.py`、`test_emulator_save_ui.py` 验证原生字节往返、覆盖备份、SRAM／RTC、核心兼容性、损坏文件、写盘失败、分叉选择、运行时保护和启动取消。`test_emulator_save_sync.py` 使用真实 rclone 与隔离目录模拟两个设备，验证首次合并、并发上传、离线冲突、选择后的收敛、取消、配置切换及后台恢复，并通过本机 WebDAV 服务实际断线、重连检查离线进度；`test_emulator_save_daemon.py` 使用独立 D-Bus 会话运行真实后台服务，验证协议、状态通知、前端断开和服务重启。Qt 按键探针另外覆盖原生导入确认／取消、槽位映射、导出、历史与焦点。

0.2.16 已在 uConsole 安装，完成真实 Gambatte 原生存档恢复、SRAM 正常与异常退出保护、已安装后台服务及中英文界面验证，见 [2026-11-14 真机部署记录](../udeck/emulator-save-sync-2026-11-14.md)。实际网盘传输与真人物理按键仍需单独验收；本轮设备未配置真实云端账户，云同步保持默认关闭。

`tests/games_device_probe.py <evidence-directory>` 在设备图形会话运行原创 GB、NES、GBA 程序，验证完整启动、修改设置保留 PID、暂停、存取档、返回和重启续玩流程。测试只写指定证据目录，并通过 `tests/game_fixtures.py` 生成原创测试内容，不包含商业 ROM 或主机标志。运行前应确保没有另一个 RetroArch 会话。
