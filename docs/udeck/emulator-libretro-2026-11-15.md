# Emulator Libretro compatibility verification — 2026-11-15

The implementation (`ecf8756`) and uDeck **0.2.17** release preparation
(`3348cdfa06e0791e63dbdb2a5c8bd3ecdbbdc551`) are merged into and pushed to `main`.
That release is installed on the uConsole, and its existing ROM library has been
migrated to the standard layout. Subsequent delivery documentation does not change
the packaged application source.

## Delivered behavior

- Separate ROM, playlist and thumbnail directories, defaulting to `~/Games/{roms,playlists,thumbnails}`; registered platforms use Libretro database names.
- JSON `.lpl` is authoritative. Refresh reads playlists; manual scanning and selected-file imports require preview confirmation before publication.
- Playlist navigation retains search/focus, mixed-platform entries, missing files and unavailable cores. Favorites, records and saves use persistent game IDs; entries retain their own labels and cores.
- Portable base directories and archive members retain separate filesystem and RetroArch launch paths. Playlist changes preserve unknown fields/order and reject external edits since the last read or preview.
- Standard thumbnail lookup, aspect-fit previews, image-type selection and asynchronous missing-image downloads with cancellation, timeouts, validation and exclusive publication.
- Migration preflight, explicit ambiguous-platform mapping, conflict/dependency/space checks, a recovery journal, verified cross-device copying and preservation of game IDs/native save associations. Incomplete recovery suspends refresh and launch; closing recovery does not overwrite journaled configuration.

The user guide is [Emulator: Libretro lists, directories, cores and saves](../apps/emulator.md).

## Validation

- Debian arm64 release build, Python 3.13 / Qt 6.8.2: **1705 passed**, with no skipped or failed tests. The build manifest records the release revision above and `gitDirty: false`.
- Before the release build, the affected source suite passed **240 tests**; the final targeted verification passed **51 tests**, Ruff and whitespace checks.
- Binary-package and source-archive inspection: **506 application files** match the merged source bytes, including Python, QML, translations and the database mapping resource.
- Disposable Debian package lifecycle: passed install, upgrade, reconfiguration, reinstall, removal and reinstall checks, installed application/IPC smoke tests, native terminal checks, source-archive comparison and configuration preservation. It independently checked **506 installed source files**.
- On the uConsole, using installed application code and private test settings/D-Bus: **224 regression tests passed**.
- Installed Qt keyboard probes: **4 passed**, English/Chinese × Classic/Dark, with no QML errors. They cover list navigation and scroll/back focus, empty lists, core menus, native-save import/export/history, directory-picker cancellation, scan preview/cancel/confirm and measured image aspect ratios.
- Real Wayland/Gambatte acceptance with an original battery-backed GB fixture: passed creation and restoration of a **34,864-byte native state**, **8,192-byte SRAM** round trips, ownership locks, native import/export/history, relocated-game restoration, stable game identity and an intentional abnormal exit that preserves durable SRAM/history. Foreground window activation is checked before capturing the Classic/Dark screenshots.

The installed package SHA-256 is
`a6d6a660da99c3bbddfc2fb1727948c1bf2b15fa607082154f971e6b3fe39d10`.

Isolated migration tests use original fixtures. They cover
sidecars, instant-save content compatibility, native SRAM, favorites/recent/play
records, ambiguous platforms, same-name conflicts, stale or missing disc tracks,
insufficient space, write failures, interrupted moves, configuration-publication
crashes, cross-device transfers, destination races and separate archive members.
Download tests use locally generated PNGs and a local HTTP server; they cover 404,
invalid images, cancellation, timeouts/retry and preserving existing images.

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
**24,933,068,800 bytes (24.93 GB)** after cleanup.

Five live application log files were moved, preserving their open inodes, from an
old deployment directory into `~/.local/state/udeck/desktop-logs` before deleting
that directory. No application restart was required. Installed-source hashes,
protected data and `dpkg --verify udeck` passed again after deletion.

Release and device receipts, logs and screenshots are retained under the ignored
`artifacts/libretro-deploy-0.2.17-20261115/` directory in the main checkout.
`device-evidence/final-verification.json` records the installed version, directories,
playlists, missing-file count, cloud/service state, preserved processes and cleanup
result. `device-evidence/device-playlists.png` shows the final library.

The checks use automated Qt and compositor key events; human physical-input
acceptance is not established by this deployment.
