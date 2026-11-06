# uDeck native applications

Music, Video, Browser, Reader and Games are independent PySide6/Qt Quick processes.
Install `udeck >= 0.1.7` and the optional `udeck-apps` Debian package. Each app has a
desktop entry and `udeck-{music,video,browser,reader,games}` launcher. Installation
does not change default applications or move user files.

Use Settings → Sources to add an absolute folder path. L/R (PageUp/PageDown) switches
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

Games launches installed RetroArch cores in a separate process. Set core/firmware
folders in Settings. GB/GBA/SNES/NES/PS1 extensions are indexed; each title still
needs an installed compatible core and required firmware. No ROMs or BIOS files are
distributed. Physical game buttons belong to RetroArch. In a uDeck session,
Ctrl+Alt+M requests the frontend pause menu; Ctrl+Alt+Esc keeps the desktop shortcut.
The private stdin command channel is used; no network command port is opened.
Manual slots 1–3 and the automatic resume point use separate local save groups with
content/core hashes and checksums. Wrong-core or damaged states are rejected.

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
