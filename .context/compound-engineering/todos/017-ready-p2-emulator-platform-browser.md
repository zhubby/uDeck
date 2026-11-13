---
status: ready
priority: p2
issue_id: "017"
tags: [emulator, navigation, icons, device]
dependencies: []
---

## Problem Statement

All platforms currently mixes games from all systems. The approved design requires enabled-platform cards followed by each platform's games, with one bundled Monochrome icon set.

## Findings

Platform visibility must follow Settings core enablement, independently of game presence. Existing card caches also need to observe in-place core switches and probe results.

## Proposed Solutions

Keep the existing three tabs, add platform cards and independent browser locations, reuse the core catalogue's enabled candidate policy, and bundle pinned warm-gold RetroArch artwork.

## Recommended Action

Implement the user-approved plan, validate real Qt events and complete Debian tests, review, deliver main, and install the exact clean build on the existing uConsole.

## Acceptance Criteria

- [x] Enabled empty platforms show 0 games; disabled platforms are hidden.
- [x] Platform/game navigation, searches, focus, recent games and favorites pass regression tests.
- [x] Fixed Monochrome resources, attribution and packaging verified.
- [x] English/Chinese and Classic/Dark Qt probes pass; code review completed.
- [ ] Full Debian build/tests pass, main pushed and live ref checked.
- [ ] Exact package deployed, runtime verified, and requested device screenshots captured.

## Work Log

- 2026-11-13: Approved plan implemented in isolated `codex/emulator-platforms`; original 50 baseline tests passed and new navigation tests reproduced the missing behavior before implementation.
- 2026-11-13: 73 focused regressions and an additional 13 navigation/QML checks passed; all 60 SVGs render in Qt with fixed gold foreground. Ruff, lock consistency and wheel resource checks passed. Full Debian and device delivery remain pending.
