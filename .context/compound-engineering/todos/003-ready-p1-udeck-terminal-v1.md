---
status: ready
priority: p1
issue_id: "003"
tags: [terminal, qt, input, delivery]
dependencies: []
---

# uDeck Terminal v1

## Problem Statement

Implement the user-approved Qt Quick / QMLTermWidget terminal and deliver it on CM4. The terminal becomes the system default only after the agreed acceptance gates pass.

## Findings

- Implementation is isolated at the app-managed `udeck-terminal-v1` worktree, branch `codex/udeck-terminal-v1`; the original checkout and unrelated hardware archives are preserved.
- CM4 at 192.168.11.59 is running Debian 13.5 / Qt 6.8.2 / labwc 0.9.2. Installed `udeck 0.1.4` and `udeck-terminal 0.1.0` arm64.
- Final build: `5339088bbd72cdf484a0fdb5fcf57fd34b1663036fb904e7da71f8e77d04d93a`.
- Local and CM4 full suites: 157 passed each, with 13 existing dbus-next deprecation warnings. Installed Wayland/Xwayland, CLI/IPC, TUI, input ownership and isolated defaults restoration probes pass.
- Final 60.0396-second CM4 sample: first frame 1.998 seconds, RSS 195.609 MiB, idle CPU 0.01666% of one logical core. All performance gates pass.
- Human physical input, real IME and hardware recovery remain pending. Original system default remains auto → lxterminal. Global default rollout/restore is deliberately gated.

## Proposed Solutions

Use a pinned Qt 6 QMLTermWidget plugin, independent QApplication terminal process, reused foreground Gamepad input, directed desktop L/R IPC, and Debian/XDG default integration with backups.

## Recommended Action

Execute the plan approved in the conversation sequentially in the main agent. Keep local, device, synthetic-input and physical acceptance distinct. Preserve the previous default until critical acceptance succeeds.

## Acceptance Criteria

- [x] Pinned plugin builds; real PTY / Unicode / synthetic IME interfaces and target TUI probes pass.
- [x] CLI argv/cwd/environment, windows/tabs and process lifecycle are implemented and tested.
- [x] QML menus, copy/search/paste/font and close confirmation pass automated keyboard/native-buffer checks.
- [x] Foreground ABXY and directed/local L/R ownership pass regression and actual device-grab checks.
- [x] Debian packages, desktop/file/Gio integration, defaults apply/restore tools and usage docs are implemented and installed.
- [x] CM4 performance and installed Wayland/Xwayland results are recorded.
- [ ] Human uDeck/original-desktop input, real IME and physical focus/hardware recovery acceptance pass.
- [ ] System defaults are applied, verified through real launch paths and restored once, only if gates pass.

## Work Log

### 2026-11-06 — implementation started

Read the approved plan, inspected input, window and package contracts, created an app-managed worktree, verified the 109-test baseline and resolved QMLTermWidget HEAD to 8913504fa2ebd220ebe7c680c32954e1b3c035c5.

### 2026-11-06 — implementation and installed automatic acceptance complete

Built and installed the system-Qt ARM64 plugin and both packages. Fixed modal shortcut isolation, asynchronous window-close fencing, existing-primary directory launches, Wayland service identity and IME UTF-16/candidate queries. Ran 157 tests on both hosts and installed real-window/TUI/IPC/ownership/default rehearsal probes. Verified package bytes, owners, permissions and disjoint file ownership. Final performance gates pass. Requested human uDeck/IME observation and retained a terminal shell for it. No system default change, commit or push. Evidence and remaining rollout steps are in `docs/udeck/terminal-acceptance-2026-11-06.md` and `artifacts/cm4-2026-11-06/`.

Generated `dist/udeck-terminal-v1-cm4.tar.gz` with both packages, complete corresponding source, licenses/patches, docs and evidence. Verified all 35 manifest entries, all 24 packaged Python/QML source files against the checkout, and local/device SHA256SUMS. Copied the final bundle and source to the device's build directory. Remaining work requires actual physical observations before global default rollout.

### 2026-11-06 — physical checks deferred; Git delivery requested

The user is temporarily unable to perform physical testing and explicitly requested committing, merging into main and pushing. Keep all physical/IME/recovery gates pending and retain lxterminal as the system default. Git delivery includes only this terminal feature and its records; preserve unrelated hardware archives and research in the primary checkout.
