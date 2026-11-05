---
status: complete
priority: p1
issue_id: "001"
tags: [udeck, implementation, device]
dependencies: []
---

# uDeck v1 delivery

## Problem Statement

Implement the approved button-first uConsole desktop without replacing the existing desktop.

## Findings

Software implementation and optional arm64 installation are verified with 67 local/device tests, actual owned Wayland/Xwayland windows, installed file operations and a 60-second performance sample. Full-session and physical acceptance remain explicitly outstanding in todo 002 and the Chinese acceptance record.

## Proposed Solutions

Fix reproducible failures with regression tests; verify real read-only services and isolated test windows; build and install an optional arm64 package; document exact evidence and pending onsite checks.

## Recommended Action

Keep the existing unborn repository and original login configuration intact. Continue onsite acceptance only with the user's participation, saved work and recovery access; do not perform disruptive actions remotely by default.

## Acceptance Criteria

- [x] Automated navigation, file safety, input and QML regressions pass.
- [x] Actual window enumeration/activation/close, session D-Bus control and read-only system state work on CM4; maximization geometry remains unpassed.
- [x] Optional Debian package installs without replacing desktop configuration.
- [x] Startup, RSS and idle CPU measurements are recorded.
- [x] Chinese usage, architecture, rollback and physical acceptance documentation are complete.
- [x] Human physical input, radio connection and disruptive session tests are explicitly pending rather than claimed passed.

## Work Log

- 2026-11-06: Resumed implementation from the previous context; collected 33 passing local/device tests and the evdev diagnostic failure. No physical key or disruptive operation is authorized for unattended acceptance.
- 2026-11-06: Fixed input lifecycle, file safety, service prompt cancellation and error reporting; 67 tests pass locally and on CM4, Ruff and QML smoke are clean, wheel and arm64 Debian package build.
- 2026-11-06: Installed final package; all 12 Python/QML files match the source and original labwc/LightDM hashes are unchanged. Verified Chinese file operations, private copy permissions, atomic move and actual home-filesystem Trash data/metadata. `/tmp` tmpfs refuses Trash safely and the UI now exposes that reason.
- 2026-11-06: Final installed 60.060-second sample: process launch to first-frame report 2.173 s, internal first frame 1.226 s, RSS 194.36 MiB (peak 194.41), idle CPU 0.716% of one core, no warnings. Package and evidence copied into local ignored `dist/` and `artifacts/`.
- 2026-11-06: Original compositor returns zero-sized maximized configure even to a direct Qt self-maximize request. No compositor/config workaround applied; independent login, maximization, real buttons, radios, IME and power acceptance are tracked separately, not declared complete.
