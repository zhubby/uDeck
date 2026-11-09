---
status: complete
priority: p1
issue_id: "012"
tags: [debian, release, ci]
dependencies: []
---

# Debian desktop suite and Release-only automation

## Problem Statement

Existing ad hoc Debian builders omit runtime components and have no GitHub release workflow.

## Findings

- Main is now 0.2.1 with multi-adapter hotspots; retain dnsmasq-base and nftables.
- Target is official CM4 v3.1 / arm64 / Trixie, Qt 6.8 and labwc >= 0.9.
- Official v0.1b XFCE is a migration target, not an in-place runtime target.
- Base image must retain ClockworkPi drivers, firmware, original desktop and user data.

## Proposed Solutions

Use one native Debian source package producing the udeck full-suite metapackage plus udeck-shell, udeck-terminal and udeck-apps. Build the private terminal plugin against system Qt. Publish binaries, matching source, dependency documentation and hashes only for published GitHub Releases.

## Recommended Action

Implement the approved plan sequentially in the isolated release worktree.

## Acceptance Criteria

- [x] Standard multi-binary packaging, synchronized versions and correct runtime dependencies.
- [x] Standalone compatibility check and expanded installed-system diagnostics.
- [x] Release-only workflow with exact tag/version validation and arm64 Debian builds.
- [x] Binary/source bundle, checksums and install/upgrade/migration documentation.
- [x] Automated tests, workflow lint, native build and package lifecycle validation.
- [x] Record raw-image and physical acceptance limits accurately.

## Work Log

- 2026-11-09: Approved plan loaded; isolated from unrelated main-checkout reference files. Linux CLI/login/file/input baseline: 24 passed. Original macOS virtualenv has a broken Homebrew interpreter; creating a task-local environment.
- 2026-11-09: User named the full-suite entrypoint udeck; rename the shell payload package udeck-shell and add Breaks/Replaces for old udeck package ownership. Set unified release version to 0.2.2.
- 2026-11-09: Native Debian arm64 build completed with 1097 tests passed and no native skips. Corrected QML plugin naming under dh_python3 and added explicit wpasupplicant runtime dependency. Clean signed-APT container lifecycle passed, including installed shell/five apps/terminal PTY, legacy ownership upgrade, reinstall/remove/reinstall, 315 source/resource byte comparisons and original login/default-terminal fixtures. Ruff, Actionlint, ShellCheck and whitespace checks passed. Detailed evidence and remaining original-image/physical/hosted-Release boundaries are in docs/udeck/debian-release-2026-11-09.md.
