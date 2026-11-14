# RetroArch native save management and rclone sync

The approved plan adds native `.state`, `.stateN`, `.state.auto`, `.srm` and
`.rtc` import/export, automatic local history, and persistent multi-device sync.
Files retain their original bytes. Instant states retain exact core-hash
compatibility; SRAM remains shared by versions of the same core.

Implementation runs sequentially in this chat. Commit, push and deployment
are separate from this implementation request.

- [x] Native file management and immutable history (`emulator_saves/native.py`,
  `history.py`, `store.py`): byte-for-byte round trips, backup before overwrite,
  game locks, content-based matching, verified restores and causal conflict heads.
- [x] Background transport (`sync.py`, `daemon.py`, `client.py`): configured
  rclone remotes, access marker, first-run baseline, recoverable bisync, serialized
  jobs, persisted configuration, periodic retry and user D-Bus notifications.
- [x] Emulator integration (`apps/emulator/save_management.py`, controller):
  native file pickers and confirmations, backup/history/restore, sync settings,
  asynchronous work, pre-launch sync gate and game-lifetime ownership.
- [x] Packaging, bilingual messages, documentation and validation: systemd user
  service and D-Bus activation, optional rclone recommendation, real-rclone
  two-device tests, Qt keyboard probes, emulator regressions and wheel build.

Snapshots contain native files and a versioned JSON manifest recording identity,
SHA-256, origin device, time, and parent snapshot IDs. Cloud credentials remain in
rclone. Each device publishes unique immutable directories. Divergent progress
is resolved explicitly by creating a child of both competing versions.

Cloud synchronization defaults off; local history defaults on. Keep full
history without automatic pruning. Synchronize before launch, after confirmed
state saves and clean SRAM flush, and every 60 seconds while idle. Offer retry,
wait and offline launch after 30 seconds. Background work follows the user
session and persists when the emulator window closes.

Actual cloud-provider transfers and physical uConsole acceptance require their
own evidence; local filesystem rclone tests do not establish either.

Validation completed on 2026-11-14: 159 emulator, native-save, real-rclone,
private-D-Bus, Qt, localization and release tests passed. Another 81 shared-app
tests passed, as did 90 save/terminal interaction tests. The remaining 26
modules passed in a fresh process (427 passed, 4 skipped). Ruff, diff checks,
lockfile checks and the wheel build passed; wheel payloads are checked against
the edited sources.

The single-process full-suite attempt aborted in a terminal Qt event test at
74%; that terminal module passed alone (24 tests) and alongside the save tests.
Its four Qt menu failures were rechecked successfully by the latest focused
suite after fixing truncated import details. No clean single-process full-suite
result is claimed. Debian installation, actual cloud-provider and uConsole
acceptance remain separate. Evidence is in artifacts/emulator-save-sync/.
