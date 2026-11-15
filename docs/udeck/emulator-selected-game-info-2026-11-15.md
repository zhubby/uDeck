# Selected-game information on uConsole — 2026-11-15

uDeck **0.2.23**, application revision
`4c06ede7c829ede59098cd6612b47dc7ac569677`, is installed on the uConsole.
The implementation is merged into and pushed to `main`.

## Behavior

The selected-game sidebar now shows four information rows beneath the cover
and single-line title: platform/content format, resolved core, last played and
accumulated session time. Archive-member entries show both the member format and
container format. The database distinguishes Game Boy from Game Boy Color.

Each list entry retains its own core selection, using the existing entry/list/
platform precedence. History uses the stable game ID, so different labels and
custom playlists share play records. Unavailable or disabled cores and cores
still being checked have explicit states.

RetroArch must confirm playing or paused content before a session enters recent
history or receives a timestamp. Exit updates the timestamp and accumulated
duration. Timestamps are stored as epoch seconds and displayed in the device's
current timezone. Session duration retains the existing pause-inclusive policy.
Legacy records retain their duration and show “Time not recorded”; new games
show “Not played yet”. ROM and save modification dates are not substituted for
missing history.

Long values use the existing single-line marquee, reset on selection and pause
when a menu opens or the window becomes inactive. The information area scrolls
vertically when the window is too short. Its wheel handling clamps to the actual
viewport after resizing, while arrow keys continue to navigate the game grid.
The shared Music sidebar retains its existing layout and playback behavior.

## Verification

- Final source checks: **103** related tests, **1** native Music/QML workflow,
  Ruff and whitespace checks pass. The preceding broad regression also passed
  the **8** existing game menu/title probes. The four new information probes
  cover English/Chinese × Classic/Dark, shared history with entry-specific
  cores, legacy/unplayed states, marquee behavior, back focus and scrolling at
  960×600 and 800×500.
- Binary and source archives contain **508** application files matching the
  clean implementation revision. Installed files match the same manifest;
  `dpkg --verify udeck` is clean.
- Installed source: **63** game-information, frontend, save and playlist
  regression tests plus the **4** language/theme information probes pass.
- Real native device runs pass for original GB, NES and GBA fixtures, plus
  no-content 2048 and Mr.Boom. These cover launch, pause, save/load, automatic
  save/return, restoring a disabled core and resume. GB/NES/GBA timestamps and
  accumulated time survive state-file reload and subsequent sessions. The test
  library and native saves are isolated; **69** existing configuration, save,
  playlist and thumbnail files retain their hashes.
- Compositor key events exercise the normal installed GBA library, metadata
  selection and returning from details. It retains **730 entries in 4 lists**,
  including **727 GBA entries**. F1 2002 correctly shows an unplayed state;
  Original red retains **8 min** of legacy history with no invented date.
  Favorites, recent records, durations, core choices, list bytes and all **25**
  pre-existing native save files are preserved. Normal-session QML errors are
  empty.
- Installation preserves **39** protected configuration/native-save files,
  **7** other desktop processes, cloud configuration and the active/enabled
  save service. These are automated device checks, not new human physical-input
  or cloud-transfer acceptance.

After evidence was copied locally, deployment staging and its temporary rollback
package were removed, releasing **64,847,872 bytes**. Free space is now
**24,959,127,552 bytes** (24.96 GB); no uDeck build/backup paths remain under
`/var/tmp` or `/var/backups`. Installed files, protected data, desktop processes,
save service and normal-session health pass again after cleanup. The durable
receipt is `~/.local/state/udeck/device-tests/selected-game-info-0.2.23-20261115-cleanup.json`.

The arm64 package SHA-256 is
`e0b0c8ec2e32420cbe67dc6dfd19e569adb9fbe7054c6f73e79a63e3013ed551`.

Receipts, package/source manifests and screenshots are in the main checkout's
ignored `artifacts/selected-game-info-0.2.23-20261115/` directory. Device evidence
is under `device-evidence/`; the normal Wayland screenshots are
`normal-session/gba-selected-game-info.png`,
`normal-session/gba-legacy-game-info.png` and `normal-session/gba-final.png`.
