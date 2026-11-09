---
status: complete
priority: p1
issue_id: "008"
tags: [files, qml, safety, handheld]
dependencies: []
---

## Problem Statement

Files needs the complete approved lightweight handheld file-manager workflow, including the two reproduced focus/refresh regressions.

## Findings

Rename loses selection after reordering; returning to Files does not refresh external changes. Search is application-only, file rows lack metadata/type icons, transfer progress is indeterminate, and batch/recovery/location workflows are absent. Full lists are duplicated in the generic QML snapshot.

## Proposed Solutions

Use focused filesystem helpers, a Files controller mixin and incremental list model, and a compact Files-only surface. Preserve existing mutation safeguards and external snapshots.

## Recommended Action

Implement the approved complete scope sequentially using `docs/superpowers/plans/2026-11-08-files-workspace.md`.

## Acceptance Criteria

- [x] Focus/refresh regressions covered by tests.
- [x] Navigation, search/sort/filter, bookmarks and rich compact rows work with controller navigation.
- [x] Batch copy/move/trash, safe conflict choices, progress/cancel/background operation work.
- [x] Preview, open-with, mounted-device and trash-recovery flows are reachable and validated within the documented automated scope.
- [x] Large listings do not enter the compact QML snapshot; external snapshots remain compatible.
- [x] English/Chinese, Classic/Dark, QML tests and packaging resources verified.
- [x] Existing sessions/defaults/unrelated work preserved; physical acceptance boundaries recorded.

## Work Log

- 2026-11-08: User approved all assessed functionality. Started test-first implementation; no deployment or Git delivery requested for this change.
- 2026-11-09: Completed all approved Files workflows, including safe batch jobs, same-filesystem trash recovery, incremental QML data and focus/refresh fixes. Corrected hidden-editor shortcut focus, long preview metadata overflow and post-EXIF image bounds through regression coverage.
- 2026-11-09: macOS/Linux arm64 focused suites each pass 165 tests. Full suite reports 861 passed, 3 skipped and 2 independently reproduced baseline Reader failures. Scoped Ruff and eight QML combinations pass. Wheel and Debian resources match source, and both unpacked-package QML probes pass. Screenshots and detailed evidence are recorded in `docs/udeck/files-workspace-2026-11-08.md`.
- 2026-11-09: No commit, push, package installation, default change or device deployment performed. Real GIO operations/authorization, installed-app launch, USB hotplug/unmount, physical controls and device display remain separate acceptance gates.
- 2026-11-09: User subsequently requested commit and push to main for the complete Files workspace, icon grid and Tabler assets. Device deployment remains outside this Git delivery.
