# Emulator Libretro compatibility verification — 2026-11-15

Implementation is on `codex/emulator-libretro-library`, based on `6d87012`.
The original `main` checkout remains unchanged. This change has not been committed,
pushed, installed on a device or applied to the user's real ROM library.

## Delivered behavior

- Separate ROM, playlist and thumbnail directories, defaulting to `~/Games/{roms,playlists,thumbnails}`; registered platforms use Libretro database names.
- JSON `.lpl` is authoritative. Refresh reads playlists; manual scanning and selected-file imports require preview confirmation before publication.
- Playlist navigation retains search/focus, mixed-platform entries, missing files and unavailable cores. Favorites, records and saves use persistent game IDs; entries retain their own labels and cores.
- Portable base directories and archive members retain separate filesystem and RetroArch launch paths. Playlist changes preserve unknown fields/order and reject external edits since the last read or preview.
- Standard thumbnail lookup, aspect-fit previews, image-type selection and asynchronous missing-image downloads with cancellation, timeouts, validation and exclusive publication.
- Migration preflight, explicit ambiguous-platform mapping, conflict/dependency/space checks, a recovery journal, verified cross-device copying and preservation of game IDs/native save associations. Incomplete recovery suspends refresh and launch; closing recovery does not overwrite journaled configuration.

The user guide is [Emulator: Libretro lists, directories, cores and saves](../apps/emulator.md).

## Validation

Run with the existing Python 3.13/PySide6 6.8 environment and `PYTHONPATH=src`.

- Final affected-suite run: **240 passed**, covering playlists, library/browser, migration, local HTTP thumbnails, platform/catalogue behavior, native save management, shared application state/settings and translations.
- Real Qt keyboard probes: **4 passed**, English/Chinese × Classic/Dark. Includes list navigation and scroll/back focus, empty lists, core menus, native-save import/export/history, directory-picker cancellation, scan preview/cancel/confirm and measured image aspect ratios. No QML errors.
- After the final download-cancellation notification adjustment: **5 thumbnail tests passed** again.
- Full repository run before the final fixes: **1679 passed, 7 skipped, 4 failed**. Three failures were old expectations that refresh auto-scans ROM folders; their fixtures now explicitly generate playlists and all 12 default-source tests pass in the affected-suite run. The fourth was a video probe process exiting with SIGBUS in Qt/FFmpeg; the unchanged video test passed on its single-test rerun (**1 passed**). The full suite was not rerun after these fixes.
- `ruff check src tests`: passed. `git diff --check`: passed.
- Isolated wheel build: successful. Package inspection compares bundled Emulator Python/QML/JSON files and changed shared resources with their current source bytes, including `resources/databases.json`.

Migration tests use isolated original fixtures, not the user's library. They cover
sidecars, instant-save content compatibility, native SRAM, favorites/recent/play
records, ambiguous platforms, same-name conflicts, stale or missing disc tracks,
insufficient space, write failures, interrupted moves, configuration-publication
crashes, cross-device transfers, destination races and separate archive members.
Download tests use locally generated PNGs and a local HTTP server; they cover 404,
invalid images, cancellation, timeouts/retry and preserving existing images.

Persistent review artifacts are under ignored `artifacts/libretro-qt/` (English
Classic and Chinese Dark screenshots) and `artifacts/libretro-package/` (wheel and
build log). No ROM/BIOS download or real-library migration was performed. Native
RetroArch gameplay, installed-device migration and physical input remain outside
this source validation.
