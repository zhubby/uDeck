# Emulator playlist card sizing and scrolling — 2026-11-15

This records the historical 0.2.19 delivery. The uConsole now runs 0.2.20,
which extends this behavior to every platform's games and the sidebar; see
[single-line game title verification](emulator-game-titles-2026-11-15.md).

uDeck **0.2.19** (`b8db50f77123beaa955829e5a4d628391a358a55`) fixes playlist
artwork sizing and long-name readability. The change is merged into and pushed
to `main`, and the package was installed on the uConsole.

## Behavior

Every playlist card reserves the same font metrics for one title line and one
game-count line. Artwork height no longer depends on a title wrapping onto a
second line. Short and long names therefore have identical artwork bounds and
caption positions, within each language's font metrics.

Unselected long names show an ellipsis. Selecting an overflowing title waits
1.2 seconds, scrolls left at 36 pixels/second until its end is visible, pauses
for 1.4 seconds, and restarts from the beginning. Short titles remain still.
Changing selection, opening a menu, hiding the card or deactivating the window
stops the animation and restores its starting position. Text is clipped within
its own title area, keeping the count and neighboring cards clear.

## Verification

- The real Qt regression first reproduced unequal icon heights for short and wrapped names: **77 versus 45 pixels**, at the same card size and font. It now checks identical artwork/caption geometry across five short and long playlist names.
- The probe verifies the initial reading pause, scrolling through to the end, stopping/resetting behind a menu and after arrow-key selection changes, and a stationary short title.
- Local English/Chinese × Classic/Dark Qt probes, native workflows and empty-library menus for shared applications, and release checks: **26 passed**. Ruff over `src tests` and whitespace checks pass.
- The arm64 package builds from the clean revision above in **131.26 seconds**. All **506 application files** match both the binary package and source archive. This scoped build uses `DEB_BUILD_OPTIONS="parallel=4 nocheck"`; the affected tests run separately. The earlier full **1,710-test** result belongs to 0.2.18, as recorded in the [Libretro delivery report](emulator-libretro-2026-11-15.md).
- Installation verifies all **506 installed source files**, passes `dpkg --verify udeck`, and starts the normal Emulator with **no QML errors**. All **39 pre-existing protected configuration/save files** retain their hashes. The **7 other desktop application processes** retain their PIDs and start times, and cloud settings plus the active/enabled save service are preserved.
- The installed code passes **10 shared-application empty-library/menu checks** in isolated settings and a private D-Bus session.
- All **four installed-code Qt probes** pass: English/Chinese × Classic/Dark, including identical card dimensions, complete title scrolling and reset after menu/selection changes, plus the existing navigation, native-save menus, thumbnail and scan-preview checks. Each probe reports an empty QML error list.
- The normal installed Wayland window is operated with compositor keyboard events. Its four original playlists retain **730 games**. All list bytes, **25 save files**, favorites, recent records, positions and core choices are preserved.
- **40 foreground screenshots** record the selected long title. The title has **30 distinct rendered frames**; artwork and game-count regions have **one identical pixel hash each across all 40 frames**. The actual screenshots also confirm aligned artwork and single-line captions across the four cards. Menu open/close and changing selection complete without QML errors.

Package SHA-256:
`aff5a963cdb64117a08e4071b3e0cdfab5c4816845d582008ccf0a1cd4772c2d`.

Build, package and device evidence is retained in the main checkout's ignored
`artifacts/playlist-cards-0.2.19-20261115/` directory:

- `local-verification.json`, `package-verification.json`, `build.log` and `release/build-manifest.json`: source revision, affected tests, build and package/source hashes.
- `device-evidence/{installation,installed-tests,normal-session}-verification.json` and the associated logs: upgrade, installed-code checks and normal-session preservation.
- `device-evidence/normal-session/playlist-cards.png`: actual foreground library; `frames/` contains the 40 original screenshots. `title-scroll.gif` is a cropped animation of those frames, and `screenshots-verification.json` records unchanged artwork/count pixels during scrolling.
- `device-evidence/qt/`: isolated installed-code screenshots in both languages and themes, including the start/end of the scrolling title.
- `device-evidence/cleanup.json`: deletion of the temporary upgrade directory and post-cleanup verification. A durable copy remains on the device at `~/.local/state/udeck/device-tests/playlist-cards-0.2.19-20261115-cleanup.json`.

After copying evidence locally, the temporary installation, rollback package and
test directory `/var/tmp/udeck-playlist-cards-0.2.19-20261115` was removed, freeing
**61,370,368 allocated bytes**. Available disk space is **24,966,639,616 bytes
(24.97 GB)**. All 506 installed source hashes, 39 protected configuration/save
hashes, 7 other desktop processes, cloud settings/service state and
`dpkg --verify udeck` pass again after deletion. The normal Emulator remains
idle on 0.2.19, with no QML errors and no remaining uDeck build/backup paths under
`/var/tmp` or `/var/backups`.

Generated fixtures, Qt events and compositor-injected keys verify software
behavior; human physical-input acceptance remains separate.
