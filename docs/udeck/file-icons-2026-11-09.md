# Files：Tabler 文件类型图标

Files 的大图标网格使用 65 类 Tabler outline 图标，识别 667 条不同后缀、55 个特殊文件名和 100 个明确 MIME 后备规则。图标在圆角色块上显示，文档用蓝色、表格用绿色、PDF 用红色、压缩包用金色、图片用青色，保留现有 Classic / Dark 界面和选中效果。

## 常用类型

| 类别 | 示例 |
| --- | --- |
| Office 与文档 | PDF、DOC/DOCX、XLS/XLSX、PPT/PPTX、ODT/ODS/ODP、RTF、Pages、Numbers |
| 文本与电子书 | TXT、Markdown、README、EPUB、MOBI、AZW3、FB2、DJVU、CBZ/CBR |
| 图片与设计 | JPG、PNG、BMP、GIF、WebP、AVIF、HEIC、SVG、EPS、AI、PSD、Krita、Sketch、Figma |
| 相机 RAW | CR2/CR3、ARW、NEF、DNG、RAF、ORF、RW2 等 |
| 音频、视频、字幕与播放列表 | MP3、FLAC、WAV、AAC、OPUS、MIDI、MP4、MKV、WebM、MOV、SRT、ASS、VTT、M3U8、CUE |
| 压缩包 | ZIP、7Z、RAR、TAR、GZ、XZ、ZST、TAR.GZ、TAR.ZST 等 |
| 编程语言与网页 | Python、C/C++、Java、Go、QML、HTML、CSS/SCSS、JS/JSX、TS/TSX、Vue、PHP、Rust 等 |
| 配置与数据 | INI、TOML、YAML、JSON/JSONL、XML、CSV/TSV、SQL、SQLite、Parquet、Notebook、`.env.*`、`.gitignore` |
| 字体与程序 | TTF、OTF、WOFF/WOFF2、DEB、RPM、APK、WHL、AppImage、EXE、DLL、SO 及 `.so.1` 等版本文件 |
| 磁盘与游戏 | ISO、IMG、DMG、QCOW2、NES、SFC、GB/GBA、NDS、N64、CHD、NSP、游戏存档 |
| 3D、CAD 与固件 | STL、OBJ、GLTF/GLB、FBX、Blend、STEP、DWG/DXF、KiCad、G-code、UF2、HEX |
| 其他 | 证书、加密文件、Torrent、日历、联系人、备份、日志、二进制、模型权重、链接、邮件 |

完整逐项后缀映射与维护说明见 [图标资源 README](../../src/udeck/assets/file-icons/README.md)。这些是**图标识别规则**，不代表新增格式解码、预览、应用启动或游戏支持；未知文件保留中性图标。

## 来源与离线分发

- 官方网站：[Tabler Icons](https://tabler.io/icons)。
- 官方仓库：[tabler/tabler-icons](https://github.com/tabler/tabler-icons)。
- 固定版本：`@tabler/icons` **3.51.0**，下载日期 2026-11-09。
- 归档：[icons-3.51.0.tgz](https://registry.npmjs.org/@tabler/icons/-/icons-3.51.0.tgz)。
- 归档 SHA-256：`b30108713d3fa60aee862c2a133225da8e0f309be0708fe2925763ff810c766c`。
- 许可：**MIT**；随包保留原作者署名和 [原始许可](../../src/udeck/assets/file-icons/LICENSE.txt)。

官方 npm 元数据中的 SHA-512 integrity 和 SHA-1 与下载归档一致。所选 SVG 只补充文件末尾换行，路径、viewBox 和 stroke 设置不变；源文件与本地文件的 SHA-256 分别记录在 [manifest.json](../../src/udeck/assets/file-icons/manifest.json)。运行时替换 `currentColor`，在现有色块上居中绘制；不会改写文件，也不会联网加载资源。

图标通过现有 Qt SVG 图像插件渲染，不增加 Qt 模块、Python 依赖或网络服务。Wheel 显式包含此资源目录，Debian 包沿用现有模块/资源复制流程。

## 验证

分类用例覆盖常用后缀、大小写、复合压缩包、特殊文件名、带版本的共享库、未知文件和无扩展名 MIME 后备；目录优先于同名扩展名。测试还确认图标变化不改变 Office 文件的既有预览分类，不读取或改写原文件内容。

`tests/file_icons_probe.py` 禁止退回旧手绘图标，对全部 65 类逐个执行 48、80、144 px 离线渲染，检查透明边缘、实际 SVG 前景和代表性类型之间的区别，并生成完整图标总览。文件页另沿用双主题、双语言、双尺寸的 QML 导航和截图检查。

2026-11-09 的本地验证结果：

| 检查 | 结果 |
| --- | --- |
| macOS 专项回归 | 276 项通过，涵盖类型规则、资源哈希、离线渲染及已有 Files 功能 |
| Linux arm64 专项回归 | 同一组 276 项通过；源码只读、容器断网 |
| SVG 离线渲染 | 全部 65 类在 48 / 80 / 144 px 渲染通过；禁止使用旧图标后备 |
| QML 矩阵 | 英文 / 中文 × Classic / Dark × 1280×720 / 960×600，共 8 组通过，无 QML 错误 |
| Wheel | 305 个模块/资源文件与源码逐字节一致；解包后的 QML 和全部图标渲染探针通过 |
| Debian arm64 | 237 个基础包模块/资源文件与源码逐字节一致；解包后的 QML 和全部图标渲染探针通过 |
| 代码检查 | 修改和新增的 Python 文件通过 Ruff，`git diff --check` 通过 |

精简 Linux 验证镜像最初没有安装 `qt6-svg-plugins`，导致 SVG 探针明确失败。uDeck 的现有 Debian 包已经声明该依赖；验证时从 Debian 官方站点取得同版本 `6.8.2-3` arm64 插件，仅解包至容器临时目录后离线重跑成功，没有增加应用依赖或安装主机软件。原始失败及最终通过日志分别保存在 `/tmp/udeck-files-validation-20261108/linux-icons.log` 和 `linux-icons-verified.log`。

本地验证包版本保持 `0.1.20`：Wheel SHA-256 为 `f8a70c105e9000c8c3d1d032c4914dc018aec094e2c26cf55aa6daaf1542c986`，Debian SHA-256 为 `f85c20f0190283d754ce16100818f887f9853c0bb807e67269bb9625279b871c`。资源总览和文件页截图均为本地离屏渲染；验证包仅解包检查，尚未部署到 uConsole。源代码交付以 Git 历史为准，实机显示和物理输入验收仍需在设备上单独执行。
