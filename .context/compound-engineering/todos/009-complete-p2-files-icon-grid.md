---
status: complete
priority: p2
issue_id: "009"
tags: [files, qml, handheld]
dependencies: ["008"]
---

## Problem Statement

The user finds the Files workspace too desktop-oriented and requests no location sidebar and an icon grid by default.

## Findings

The current full-height rail and single-column rows also own left/right navigation. Removing the rail requires matching grid navigation and keeping locations, bookmarks, trash and safe unmount reachable in the action menu.

## Proposed Solutions

Use a full-width responsive icon grid, keep breadcrumbs and a compact selected-item footer, and move locations/device choices into X actions. Keep file operations and external snapshots compatible.

## Recommended Action

Implement the approved focused visual/navigation adjustment with runtime QML and controller regression coverage. The user subsequently authorized scoped commit and push to main; device deployment remains separate.

## Acceptance Criteria

- [x] Files uses the full content width for icons and labels with no sidebar.
- [x] Direction keys match responsive columns, respect edges and preserve selection during resize.
- [x] Locations, bookmarks, trash and safe unmount remain reachable through X actions.
- [x] Existing batch, preview, clipboard, refresh and theme/language behavior passes focused regression.
- [x] Inspect English/Chinese Classic/Dark at both supported preview sizes and provide updated screenshots.

## Work Log

- 2026-11-09: User requested icon-first Files. Began focused layout/navigation update over the existing uncommitted Files work; unrelated material remains untouched.
- 2026-11-09: Implemented 4/5-column full-width icons, two-line labels, selected-item details and menu-based locations/device choices. Added controller boundary/resize/menu regression coverage and expanded the runtime QML probe for resize and last-row visibility.
- 2026-11-09: macOS and isolated Linux arm64 focused suites each pass 178 tests. All eight QML combinations pass, screenshots inspected, scoped Ruff and diff checks pass. Rebuilt local wheel/Debian artifacts, verified 236/168 source/resource files and ran unpacked-package QML probes. No commit, push, deployment or change to physical acceptance boundaries.
