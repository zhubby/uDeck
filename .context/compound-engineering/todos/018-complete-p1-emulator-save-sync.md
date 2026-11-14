---
status: complete
priority: p1
issue_id: "018"
tags: [emulator, saves, rclone]
dependencies: []
---

## Problem Statement

Emulator needs RetroArch native import/export, recoverable history and persistent
multi-device rclone synchronization, as approved in the current chat.

## Findings

Existing saves are atomic and core-hash scoped, but local game IDs include the
ROM root identity. SRAM must not be restored while its game is running.

## Proposed Solutions

Use immutable native snapshots with portable content identity and parent links;
delegate transfer and filesystem synchronization to rclone bisync.

## Recommended Action

Implement the approved plan in docs/superpowers/plans/2026-11-14-emulator-native-save-sync.md.

## Acceptance Criteria

- [x] Native bytes round-trip with backups and compatibility checks.
- [x] Full history syncs and offline conflicts converge after explicit choice.
- [x] User background service and bilingual keyboard-accessible UI work.
- [x] Relevant regressions, real-rclone integration, Qt probes and wheel packaging pass.

## Work Log

- 2026-11-14: User approved implementation. Started test-first native/history layer
  on codex/emulator-save-sync; no commit, push or device changes requested.
- 2026-11-14: Implemented native management, automatic immutable history,
  recoverable rclone bisync, D-Bus/systemd integration and bilingual menus.
  Focused 159-test suite passed; shared-app (81), save/terminal (90), and remaining
  modules (427 passed, 4 skipped) passed separately. Full single-process run
  aborted in a terminal Qt test; recorded that limitation. Cloud-provider,
  Debian install and uConsole acceptance remain separate. No commit or deploy.
- 2026-11-14: User authorized commit, merge to main, push, actual uConsole
  deployment and screenshots. Prepared 0.2.16 for an identifiable package upgrade;
  deployment evidence will be recorded after installed-device verification.
