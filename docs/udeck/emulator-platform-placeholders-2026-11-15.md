# Emulator platform artwork placeholders — 2026-11-15

uDeck **0.2.21** (`233e58a977c6e58c5e00e577d83cf96ec47a11cd`) replaces the
Emulator's generic plus-sign placeholder with the selected game's platform
icon. The change is merged into and pushed to `main`, and the package is
installed on the uConsole.

## Behavior

Game cards, the selected-game sidebar and game details display cover artwork
first. When an image is absent, loading or unreadable, they display that game's
bundled RetroArch Monochrome platform icon with its original aspect ratio.
Unrecognized platforms use the bundled generic gamepad. Custom mixed-platform
playlists, Recently played and Favorites choose each game's platform independently.
GB and GBC share the existing GB platform icon, matching their playlist icons.

The original cover paths and playlist labels are preserved. The shared image
component keeps existing artwork behavior for the other applications. Fixed
card dimensions and single-line title scrolling remain in place.

## Verification

- The extended real Qt regression first fails against 0.2.20 because the game card has no platform-image fallback. It now checks GB, GBC, GBA, NES and PSP cards and sidebar previews, mixed GB/NES/unknown entries, generic gamepad fallback, valid-cover priority, corrupt-image fallback in cards/sidebar/details, and Recently played/Favorites. Existing title scrolling and menu/focus checks also pass.
- Local English/Chinese × Classic/Dark Qt probes, playlist-browser tests, shared native workflows and release checks: **39 passed in 259.05 seconds**. Ruff over `src tests` and whitespace checks pass.
- The arm64 package builds from the clean revision above in **123.32 seconds**. All **507 application files** match the binary package and source archive. This scoped build uses `DEB_BUILD_OPTIONS="parallel=4 nocheck"`; the affected tests run separately.
- Installation verifies all **507 installed source files**, the installed preflight and `dpkg --verify udeck`. The normal Emulator starts without QML errors. **39 protected configuration/save files**, **seven other desktop processes**, cloud settings and the active/enabled save service are preserved.
- Installed code passes **10 shared-application smoke tests** and **four English/Chinese × Classic/Dark Qt probes**. Each probe checks all five platforms and the artwork cases above. Each reports three expected image-decoding diagnostics from the intentionally corrupt fixture and no unexpected QML errors.
- The normal installed Wayland application is navigated with compositor keyboard events through the real GB, NES, PSP and **727-game GBA** playlists. Screenshots show the corresponding platform icon in game cards and the sidebar. The application remains idle in GBA, selecting the short `Original red` title for the final screenshot.
- **45 actual GBA frames** also verify scrolling: the card title has **36 distinct frames**, the sidebar title **33**, while the platform-artwork and subtitle regions each have **one unchanged pixel hash**. Menu and selection reset complete without QML errors.
- All four normal playlists retain **730 entries**, every playlist byte and **25 pre-existing save files** are unchanged, and favorites, recent records, positions, bookmarks, play records and core choices are preserved.

Package SHA-256:
`ad72ee270411175c3b1d659479721f2322d14bbd44a5275ef70653ab76b97f01`.

## Evidence and cleanup

Evidence is retained in the main checkout's ignored
`artifacts/platform-placeholders-0.2.21-20261115/` directory. Build/package/local
verification receipts identify the clean revision and hashes. Under
`device-evidence/`, installation, installed-test and normal-session receipts
record the device checks; `qt/` contains isolated screenshots, including valid
and corrupt cover cases. `normal-session/` contains actual GB/NES/PSP screenshots,
`gba-library-final.png`, the 45 original frames, `game-title-scroll.gif` and the
pixel-comparison receipt `screenshots-verification.json`.

After collecting evidence, `/var/tmp/udeck-platform-placeholders-0.2.21-20261115`
was removed, including both temporary packages and test fixtures. Cleanup frees
**62,963,712 allocated bytes** and leaves **24,963,842,048 bytes** available.
The 507 installed hashes, 39 protected files, seven other desktop processes,
cloud settings/service and `dpkg --verify udeck` pass again after deletion; no
uDeck build/backup paths remain under `/var/tmp` or `/var/backups`.

A screenshot remains at
`~/.local/state/udeck/device-tests/platform-placeholders-0.2.21.png`, with a
durable cleanup receipt alongside it. These tests exercise installed software
and the device compositor; human physical-input acceptance remains separate.
