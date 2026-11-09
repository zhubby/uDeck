# uDeck native applications

Music, Video, Browser, Reader and Games are independent PySide6/Qt Quick processes.
Install `udeck 0.2.0` and the optional `udeck-apps 0.2.0` Debian package. The shell and
application suite share `udeck.__version__`; their Debian packages require matching
versions and are upgraded together. Each app has a
desktop entry and `udeck-{music,video,browser,reader,games}` launcher. Installation
does not change default applications or move user files.

Use Settings → Sources to add media folders; Games uses Settings → ROM root and
platform subfolders instead. L/R (PageUp/PageDown) switches
collections; directions select; A/Enter opens; B/Esc returns; X/F2 opens actions;
Y/F3 opens settings. Ordinary A/B/X/Y letters remain text. English is the default;
Settings → Language shares the shell's persisted English/Chinese preference.

Music uses QtMultimedia, with real queue/end-of-file behavior, seek and device
selection. Returning to the library continues playback. Closing while playing
offers background playback, stop and exit, or cancel. Video uses the same engine
and a composited VideoOutput, with confirmed resume, seek, embedded audio/subtitle
tracks, companion UTF-8 SRT captions, chapters from ffprobe, speed and fading controls.
Hardware decoding and supported codecs depend on the installed Qt/FFmpeg build.
With `QT_QUICK_BACKEND=software`, a decoded-frame image provider replaces the
scenegraph VideoOutput and limits presentation to 15 frames/second. This fallback
is for compatibility; it does not establish hardware decoding or playback performance.

Browser uses QtWebEngine with a persistent, separate profile. It supports real
HTTP/HTTPS pages, address/search, tabs, history, bookmarks, zoom, reading extraction,
spatial link navigation, virtual pointer and native text entry. Navigation varies
across websites; pointer/keyboard modes remain available. Certificate errors are
rejected; site permissions and downloads require a choice. Browser data is local
under the app data directory. The app does not claim compatibility with every site.

Reader uses QtPdf for PDF pages, zoom/pan, contents and text search. TXT (UTF-8,
UTF-16, GB18030) and EPUB use pinned foliate-js with CFI positions. Reflow keeps a
logical anchor; bookmarks do not modify the source. A tokenized loopback resource
server exposes the selected book and renderer only. A nonce CSP blocks book scripts,
remote resources, forms and objects; its off-the-record profile shares no browser
cookies. Source loss closes the document and its menus while retaining local position.

Games discovers installed RetroArch cores and their metadata. Its default ROM root
is `~/Games`: use `gba/`, `psp/`, `psx/`, `dreamcast/`, etc.; shared extensions never
guess the platform. Settings provides a folder picker, explicit platform folder
creation, searchable core management, enablement and platform defaults. Each title
can select an enabled compatible core. CUE/GDI/M3U dependencies are deduplicated
and confined to their platform folder. Archives stay single library entries;
game engines use explicit entrypoints, and no-content cores can run independently.
Core loading is checked in disposable subprocesses and does not establish game
compatibility or performance. Required firmware and alternatives are checked
before launch. No commercial games or firmware are distributed. See
[Games directory and core rules](games.md). Physical game buttons belong to RetroArch. In a uDeck session,
Ctrl+Alt+M requests the frontend pause menu; Ctrl+Alt+Esc keeps the desktop shortcut.
The private stdin command channel is used; no network command port is opened.
Manual slots 1–3 and the automatic resume point use separate local save groups with
content/core hashes and checksums. States are isolated by game/core/core hash;
SRAM is isolated by game/core. Compatible legacy saves are copied on first read,
leaving originals intact. Unsupported state operations are hidden. Old libraries,
IDs and favorites remain reachable through Legacy sources. Wrong-core or damaged
states are rejected, and resuming with another core requires an explicit choice.

Local state: `$XDG_DATA_HOME/udeck/apps/` (normally `~/.local/share/udeck/apps/`).
Global language: `$XDG_CONFIG_HOME/udeck/settings.json`. Use `udeck-app APP --doctor`
for the running app's diagnostics. `--isolated --windowed --no-input` uses temporary
state and no session IPC/hardware reader. Native tests generate original fixtures;
they are distinct from the approved offline design in `docs/design/app-suite/`.

Build: `tools/build-deb` and `tools/build-apps-deb` on Debian. Run `pytest`,
`ruff check src tests`, and native probes described in `verification.md` before delivery.

See [verification](verification.md) for reproducible checks, native screenshots and
the boundary between automated/device evidence and physical acceptance. The
[review record](review.md) documents defects corrected before delivery. The earlier
`docs/design/app-suite/` directory remains the approved offline design; these apps
are the native implementation. QtMultimedia replaced the candidate mpv adapter
after actual composited playback was verified on the target Qt/Wayland environment.
