# Emulator single-line game titles — 2026-11-15

This records the historical 0.2.20 delivery. Version 0.2.21 adds platform icons
for missing artwork; see [platform artwork verification](emulator-platform-placeholders-2026-11-15.md).

uDeck **0.2.20** (`35e65faee99b3bd390d211270c301b98bffd6eaa`) extends
single-line title scrolling to every Emulator platform, Recently played,
Favorites and the selected-game sidebar. The change is merged into and pushed
to `main`, and the package was installed on the uConsole.

## Behavior

Playlist cards, game cards and the sidebar share `ScrollingTitle.qml`. Titles
use one fixed font line. Newlines and paragraph separators become spaces for
display, and labels render as plain text; the original playlist labels remain
unchanged. Every Emulator card reserves font-based title/subtitle space, keeping
artwork and captions at consistent positions regardless of title length.

Unselected overflowing titles show an ellipsis. A selected long title waits
1.2 seconds, scrolls at 36 pixels/second, pauses at its end for 1.4 seconds and
repeats. Short titles remain still. Opening a menu, hiding the item or losing
window focus stops and resets scrolling. Changing the selected entry also
resets the sidebar, including entries with identical labels.

## Verification

- The new real Qt regression first failed because a selected GB game title never moved. It now checks GB, GBC, GBA, NES and PSP, Recently played and Favorites, sidebar scrolling and selection reset, short titles, embedded newlines, caption bounds, reaching the end and menu reset.
- Local English/Chinese × Classic/Dark title probes, the existing four Games menu/focus probes, shared native workflows and release checks: **30 passed in 233.74 seconds**. Ruff over `src tests` and whitespace checks pass.
- The arm64 package builds from the clean revision above in **119.32 seconds**. All **507 application files** match the binary package and source archive. This scoped build uses `DEB_BUILD_OPTIONS="parallel=4 nocheck"`; affected tests run separately.
- Installation verifies all **507 installed source files** and passes `dpkg --verify udeck` plus the installed preflight. The normal Emulator starts with no QML errors. All **39 protected configuration/save files**, the **7 other desktop processes**, cloud settings and the active/enabled save service are preserved.
- Installed-code isolated checks pass **10 shared-application smoke tests** and **four English/Chinese × Classic/Dark Qt title probes**. Each probe exercises all five fixture platforms and both collections, with an empty QML error list. GBC uses an isolated fixture because the normal library has no GBC playlist.
- The normal installed Wayland window is navigated with compositor keyboard events into its real **727-game GBA list**. Selecting a long existing Chinese game title produces **45 screenshots**. The card title has **34 distinct frames**, and the sidebar title has **42**; artwork and subtitle regions each retain **one identical pixel hash** across all frames. Both titles stay on one line. The screenshot GIF uses the measured capture intervals.
- All four normal playlists retain **730 entries**, all playlist bytes and **25 pre-existing save files** are unchanged, and favorites, recent records, positions, bookmarks, play records and core choices are preserved. Menu open/close and changing selection finish without QML errors. The Emulator remains idle inside GBA.

Package SHA-256:
`498755b35156de7d7e885cf0a2aea36dc811a8ec447ff1ab5bc8d5fb913ea82d`.

## Evidence and cleanup

Build and device evidence is retained in the main checkout's ignored
`artifacts/game-titles-0.2.20-20261115/` directory:

- `local-verification.json`, `build-result.json`, `package-verification.json` and `release/build-manifest.json` record source and package validation.
- `device-evidence/{installation,installed-tests,normal-session}-verification.json`, logs and `qt/` record installed-code tests and isolated screenshots.
- `device-evidence/normal-session/gba-library-final.png` is the foreground device screenshot. `frames/` contains the original 45 captures; `game-title-scroll.gif` shows the sequence, and `screenshots-verification.json` records the independent title/artwork/subtitle comparisons.
- `device-evidence/cleanup.json` records removal of `/var/tmp/udeck-game-titles-0.2.20-20261115`, including both temporary packages and test fixtures. This frees **61,427,712 allocated bytes** and leaves **24,965,214,208 bytes (24.97 GB)** available. All 507 installed source hashes, 39 protected file hashes, seven other desktop processes, cloud settings/service and `dpkg --verify udeck` pass again after cleanup. No uDeck build/backup paths remain under `/var/tmp` or `/var/backups`.

A screenshot remains on the device at
`~/.local/state/udeck/device-tests/game-titles-0.2.20.png`, alongside the durable
cleanup receipt. Generated fixtures and injected keys verify device software
behavior; human physical-input acceptance remains separate.
