# 内置应用

Music、Video、Browser、Reader、Emulator 和 Agent 是独立的 PySide6 / Qt Quick 进程。
Terminal 使用独立的原生终端入口，见 [Terminal 指南](../udeck/terminal.md)。
完整套件由一个 arm64 `udeck` 包分发，版本来自 `udeck.__version__`。

## 入口与共同规则

启动命令为 `udeck-music`、`udeck-video`、`udeck-browser`、
`udeck-reader`、`udeck-emulator`，也可使用 `udeck-app APP`。
Agent 使用 `udeck-app agent`。
界面启动固定的 uDeck Python 模块，不执行桌面文件中的自定义命令。
每个应用通过当前图形会话的 D-Bus 身份转发请求和提供诊断。

方向键选择，A/Enter 打开，B/Esc 返回，X/F2 操作，Y/F3 设置。
L/R 或 PageUp/PageDown 切换集合；文字输入保留原生编辑行为。
默认英文，语言与 Classic/Dark 主题跟随全局配置。
设置使用单行图标、名称和右侧实际值，开关不预先翻转。
完整交互见[应用设计](../design/app-suite/README.md)。

没有自定义来源时，Music、Video、Reader 分别发现
`~/Music`、`~/Video`、`~/Books`，递归扫描子目录。
目录不存在时由用户创建并刷新，不替换已有自定义来源。
来源记录目录身份，后台扫描带代次；失效来源不能继续读取。
Emulator 使用独立 ROM 根目录和 Libretro 列表，见[模拟器指南](emulator.md)。

## Agent

首页第一张卡片打开 Agent。
从右上角「设置 → 管理 Agent」进入管理页。
管理页安装、登录、检查更新和回退 Codex、Claude Code、OpenCode、Pi Agent。
选择本地工作目录后开始会话。
按 Enter 或点击输入框内的发送按钮。X 打开历史会话。
返回首页保留当前会话。退出后通过历史重新打开。
连接与版本管理见 [Agent 设计](../design/agent-app.md)。

## Music 与 Video

两者共用 `apps/media` 中的 QtMultimedia 引擎。
Music 提供队列、曲末切换、定位和输出选择。
Music 优先使用目录中的独立图片，其次提取音频内嵌封面。
曲库后台缓存封面，专辑与播放页随缓存更新。
重新扫描已有曲库时会补齐内嵌封面。
返回内容库继续播放；关闭时提供后台播放、停止退出和取消。
Video 使用合成的 VideoOutput，提供确认续播、定位、
内嵌音轨/字幕、同名 UTF-8 SRT、章节、速度和淡出控制栏。
列表优先使用来源目录的封面图，其次使用内嵌封面。
缺少封面时，后台提取一帧。提取结果按视频指纹缓存。
播放栏居中显示上一章、快退 10 秒、播放或暂停、快进 10 秒和下一章图标。
上下键选择图标，左右键直接快退或快进。
播放菜单右侧显示当前倍速、内嵌字幕、外部字幕和音轨。
子菜单用勾号标记当前启用的选项。
格式和硬件解码能力取决于目标 Qt/FFmpeg 构建。

开始或恢复播放会立即暂停另一播放器，保留其进度和队列。
暂停、结束或退出当前播放器不自动恢复另一方。
软件渲染使用解码帧图像提供器，呈现上限为 15 帧/秒。
这条兼容路径不能作为硬件解码或性能验收。

TS 先由 `SeekableSource` 异步重封装为带索引的临时 Matroska。
复制音视频和字幕流，不重编码、不修改原文件。
库条目、续播和界面身份始终使用原文件。
准备前后核对文件身份，换源取消旧任务。
准备最多 180 秒，需预留原文件大小加 64 MiB 临时空间。
输出上限为原大小加上 10% 与 1 MiB 中的较大值。
准备失败保留续播记录，临时副本在换源或正常退出后清理。
准备期间的暂停意图在播放器就绪后仍有效。

## Browser

Browser 使用持久且独立的 QtWebEngine profile。
支持 HTTP/HTTPS、地址搜索、多标签、历史、书签、缩放、
阅读提取、链接导航、虚拟指针和原生文字输入。
网站的空间导航能力不同，保留键盘和指针模式。

证书错误拒绝通过，权限和下载需要用户选择。
未知协议不能调用系统处理器；mailto、tel、magnet 等不启动外部应用。
网页上传和颜色选择的系统选择器被拒绝，并显示限制说明。
页面确认和认证使用进程内 Qt Quick 对话框。
网页内容、URL 和站点账户不随界面语言翻译。

## Reader

PDF 使用 QtPdf，保留文档字形，提供翻页、缩放、平移、目录和查找。
TXT、EPUB、MOBI 使用固定版本 Foliate 渲染器及逻辑位置。
TXT 支持 UTF-8、UTF-16 和 GB18030。
重排以 CFI 等逻辑锚点恢复位置，书签不修改原书。

TXT、EPUB、MOBI 默认使用随包的 LXGW WenKai Screen 1.530。
布局菜单仍提供无衬线、衬线和等宽选项。
PDF 不使用重排字体。字体来源和许可保留在源码资源目录。

MOBI 直接读取原文件，上游提供 MOBI6、KF8 与混合容器解析。
KF8、HUFF/CDIC 与压缩字体仍需独立实书验收。
书籍上限为 512 MiB，单条记录或请求上限为 64 MiB，
文件头声明的正文上限为 128 MiB。
DRM 文件与不支持的压缩明确报错，不解密或执行外部转换命令。
原文件位置与书签使用稳定内容身份，未转换为另一份库条目。

随机会话令牌的 loopback 服务只暴露当前文档、渲染器和固定字体。
非持久 WebEngine profile 不共享 Browser Cookie。
CSP 拒绝书内脚本、远程资源、表单和对象。
切书、关闭或来源丢失后撤销旧资源会话。
来源丢失关闭所属菜单并保留已知本地位置。

## Emulator

前端负责列表、核心、固件检查、封面、暂停菜单和存档。
RetroArch 在受监管的独立进程运行，通过私有 stdin 通道控制。
游戏中普通按键交给 RetroArch，Ctrl+Alt+M 打开暂停菜单，
Ctrl+Alt+Esc 返回桌面。返回游戏需合成器确认原窗口激活。

原生存档导入导出、不可变历史、SRAM 保护和 rclone 冲突规则
统一见[模拟器指南](emulator.md)。
不分发商业游戏和固件；核心加载不证明游戏性能。

## 数据与验证

应用状态位于 `$XDG_DATA_HOME/udeck/apps/`，默认
`~/.local/share/udeck/apps/`。全局配置位于
`$XDG_CONFIG_HOME/udeck/settings.json`。
索引、队列、标签、阅读位置和游戏存档使用各自的数据契约。

`common` 提供状态、索引、输入和共享 QML；
`media` 提供播放器；应用目录保留自己的控制器和资源。
引擎状态不并入桌面的全局快照。

`udeck-app APP --doctor` 查询应用诊断。
`--isolated --windowed --no-input` 使用临时状态并关闭会话 IPC 与硬件读取；
内容引擎仍能执行真实操作。
源码与设备的验证边界见[验证规范](../udeck/validation.md)。

[PROTOCOL]: Update this header on change, then check AGENTS.md
