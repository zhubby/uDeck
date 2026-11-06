---
status: complete
priority: p2
issue_id: "006"
tags: [design, media, browser, reader, emulator, prototype]
dependencies: []
---

# uDeck five-app suite design

## Problem Statement

Design a music player, video player, browser, document reader and emulator frontend that belong to uDeck's current button-first interface. Use mature Linux frontends as references and cover complete interaction paths, rather than isolated home screens.

## Findings

- Current QML uses #151719 backgrounds, #f1eee7 foreground, #a8acae secondary text and #edb866 focus accents.
- Direction keys, A/B/X/Y, L/R and a real keyboard are the established input vocabulary. Ordinary letter keys must remain text input.
- English is the default; Simplified Chinese is supported. Application content remains literal.
- Emulator gameplay, browser page interaction and media playback require explicit input ownership and return behavior.

## Proposed Solutions

Create a shared design specification, source-grounded reference study and interactive five-app prototype, with keyboard navigation and bilingual states at 1280×720 and 960×600. Keep review controls outside the product viewport and production application code unchanged during this design task.

## Recommended Action

Research upstream interaction patterns; implement the full design prototype; inspect screenshots and keyboard flows; document native integration and remaining device checks; review and deliver the design assets.

## Acceptance Criteria

- [x] All five apps have coherent library/start screens and their primary content/detail states.
- [x] A/B/X/Y, directional navigation, L/R and text entry behave consistently and preserve focus on return.
- [x] Music queue, video resume/tracks, browser tab/navigation modes, reader contents/bookmarks, emulator states/return are represented with usable flows.
- [x] English and Chinese, long text, empty/loading/error/removable-source states are designed and exercised.
- [x] Rendered layouts and interaction tests cover 1280×720 and 960×600.
- [x] Reference sources, native integration choices, evidence and design boundaries are documented.

## Work Log

### 2026-11-06

- Started from 08c195d on codex/udeck-app-suite-design; existing worktrees and unrelated records retained.
- Read the current shell, Terminal, input ownership and i18n contracts. Researching Elisa, Celluloid/mpv, Angelfish/Falkon, KOReader/Okular, Pegasus, ES-DE and RetroArch.

### 2026-11-07

- Completed the five-app offline interactive prototype with original artwork, bilingual flows, nested focus/return paths and source-loss recovery.
- Documented app-specific screens and controls, upstream reference mapping, candidate native engines, input ownership and separate device acceptance requirements.
- Sequential code review fixed disabled menu focus, queue return, video folder filtering/chapter boundaries/subtitles, browser modes/IDs/text focus, reader PDF/search/bookmarks, empty save state handling, compact clipping and stale notifications.
- Final Chromium run: 499 checks passed, 195 screenshots, both languages and 1280×720 / 960×600; source hashes retained with the report. JavaScript syntax and Ruff passed.
- Production src/tests/tools/dependencies and the Terminal worktree were unchanged. Native playback, real websites/document engines and actual emulation remain future implementation acceptance, not evidence claimed by this design delivery.
