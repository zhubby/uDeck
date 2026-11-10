---
status: ready
priority: p2
issue_id: "013"
tags: [input, shell, wayland]
dependencies: []
---

# Trackball clicks and global control panel

## Problem Statement

Map the built-in trackball press to a left click and a hold longer than two seconds to a single right click. Provide a global Ctrl+Shift+Esc panel with Home, Running Apps, Settings, Power Off and Restart.

## Findings

- The stock mouse interface reports the trackball as BTN_MIDDLE (274), independently of L/R.
- PointerGuard owns this interface; recovery releases must not turn into synthetic clicks.
- The shell uses button navigation. Third-party apps need Wayland virtual pointer events.
- labwc owns global shortcuts. Existing power actions already require confirmation.
- The main checkout contains unrelated startup/loading and cursor work; preserve it.

## Proposed Solutions

Reuse the native input reader, Wayland virtual pointer, shell menu and confirmation controls. Keep physical test edges separate from semantic clicks. Cancel holds on input loss, focus changes, diagnostic mode and inactive/locked sessions.

## Recommended Action

Implement sequentially in the existing isolated worktree on codex/udeck-trackball-console, validate, merge to main and push. Attempt the previously authorized device deployment if authenticated access is available.

## Acceptance Criteria

- [x] Short release produces one left click; a hold over 2 seconds produces one right click and no left click.
- [x] Focus/input/session loss and diagnostics never synthesize a click; raw diagnostic edges remain available.
- [x] Built-in trackball motion and clicks reach focused apps through the existing Wayland protocol.
- [x] Global Ctrl+Shift+Esc opens exactly five actions, ignores repeat, and Esc/B restores the previous window.
- [x] Power actions require confirmation; new UI text follows themes and both languages.
- [ ] Automated input/routing/QML checks and review pass; main/remote equality is verified.
- [x] Device/software and physical acceptance boundaries are recorded separately.

## Work Log

- 2026-11-10: Continued from the existing input investigation. Verified clean feature worktree at f3bf6d6 and inventoried unrelated dirty main-checkout changes.
- 2026-11-10: Implemented timed trackball gestures, global panel, compositor/CLI/D-Bus entrypoints and existing-desktop shortcut configuration with a byte-exact backup. Debian arm64 full suite: 1146 passed; after the queued-event timing refinement, 81 focused regressions and the actual Wayland/Xwayland protocol probe passed. Ruff and whitespace checks passed. Device SSH timed out twice; hardware deployment and physical acceptance remain pending access.
