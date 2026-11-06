---
status: complete
priority: p2
issue_id: "005"
tags: [i18n, qml, settings]
dependencies: []
---

# English and Simplified Chinese interface

## Problem Statement

uDeck embeds Chinese interface text in QML and Python. Add English as the default and persist an English / Simplified Chinese selection in Settings.

## Findings

- Shell, backend prompts, input menus and Terminal own interface text.
- User content (SSID, filenames, application titles, terminal output) must remain literal.
- Settings are atomically persisted in ConfigStore; mock mode uses temporary configuration.

## Proposed Solutions

Use shared translation catalogs and explicitly marked, deferred messages. Render marked messages at the presentation boundary so existing dialogs can change language without losing navigation, passwords, or operations. QML uses the same catalog through its controller.

## Recommended Action

Implement sequentially: translation layer and validated preference; shell/settings/QML; backend and Terminal integration; regression and visual verification; code review and delivery.

## Acceptance Criteria

- [x] Fresh, legacy and invalid language preferences default to English.
- [x] Settings offers English and 简体中文, applies immediately and survives restart.
- [x] Authored shell, menus, prompts and Terminal text uses catalogs; user content stays intact.
- [x] Switching preserves focus, modal input and active terminal sessions.
- [x] Failed preference writes retain the previous selection and show a localized error.
- [x] Both locales pass automated tests, Ruff and QML smoke/screenshots.
- [x] Code review, documentation and scoped delivery completed.

## Work Log

### 2026-11-06

- Started from clean c56910a on codex/udeck-i18n in the existing feature checkout.
- Preserve unrelated primary checkout files and the Terminal worktree.
- Implemented 421 shared messages, persisted Settings / Quick settings selection and Terminal synchronization.
- Serial code review fixed five P2 findings; details are in the i18n review artifact.
- Final local suite: 289 passed, 2 native-plugin skips, 13 existing warnings; Ruff and wheel passed.
- uConsole full suite: 291 passed with native PTYs. Installed 0.1.6 / Terminal 0.1.1 and verified 32 installed source/resource files.
- Live virtual keys verified bilingual selection and persistence across shell restart; restored English and original screen power.
- Preserved the existing Terminal process, unrelated device configuration, source records and other worktrees. Physical acceptance remains tracked separately.
