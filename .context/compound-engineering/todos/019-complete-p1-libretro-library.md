---
status: complete
priority: p1
issue_id: "019"
tags: [emulator, libretro, playlists, migration]
dependencies: []
---

# Libretro library compatibility

## Problem Statement
The Emulator library must use interoperable JSON .lpl playlists, standard database directory names and thumbnails, while preserving existing saves during ROM relocation.

## Findings
At the initial baseline (`6d87012`), the library scanned enabled platform folders, bound game IDs to paths and read adjacent covers. Implementation was isolated on `codex/emulator-libretro-library` and is now delivered on `main` as uDeck 0.2.17.

## Proposed Solutions
Use explicit playlist generation and playlist-only refresh, persist content identities separately from playlist entries, and provide journalled relocation plus asynchronous missing-thumbnail downloads.

## Recommended Action
Implement the user-approved plan sequentially in this worktree. Do not commit, push or install on a device without a corresponding user instruction.

## Acceptance Criteria
- [x] JSON playlist round trips, portable paths, core precedence, archive members, stable game identities.
- [x] Playlist navigation, independent directory settings and scan preview.
- [x] Standard thumbnail lookup, preview selection, cancellable missing-image downloads.
- [x] Preflight, classification, journalled migration/recovery and preserved saves/records.
- [x] Isolated filesystem/HTTP tests, translated Qt keyboard probes, regressions, Ruff, package resource check and documentation.

## Work Log
- 2026-11-15: User approved the complete implementation plan. Read current code and established isolated worktree; baseline validation started.
- 2026-11-15: Source implementation validation complete: 240 affected tests, four bilingual/theme Qt probes, final thumbnail tests, Ruff and wheel resource checks passed. Delivery had not yet been authorized at this stage.
- 2026-11-15: User authorized main delivery and device deployment. Merged/pushed `ecf8756` and release `3348cdf` (0.2.17); the arm64 release build passed all 1705 tests, 506 packaged/source files matched, and Debian lifecycle validation passed. Installed-code device checks passed 224 regressions, four bilingual/theme Qt keyboard probes and real Wayland/Gambatte save/migration acceptance.
- 2026-11-15: Migrated 731 existing ROM/resource files into the standard layout with 730 entries in four playlists; preserved all three legacy IDs, records, native saves, core choices and enabled cloud profile. Verified the committed journal, final paths, protected hashes and desktop process continuity. Captures were corrected for foreground activation and display power state.
- 2026-11-15: User requested obsolete build/backup removal. Moved five live log inodes to the user state directory, removed 78 obsolete paths and released 2,654,302,208 bytes. Final installed-source, dpkg, library, cloud/service and protected-data verification passed; evidence is recorded in docs/udeck/emulator-libretro-2026-11-15.md.
