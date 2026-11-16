# Emulator Libretro compatibility verification — 2026-11-15

The Libretro implementation (`ecf8756`), subsequent Wayland fixes (`c13625c`) and
uDeck **0.2.18** release preparation
(`86bb1f0ddac5c333618cefe66cc3f3657dd66bfa`) are merged into and pushed to `main`.
Version 0.2.18 was installed and accepted on the uConsole. Its existing ROM
library was migrated with 0.2.17 and remains in the standard layout. This report
retains the 0.2.18 results; the subsequent 0.2.19 card layout and title-scrolling
fix is recorded in the [playlist card verification](emulator-playlist-cards-2026-11-15.md).

## Delivered behavior

- Separate ROM, playlist and thumbnail directories, defaulting to `~/Games/{roms,playlists,thumbnails}`; registered platforms use Libretro database names.
- JSON `.lpl` is authoritative. Refresh reads playlists; manual scanning and selected-file imports require preview confirmation before publication.
- Playlist navigation retains search/focus, mixed-platform entries, missing files and unavailable cores. Favorites, records and saves use persistent game IDs; entries retain their own labels and cores.
- Portable base directories and archive members retain separate filesystem and RetroArch launch paths. Playlist changes preserve unknown fields/order and reject external edits since the last read or preview.
- Standard thumbnail lookup, aspect-fit previews, image-type selection and asynchronous missing-image downloads with cancellation, timeouts, validation and exclusive publication.
- Migration preflight, explicit ambiguous-platform mapping, conflict/dependency/space checks, a recovery journal, verified cross-device copying and preservation of game IDs/native save associations. Incomplete recovery suspends refresh and launch; closing recovery does not overwrite journaled configuration.

The user guide is [Emulator: Libretro lists, directories, cores and saves](../apps/emulator.md).

## Validation

- Debian arm64 0.2.18 release build, Python 3.13 / Qt 6.8.2: **1710 passed**, with no skipped or failed tests. The build manifest records the release revision above and `gitDirty: false`.
- The Wayland and card-layout fixes passed **29 targeted tests**, all **4 local Qt language/theme probes**, Ruff over `src` and `tests`, and whitespace checks. Earlier Libretro implementation checks passed **240 affected tests** and **51 final targeted tests** before the 0.2.17 build.
- Binary-package and source-archive inspection: **506 application files** match the merged source bytes, including Python, QML, translations and the database mapping resource.
- The earlier 0.2.17 disposable Debian package lifecycle passed install, upgrade, reconfiguration, reinstall, removal and reinstall checks, installed application/IPC smoke tests, native terminal checks, source-archive comparison and configuration preservation. It independently checked **506 installed source files**; 0.2.18 package/source verification and the real-device upgrade are checked separately.
- On the uConsole, using installed 0.2.18 application code and private test settings/D-Bus: **253 regression tests passed**.
- Installed Qt keyboard probes: **4 passed**, English/Chinese × Classic/Dark, with no QML errors. They cover list navigation and scroll/back focus, empty lists, core menus, native-save import/export/history, directory-picker cancellation, scan preview/cancel/confirm and measured image aspect ratios.
- Earlier 0.2.17 Wayland/Gambatte acceptance with an original battery-backed GB fixture passed creation and restoration of a **34,864-byte native state**, **8,192-byte SRAM** round trips, ownership locks, native import/export/history, relocated-game restoration, stable game identity and an intentional abnormal exit that preserves durable SRAM/history. Foreground window activation is checked before capturing the Classic/Dark screenshots.

The installed package SHA-256 is
`4ced2f40c2f49a2f438465265b37f173a561b2b328ea17dfd588664c3bded1ef`.

Isolated migration tests use original fixtures. They cover
sidecars, instant-save content compatibility, native SRAM, favorites/recent/play
records, ambiguous platforms, same-name conflicts, stale or missing disc tracks,
insufficient space, write failures, interrupted moves, configuration-publication
crashes, cross-device transfers, destination races and separate archive members.
Download tests use locally generated PNGs and a local HTTP server; they cover 404,
invalid images, cancellation, timeouts/retry and preserving existing images.

## Device retest and fixes

Testing the normal installed application on Wayland exposed a pause/command
failure: presenting Emulator before RetroArch confirmed pause could fully cover
the game and stop its command loop. Saving from the pause menu could likewise
time out. Version 0.2.18 waits for pause acknowledgement before presenting the
menu and uncovers the game while native save/load commands run. A separate
layout fix reserves the measured caption height, keeping long playlist names
and game counts inside their cards. Both fixes have regression coverage.

The 0.2.18 installation check verifies **506 installed source files** against the
release manifest and passes `dpkg --verify udeck`. All **15 pre-existing protected
configuration/native-save files** retain their hashes; **7 other desktop
application processes** retain their PIDs and start times. Cloud settings and
the active/enabled save service are preserved.

The normal installed application, using the migrated library and compositor
keyboard events, passes this sequence for each original fixture: launch, capture
the running core, pause with `Ctrl+Alt+M`, save slot 3, load slot 3, save and return,
relaunch with Continue and automatic restoration, then exit cleanly.

| Platform | Installed core | Native slot bytes |
| --- | --- | ---: |
| Game Boy | Gambatte | 26,672 |
| NES | Nestopia | 5,096 |
| Game Boy Advance | mGBA | 528,472 |

Only slot 3 and automatic states created by this acceptance run are replaced.
The pre-existing SRAM remains protected. Existing cloud synchronization stays
enabled; two launches use the application's offline-play choice while its
background synchronization is still pending. This does not establish a
successful transfer to the user's cloud account.

The same session passes entry/back selection for all four migrated playlists,
independent list/game searches, favorites add/remove and refresh without changing
any `.lpl` bytes. Cancelling missing-image downloads through the normal menu
reports cancellation without a QML error. The final foreground screenshot
confirms that wrapped platform titles and counts remain inside the cards.

An isolated library, using the installed 0.2.18 controller and real Gambatte,
passes launch/save/load/exit for **three members of one ZIP**, including a Chinese
member name and a GBC member under `Nintendo - Game Boy Color.lpl`. Native states
are **34,864**, **34,864** and **59,440 bytes**. Each member has a distinct content
hash, its own member-based native filename and **8,192-byte SRAM** with the
expected distinct battery marker. The same probe verifies portable base-directory
relocation, a mixed GB/NES list, entry/default core precedence, shared game IDs
across independently named entries, favorites/save-root preservation after a
label edit, unknown fields/order, and isolation of empty/missing/corrupt lists.

The installed downloader also retrieves all **three image types** from the real
`https://thumbnails.libretro.com/` service into isolated test data. An unmatched
local ROM filename falls back to the playlist label. Images decode at their
expected dimensions; repeating the request queues **zero downloads** and
preserves all three hashes. These checks download artwork only.

## Installed library migration

The normal installed Emulator migration menu was operated with compositor keyboard
events after preflight and preview. The journal is **committed**:

- **731 ROM/resource files** moved into `~/Games/roms`; each move validates its checksum. The additional checksum pass and record/save assertions completed before the final screen capture.
- **730 game entries** are present in **4 JSON playlists**: Nintendo - Game Boy, Nintendo - Game Boy Advance, Nintendo - Nintendo Entertainment System and Sony - PlayStation Portable.
- ROM, playlist and thumbnail preferences now point to `~/Games/roms`, `~/Games/playlists` and `~/Games/thumbnails`. No indexed ROM paths are missing.
- All **3 legacy game IDs**, favorites, recent entries, play records and per-game core choices are preserved. The pre-existing native save bytes match the baseline.
- The user's existing cloud selection remains unchanged and enabled. The save service was restored to its original active/enabled state after migration.
- All **15 protected configuration/native-save files** retain their original hashes. The other **6 desktop application processes**, including the terminal session, retain their PIDs and start times.

The final screenshot initially failed because `DSI-1` had entered its normal off
state during the long checksum operation. The same capture failed while off and
succeeded after waking the panel. The completed data checks were retained, and
the migration receipt, final library state and foreground screenshots were then
verified. This did not require another file migration.

## Device disk cleanup

At the user's request, **78 obsolete build, test-artifact and deployment-backup
paths** were removed after verification, including the temporary migration
snapshot. This released **2,654,302,208 bytes (2.65 GB)**; available space was
**24,933,068,800 bytes (24.93 GB)** after that cleanup.

Five live application log files were moved, preserving their open inodes, from an
old deployment directory into `~/.local/state/udeck/desktop-logs` before deleting
that directory. No application restart was required. Installed-source hashes,
protected data and `dpkg --verify udeck` passed again after deletion.

After the 0.2.18 retest, both remaining deployment/test staging directories
(`/var/tmp/udeck-libretro-0.2.17-20261115` and
`/var/tmp/udeck-libretro-0.2.18-20261115`) were also removed. Receipts, logs and
screenshots were copied locally first; no process had a current directory or
open file in either tree. This releases a further **78,016,512 bytes**, for a
combined **2,732,318,720 bytes (2.73 GB)**. Final available space is
**24,967,860,224 bytes (24.97 GB)**. All 506 installed source hashes, the 15
protected files, cloud settings, `dpkg --verify`, the running 0.2.18 version,
idle game state and empty QML error list pass again after deletion.

Historical release and migration receipts, logs and screenshots are retained
under the ignored `artifacts/libretro-deploy-0.2.17-20261115/` directory in the main checkout.
`device-evidence/final-verification.json` records the installed version, directories,
playlists, missing-file count, cloud/service state, preserved processes and cleanup
result. `device-evidence/device-playlists.png` shows the final library.

Current release and retest evidence is retained under
`artifacts/libretro-retest-0.2.18-20261115/` in the main checkout:

- `package-verification.json`, `build.log` and `release/build-manifest.json`: clean revision, full suite, package and source-byte verification.
- `device-evidence/installation-verification.json` and `installed-tests-verification.json`: installed source, package integrity and four Qt probes; `installed-tests.log` records the 253 device regression tests.
- `device-evidence/normal-session/{navigation,games,downloads,final}.json`: normal installed application, unchanged original files/lists/favorites, preserved desktop processes and final cloud phase `idle`.
- `device-evidence/normal-session/installed-playlists-final.png` and core game/pause PNGs: foreground Wayland screenshots.
- `device-evidence/archive-acceptance.json`, member RetroArch logs and `https-thumbnails.json`: isolated real-core/HTTPS compatibility checks.
- `device-evidence/cleanup.json` and `post-cleanup-final.json`: staging removal, post-cleanup source/data checks, 730 entries in four lists, active/enabled save service and no remaining uDeck build/backup paths under `/var/tmp` or `/var/backups`. Copies remain on the device under `~/.local/state/udeck/device-tests/libretro-0.2.18-20261115-{cleanup,final}.json`.

The checks use automated Qt and compositor key events; human physical-input
and audio acceptance are not established by this deployment.

## 2026-11-16 source acceptance

A normal-session Wayland retest found that leaving a game with Home and opening
Emulator again displayed an inactive game-details page. Minimizing that page
alone left the shell above RetroArch, preventing the native command loop from
acknowledging pause. Reopening an active session now requests pause and waits for
confirmation before presenting the menu. Pause, resume, save, load and quit also
activate the native game window through the existing Wayland window interface.
The earlier single-outstanding-status-query fix remains in use.

The retest runs the complete frontend, its normal session D-Bus service and real
installed cores. A separate game library and save directory isolate the original
test programs. Compositor keyboard events and the regular Emulator launcher
exercise these steps for each platform: open, pause, resume, leave while playing,
return, leave while paused, return, save slot 1, load slot 1, save and exit,
Continue after restart, and quit without saving.

| Platform | Core | Manual and automatic native-state bytes | Result |
| --- | --- | ---: | --- |
| Game Boy Advance | mGBA | 528,472 | Passed |
| Game Boy | Gambatte | 26,672 | Passed |
| NES | Nestopia | 5,096 | Passed |

Leaving and returning preserves the game PID. Continue starts a new process and
confirms automatic-state restoration. All six exits return code 0 and remove the
native process. Covered games retain at most one 11-byte status query, with no
Qt write backlog. Native save checksums and load completion are verified; all
screenshots have an empty QML error list. The affected device regression suite
passes **150 tests**, and Ruff and whitespace checks pass.

Before replacing the stale running frontend, the user's current RPG session was
preserved in previously empty manual slot 1. That state is **462,936 bytes** and
passes its checksum check. The four original durable save files and all 14
protected configuration files retain their hashes. `dpkg --verify udeck` passes,
the original shell and compositor remain alive, and no RetroArch process remains
after acceptance. Other desktop applications stay open.

The verified source snapshot contains **511 checked files**. The normal user
library is restored with that source; the installed **0.2.24 package is unchanged**.
This validates automated input on the physical device, without establishing human
button or audio acceptance. The ignored
`artifacts/emulator-device-flow-20261116/acceptance-fixed/` directory contains
33 screenshots, state/process records and the three-platform result. The parent
directory contains the source checksums, user-state recovery and final checks.
