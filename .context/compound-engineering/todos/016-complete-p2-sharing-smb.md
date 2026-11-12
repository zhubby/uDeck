---
status: complete
priority: p2
issue_id: "016"
tags: [udeck, settings, sharing, samba, device]
dependencies: []
---

# System Sharing settings and SMB

## Problem Statement

Move Web file access into system Settings / quick settings and add independently configured, passwordless read/write SMB sharing using standard Samba.

## Findings

- Existing Web settings and session service must remain compatible.
- The desktop and other worktrees must be preserved during testing and delivery.
- SMB requires a restricted system D-Bus / Polkit boundary, selected NetworkManager addresses, transactional configuration and connection revocation.

## Proposed Solutions

Follow the user-approved plan recorded in docs/superpowers/plans/2026-11-12-sharing-smb.md. Work sequentially in an isolated managed worktree.

## Recommended Action

Implement and test independent protocol controls, Samba service integration and Debian lifecycle; review, test on uConsole with a remote SMB client, then merge and push main.

## Acceptance Criteria

- [x] Settings and Y Sharing entries; single-line menus retain focus and actual status.
- [x] Web configuration and legacy calls preserved; Files entry removed.
- [x] Separate SMB settings, secure D-Bus/Polkit, Samba guest access using caller Unix permissions.
- [x] Address restrictions, expiry/session/root/network revocation and rollback verified.
- [x] Debian installation preserves existing Samba configuration and prevents new standard services from starting.
- [x] Language/theme/size matrix and real remote SMB CRUD verified without disrupting the desktop.
- [x] Code review, regression and binary package validation completed.
- [x] Scoped commits delivered to main; live remote ref verified.

## Work Log

### 2026-11-12

- Created managed worktree sharing-smb and branch codex/sharing-smb from clean main 5bd1c86.
- Reused the approved plan; no additional permission gates or parallel agents.

- Sequential review fixed activation/save rollback, canonical path and bind-mount identity, D-Bus marshalling, guarded dependency startup, stop-state reporting and queued-operation feedback.
- Final native ARM64 build: 1519 passed, no skipped tests, 783.30 seconds; Ruff and diff checks passed.
- Final 0.2.4 installed on uConsole; remote guest SMB CRUD, 8 UI cases / 64 captures and original process/config preservation verified.
- Test sharing, authorization rule, network profile, forwarding and runtime overrides removed; original Web state and default-off SMB restored.
- Full clean Debian lifecycle passed, including installer recommendations, legacy migration, upgrade, reconfiguration, removal and reinstall; 423 installed source files compared. Implementation and test-fixture commits have been delivered to main.

- Fast-forwarded actual main and pushed implementation commit fe3965c2d23cd744a0d38d3a0326b645a1645266; local main, tracking origin/main and live remote matched.
- Post-merge focused regression: 51 passed; Ruff and diff checks passed. Validation records and packages remain in the managed worktree.
