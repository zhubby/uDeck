---
status: complete
priority: p1
issue_id: "007"
tags: [apps, native, media, reader, browser, games]
dependencies: ["006"]
---

## Problem Statement

Implement the approved Music, Video, Browser, Reader and Games design as independent native applications, with actual engines and persisted state.

## Findings

The design is committed in `docs/design/app-suite/`. Qt 6.8 WebEngine, PDF and Multimedia modules are available locally and in Debian arm64 repositories. The device has RetroArch 1.20 with command support and GB/GBA/SNES cores. Terminal and its input protocol must stay compatible.

## Proposed Solutions

Share source indexing, atomic state, focus/menu ownership, translations and input routing. Keep media, browser tabs, document positions and emulator saves in separate adapters. Validate QtMultimedia as the composited media engine; use QtWebEngine, QtPdf, pinned foliate-js and external RetroArch.

## Recommended Action

Implement sequentially in `codex/udeck-app-suite`, test actual behavior with original fixtures, review and fix, package, then merge and push the scoped changes as authorized. Record physical acceptance separately.

## Acceptance Criteria

- [x] Shared source identity, cancellable indexing, source removal and atomic state.
- [x] Native input ownership without changing ordinary letters or Terminal behavior.
- [x] Music library/queue/playback/output/background, Video resume/seek/tracks/chapters.
- [x] Real Browser tabs/history/bookmarks/address and navigation/reading/pointer/text modes.
- [x] Reader TXT/PDF/EPUB, logical positions, contents/search/bookmarks/zoom.
- [x] Games preflight, actual RetroArch process, pause/save/load/auto resume with verified files.
- [x] English/Chinese settings, keyboard/gamepad menus, stable focus and error states.
- [x] Tests, Ruff, QML/native probes, Debian packaging and device evidence.
- [x] Review fixes committed; main merged, pushed and remote ref verified.

## Work Log

2026-11-07: User approved implementation. Created isolated feature branch from approved design. Verified target dependency availability and preserved existing Terminal PID 381833 and USB Wi-Fi route.

2026-11-07: Implemented all five independent Qt applications and native shell routing. Serial review corrected twelve findings, including composited video, real browser input/history, document session isolation, and emulator save/load confirmation. Local suite: 332 passed, 2 native-plugin skips. Device suite: 332 passed, 2 skips; both skipped tests then passed with the installed Terminal plugin. Ruff, wheel and arm64 packages passed. Installed udeck 0.1.7 and udeck-apps 0.1.0, restarted only the shell unit, and verified all five installed apps on Wayland with their native broker enabled. Terminal PID/start time, network and login session preserved; display restored off. See docs/apps/verification.md and docs/apps/review.md for evidence and physical acceptance boundaries.

2026-11-07: Feature commit 8375eb13f20e088d0673e00f8696c6b5cb9d3c8f fast-forwarded into main and pushed to origin. Independent git ls-remote returned the same main SHA. Existing untracked research files in the primary checkout were preserved. Completed the delivery record; remaining physical acceptance is explicitly documented, not counted as automated success.
