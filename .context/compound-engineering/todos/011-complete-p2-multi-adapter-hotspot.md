---
status: complete
priority: p2
issue_id: "011"
tags: [wifi, hotspot, qml]
dependencies: []
---

## Problem Statement

Implement the approved per-adapter hotspot plan without disturbing other adapters or unrelated work.

## Findings

Current main already supports multiple Wi-Fi clients and per-adapter status icons. AP profiles are deliberately excluded from client configuration management.

## Proposed Solutions

Use NetworkManager AP/shared profiles and device-bound asynchronous operations; extend existing menus and radio indicators.

## Recommended Action

Implement in codex/udeck-hotspot. Preserve client profile filtering, service epochs, hardware identity and actual-state completion.

## Acceptance Criteria

- [x] Backend supports independent hotspots, shared IPv4, manual startup and guarded restoration.
- [x] Settings, quick settings, credentials and per-adapter icons work in both languages/themes.
- [x] Complete pytest, Ruff, QML smoke and package checks pass.
- [x] Document automated evidence and remaining physical acceptance separately.

## Work Log

- 2026-11-09: Approved plan loaded; isolated worktree created. Existing Wi-Fi backend/status baseline: 85 passed. Real device SSH authentication remains unavailable from the planning check.
- 2026-11-09: Software implementation complete in codex/udeck-hotspot (uDeck 0.2.1). Final pytest: 1066 passed, 3 skipped (existing native Terminal plugin prerequisites); Ruff and QML smoke passed. Hotspot QML matrix: 8 groups / 120 renders. Real libnm accepted emitted AP settings; an isolated real NetworkManager retained the password after a name-only Update2. Wheel and ARM64 Debian package built and checked. See docs/udeck/hotspot-2026-11-09.md and artifacts/hotspot/validation/.
- 2026-11-09: Fixed all three review findings. Configuration revisions ignore NM-maintained timestamp/seen-bssids while preserving real settings/VersionId checks; external takeovers invalidate failed operations and obsolete restoration records while same-AP stop retries retain restoration; hotspot totals reflect actual activated AP devices even after stop denial. Added 13 regression cases, including real-controller settings output; the related six suites pass (148 tests).
- 2026-11-09: Post-review full verification: 1079 passed, 3 existing native Terminal plugin skips (374.20 seconds); Ruff, standalone QML smoke and the 8-group/120-render hotspot matrix passed. Updated the 15 zh-CN dark screenshots and rebuilt Wheel/ARM64 Debian artifacts. Verified 97 Wheel and 60 Debian Python/QML/JSON files against current sources; new hashes and local logs are recorded in the feature document and validation summary.
- 2026-11-09: User authorized scoped commits, main merge and origin push. Deliver the Reader test fixture correction separately from the hotspot feature; preserve unrelated untracked material in the main checkout and verify live remote main after pushing. Build artifacts and detailed logs remain local.
- Physical acceptance remains pending: AP capability, phone association, DHCP/DNS, internet forwarding, LAN without uplink, concurrent APs, Wi-Fi restoration, physical hotplug and reboot. SSH authentication has not been restored; synthetic and container checks do not close these gates. Restoration ownership is process-local, as documented.
