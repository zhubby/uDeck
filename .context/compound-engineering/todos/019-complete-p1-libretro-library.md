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
The existing library scans enabled platform folders, binds game IDs to paths, and reads adjacent covers. Current main is 6d87012. Work is isolated on codex/emulator-libretro-library.

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
- 2026-11-15: Implementation and source validation complete: 240 affected tests, four bilingual/theme Qt probes, final thumbnail tests, Ruff and wheel resource checks passed. Full-run failures and their targeted follow-up are recorded in docs/udeck/emulator-libretro-2026-11-15.md. No commit, push, device installation or real-library migration performed.
