# Tabler 文件类型图标

来源：[Tabler Icons](https://tabler.io/icons) · [官方仓库](https://github.com/tabler/tabler-icons) · `@tabler/icons` **3.51.0** · **MIT**。

从官方 npm 归档中挑选 65 个 outline SVG，随应用离线分发。SVG 只添加一个文件末尾换行；路径、viewBox、线宽和端点设置保持原样。`LICENSE.txt` 与归档原件逐字节一致，保留原作者 Paweł Kuna 的署名。渲染时将 `currentColor` 替换为类型强调色，图形占现有圆角图标块的 70%，原始资源不在运行时改写。

归档：[`icons-3.51.0.tgz`](https://registry.npmjs.org/@tabler/icons/-/icons-3.51.0.tgz)。下载日期：2026-11-09。

`SHA-256: b30108713d3fa60aee862c2a133225da8e0f309be0708fe2925763ff810c766c`

`manifest.json` 记录 npm SHA-512 integrity、归档 SHA-256、每个源文件与本地文件的 SHA-256、字节数及转换。下载的归档同时通过官方 npm 元数据中的 SHA-512 和 SHA-1 校验。运行不访问 npm、GitHub 或 Tabler 网站。

## 识别规则

共 667 条不同后缀映射（含复合后缀）、55 个特殊文件名和 100 个明确 MIME 后备规则。目录优先，其次特殊文件名、复合/普通后缀，最后 MIME。大小写不敏感，`.env.*` 与带数字版本的 `.so.*` 另行识别；其余使用中性的未知文件图标。

这些规则只决定图标，不读取文件内容、不执行文件、不新增预览/解码或打开能力。扩展名有歧义时采用常见用途，例如 `.ts` 表示 TypeScript，`.mts` 表示视频，`.obj` 表示 3D 模型，`.bin` 表示二进制；缺少可靠名称/MIME 时保留未知图标。

## 完整后缀映射

| 类型 | Tabler 图标 | 后缀（不区分大小写） |
| --- | --- | --- |
| `unknown` | [file-unknown](file-unknown.svg) | 后备图标 |
| `folder` | [folder](folder.svg) | 目录 |
| `text` | [file-text](file-text.svg) | `.txt`、`.text`、`.rtf`、`.rst`、`.org`、`.adoc`、`.asciidoc`、`.nfo`、`.info`、`.tex`、`.latex`、`.bib`、`.sty`、`.cls` |
| `markdown` | [markdown](markdown.svg) | `.md`、`.markdown`、`.mdown`、`.mkd`、`.mdx`、`.qmd`、`.rmd` |
| `pdf` | [file-type-pdf](file-type-pdf.svg) | `.pdf` |
| `word` | [file-type-doc](file-type-doc.svg) | `.doc`、`.dot` |
| `wordx` | [file-type-docx](file-type-docx.svg) | `.docx`、`.docm`、`.dotx`、`.dotm` |
| `document` | [file-word](file-word.svg) | `.odt`、`.ott`、`.fodt`、`.pages`、`.wpd`、`.abw` |
| `excel` | [file-type-xls](file-type-xls.svg) | `.xls`、`.xlsx`、`.xlsm`、`.xlsb`、`.xlt`、`.xltx`、`.xltm`、`.xlam` |
| `spreadsheet` | [file-spreadsheet](file-spreadsheet.svg) | `.ods`、`.ots`、`.fods`、`.numbers` |
| `table` | [file-type-csv](file-type-csv.svg) | `.csv`、`.tsv`、`.psv` |
| `powerpoint` | [file-type-ppt](file-type-ppt.svg) | `.ppt`、`.pptx`、`.pptm`、`.pps`、`.ppsx`、`.ppsm`、`.pot`、`.potx`、`.potm` |
| `presentation` | [presentation](presentation.svg) | `.odp`、`.otp`、`.fodp`、`.keynote` |
| `ebook` | [book](book.svg) | `.epub`、`.mobi`、`.azw`、`.azw3`、`.azw4`、`.fb2`、`.djvu`、`.djv`、`.lit`、`.lrf`、`.pdb` |
| `comic` | [file-stack](file-stack.svg) | `.cbz`、`.cbr`、`.cb7`、`.cbt`、`.cba` |
| `image` | [photo](photo.svg) | `.gif`、`.webp`、`.avif`、`.heic`、`.heif`、`.tif`、`.tiff`、`.ico`、`.icns`、`.jxl`、`.apng`、`.pnm`、`.ppm`、`.pgm`、`.pbm`、`.xbm`、`.xpm`、`.tga`、`.dds`、`.exr`、`.hdr`、`.qoi` |
| `jpeg` | [file-type-jpg](file-type-jpg.svg) | `.jpg`、`.jpeg`、`.jpe`、`.jfif` |
| `png` | [file-type-png](file-type-png.svg) | `.png` |
| `bitmap` | [file-type-bmp](file-type-bmp.svg) | `.bmp`、`.dib` |
| `svg` | [file-type-svg](file-type-svg.svg) | `.svg`、`.svgz` |
| `raw` | [photo-scan](photo-scan.svg) | `.raw`、`.arw`、`.cr2`、`.cr3`、`.crw`、`.dng`、`.nef`、`.nrw`、`.orf`、`.raf`、`.rw2`、`.rwl`、`.pef`、`.srw`、`.x3f` |
| `vector` | [file-vector](file-vector.svg) | `.eps`、`.ps`、`.ai`、`.cdr`、`.emf`、`.wmf`、`.sk1` |
| `design` | [palette](palette.svg) | `.psd`、`.psb`、`.xcf`、`.kra`、`.ora`、`.afphoto`、`.afdesign`、`.sketch`、`.fig`、`.xd`、`.indd`、`.idml`、`.procreate` |
| `audio` | [music](music.svg) | `.mp3`、`.flac`、`.wav`、`.wave`、`.aac`、`.m4a`、`.alac`、`.ogg`、`.oga`、`.opus`、`.wma`、`.aif`、`.aiff`、`.aifc`、`.ape`、`.ac3`、`.dts`、`.mka`、`.amr`、`.au`、`.caf`、`.aiffc`、`.mid`、`.midi`、`.kar`、`.mod`、`.xm`、`.it`、`.s3m`、`.tak`、`.wv`、`.dsf`、`.dff`、`.pcm` |
| `video` | [movie](movie.svg) | `.mp4`、`.mkv`、`.webm`、`.avi`、`.mov`、`.m4v`、`.mpg`、`.mpeg`、`.m2v`、`.mpe`、`.wmv`、`.flv`、`.f4v`、`.m2ts`、`.mts`、`.vob`、`.ogv`、`.3gp`、`.3g2`、`.asf`、`.divx`、`.rm`、`.rmvb`、`.mxf`、`.nut` |
| `subtitle` | [subtitles](subtitles.svg) | `.srt`、`.ass`、`.ssa`、`.vtt`、`.sub`、`.sbv`、`.scc`、`.ttml`、`.dfxp`、`.smi`、`.idx`、`.lrc` |
| `playlist` | [playlist](playlist.svg) | `.m3u`、`.m3u8`、`.pls`、`.xspf`、`.asx`、`.wpl`、`.cue` |
| `archive` | [file-zip](file-zip.svg) | `.7z`、`.rar`、`.tar`、`.gz`、`.bz`、`.bz2`、`.xz`、`.zst`、`.zstd`、`.lz`、`.lz4`、`.lzma`、`.lzo`、`.br`、`.z`、`.tgz`、`.tbz`、`.tbz2`、`.txz`、`.tzst`、`.taz`、`.ar`、`.cpio`、`.ace`、`.sit`、`.sitx`、`.tar.gz`、`.tar.bz2`、`.tar.xz`、`.tar.zst`、`.tar.lz`、`.tar.lzma`、`.tar.br` |
| `zip` | [file-type-zip](file-type-zip.svg) | `.zip`、`.zipx` |
| `code` | [file-code-2](file-code-2.svg) | `.py`、`.pyw`、`.pyi`、`.c`、`.h`、`.cc`、`.cpp`、`.cxx`、`.hh`、`.hpp`、`.hxx`、`.cs`、`.java`、`.go`、`.rb`、`.r`、`.swift`、`.kt`、`.kts`、`.dart`、`.lua`、`.pl`、`.pm`、`.scala`、`.sc`、`.ex`、`.exs`、`.erl`、`.hrl`、`.hs`、`.lhs`、`.clj`、`.cljs`、`.cljc`、`.edn`、`.fs`、`.fsx`、`.vb`、`.vbs`、`.pas`、`.pp`、`.asm`、`.s`、`.jl`、`.m`、`.mm`、`.f`、`.for`、`.f90`、`.f95`、`.zig`、`.v`、`.sv`、`.vhd`、`.vhdl`、`.proto`、`.graphql`、`.gql`、`.svelte`、`.astro`、`.ino`、`.qml`、`.qrc`、`.cmake`、`.gradle`、`.ipy`、`.cbl`、`.cob`、`.awk`、`.sed`、`.wren`、`.gd`、`.hx`、`.nim`、`.d`、`.vala` |
| `html` | [file-type-html](file-type-html.svg) | `.html`、`.htm`、`.xhtml`、`.shtml`、`.hbs`、`.handlebars`、`.mustache`、`.ejs`、`.pug`、`.twig`、`.jinja`、`.jinja2` |
| `css` | [file-type-css](file-type-css.svg) | `.css`、`.scss`、`.sass`、`.less`、`.styl` |
| `javascript` | [file-type-js](file-type-js.svg) | `.js`、`.mjs`、`.cjs` |
| `jsx` | [file-type-jsx](file-type-jsx.svg) | `.jsx` |
| `typescript` | [file-type-ts](file-type-ts.svg) | `.ts`、`.cts` |
| `tsx` | [file-type-tsx](file-type-tsx.svg) | `.tsx` |
| `vue` | [file-type-vue](file-type-vue.svg) | `.vue` |
| `php` | [file-type-php](file-type-php.svg) | `.php`、`.phtml`、`.php3`、`.php4`、`.php5`、`.phps` |
| `rust` | [file-type-rs](file-type-rs.svg) | `.rs` |
| `xml` | [file-type-xml](file-type-xml.svg) | `.xml`、`.xsl`、`.xslt`、`.xsd`、`.dtd`、`.xaml`、`.wsdl`、`.rss`、`.atom`、`.opml`、`.kml`、`.gpx`、`.drawio` |
| `json` | [json](json.svg) | `.json`、`.jsonc`、`.json5`、`.jsonl`、`.ndjson`、`.geojson`、`.topojson`、`.ipynb`、`.har`、`.map` |
| `config` | [file-settings](file-settings.svg) | `.ini`、`.conf`、`.cfg`、`.config`、`.toml`、`.yaml`、`.yml`、`.env`、`.properties`、`.prefs`、`.service`、`.socket`、`.desktop`、`.timer`、`.target`、`.mount`、`.rules`、`.reg`、`.plist`、`.nix`、`.editorconfig`、`.gitconfig`、`.gitignore`、`.gitattributes`、`.dockerignore`、`.npmrc`、`.yarnrc`、`.lock` |
| `script` | [terminal-2](terminal-2.svg) | `.sh`、`.bash`、`.zsh`、`.fish`、`.bat`、`.cmd`、`.ps1`、`.psm1`、`.psd1`、`.command`、`.csh`、`.tcsh`、`.ksh`、`.nu` |
| `sql` | [file-type-sql](file-type-sql.svg) | `.sql` |
| `database` | [database](database.svg) | `.db`、`.db3`、`.sqlite`、`.sqlite3`、`.mdb`、`.accdb`、`.dbf`、`.odb`、`.rdb`、`.duckdb`、`.parquet`、`.arrow`、`.feather`、`.avro`、`.orc` |
| `font` | [typography](typography.svg) | `.ttf`、`.otf`、`.woff`、`.woff2`、`.ttc`、`.otc`、`.pfb`、`.pfa`、`.fon`、`.bdf`、`.pcf`、`.sfnt`、`.eot` |
| `package` | [package](package.svg) | `.deb`、`.rpm`、`.pkg`、`.msi`、`.msix`、`.msixbundle`、`.apk`、`.apks`、`.aab`、`.appx`、`.appxbundle`、`.flatpak`、`.flatpakref`、`.snap`、`.whl`、`.egg`、`.jar`、`.war`、`.ear`、`.xpi`、`.crx`、`.vsix`、`.nupkg`、`.cab`、`.appimage` |
| `executable` | [app-window](app-window.svg) | `.exe`、`.com`、`.app`、`.run`、`.out`、`.elf`、`.wasm` |
| `library` | [file-code](file-code.svg) | `.so`、`.dylib`、`.dll`、`.a`、`.lib`、`.pyd`、`.o`、`.class`、`.pyc`、`.pyo`、`.beam`、`.node` |
| `disk` | [disc](disc.svg) | `.iso`、`.img`、`.dmg`、`.vhd`、`.vhdx`、`.vmdk`、`.qcow`、`.qcow2`、`.vdi`、`.udf`、`.vfd`、`.squashfs`、`.dsk`、`.toast`、`.nrg` |
| `game` | [device-gamepad](device-gamepad.svg) | `.nes`、`.sfc`、`.smc`、`.gba`、`.gb`、`.gbc`、`.nds`、`.3ds`、`.cia`、`.n64`、`.z64`、`.v64`、`.sms`、`.gg`、`.smd`、`.gen`、`.pce`、`.chd`、`.cso`、`.pbp`、`.nsp`、`.xci`、`.wad`、`.dol`、`.gcm`、`.rvz`、`.wbfs`、`.wud`、`.wux`、`.rom`、`.sav`、`.srm`、`.state`、`.save`、`.nkit.iso` |
| `model` | [file-3d](file-3d.svg) | `.stl`、`.obj`、`.ply`、`.gltf`、`.glb`、`.fbx`、`.blend`、`.3mf`、`.dae`、`.usd`、`.usda`、`.usdc`、`.usdz`、`.abc`、`.bgeo`、`.off`、`.lwo` |
| `cad` | [vector-triangle](vector-triangle.svg) | `.dwg`、`.dxf`、`.dwf`、`.dwt`、`.step`、`.stp`、`.iges`、`.igs`、`.3dm`、`.skp`、`.scad`、`.f3d`、`.fcstd`、`.pcb`、`.kicad_pcb`、`.kicad_sch`、`.sch`、`.brd`、`.gerber`、`.gbr`、`.gcode` |
| `certificate` | [file-certificate](file-certificate.svg) | `.pem`、`.crt`、`.cer`、`.der`、`.p12`、`.pfx`、`.csr`、`.pub`、`.key`、`.keystore`、`.jks` |
| `encrypted` | [lock](lock.svg) | `.gpg`、`.pgp`、`.age`、`.enc`、`.vault`、`.kdbx`、`.aes`、`.crypt` |
| `torrent` | [magnet](magnet.svg) | `.torrent`、`.magnet` |
| `calendar` | [calendar-event](calendar-event.svg) | `.ics`、`.ical`、`.icalendar` |
| `contacts` | [address-book](address-book.svg) | `.vcf`、`.vcard` |
| `backup` | [file-time](file-time.svg) | `.bak`、`.backup`、`.bkp`、`.old`、`.orig`、`.swp`、`.tmp`、`.temp` |
| `log` | [file-report](file-report.svg) | `.log`、`.trace`、`.outlog`、`.crash` |
| `binary` | [binary](binary.svg) | `.bin`、`.dat`、`.data`、`.pak`、`.cache`、`.pkl`、`.pickle`、`.msgpack`、`.npy`、`.npz`、`.mat`、`.h5`、`.hdf5` |
| `firmware` | [cpu](cpu.svg) | `.uf2`、`.hex`、`.ihex`、`.dfu`、`.fw`、`.eeprom` |
| `ai` | [robot](robot.svg) | `.onnx`、`.safetensors`、`.gguf`、`.ggml`、`.pt`、`.pth`、`.ckpt`、`.tflite`、`.pb`、`.mlmodel`、`.mlpackage` |
| `link` | [link](link.svg) | `.url`、`.webloc`、`.lnk`、`.shortcut` |
| `email` | [mail](mail.svg) | `.eml`、`.msg`、`.mbox`、`.pst`、`.ost` |

## 特殊文件名

- `markdown`：`readme`、`changelog`、`changes`、`contributing`、`authors`、`code_of_conduct`。
- `text`：`license`、`licence`、`copying`、`notice`、`todo`、`news`、`install`。
- `config`：`.env`、`.gitignore`、`.gitconfig`、`.gitattributes`、`.gitmodules`、`.dockerignore`、`.npmrc`、`.yarnrc`、`.editorconfig`、`.prettierrc`、`.eslintrc`、`.babelrc`、`.browserslistrc`、`.bashrc`、`.zshrc`、`.profile`、`.bash_profile`、`.zprofile`、`.zshenv`、`.vimrc`、`.nanorc`、`.tmux.conf`、`dockerfile`、`containerfile`、`pipfile`、`gemfile`、`vagrantfile`、`cargo.lock`、`package-lock.json`、`yarn.lock`、`pnpm-lock.yaml`、`poetry.lock`、`uv.lock`、`cmakelists.txt`、`meson.build`。
- `script`：`makefile`、`gnumakefile`、`justfile`、`rakefile`、`procfile`、`configure`、`build.ninja`。

## 集成与维护

名称与类型规则位于 `src/udeck/file_icons.py`；`file_kind()` 在原有语义分类和 MIME 之外返回 `udeck-file-…` 图标标识。图像提供器只从此目录的受控映射读取 SVG，使用现有 Qt SVG 图像插件渲染，再绘制到图标块上；系统应用图标仍按原逻辑读取。

新增类型时同时更新类型映射、选取的 SVG、来源清单及分类用例。不要根据图标推断文件可安全预览、可执行或可被已安装应用打开。

诊断：`PYTHONPATH=src QT_QPA_PLATFORM=offscreen python tests/file_icons_probe.py /tmp/udeck-file-icons`。探针禁止使用旧绘图后备，逐个检查 48/80/144 px 的透明边缘和实际 SVG 前景，并输出 `file-icons.png`。
