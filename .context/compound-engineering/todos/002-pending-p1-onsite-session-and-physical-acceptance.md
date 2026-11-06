---
status: pending
priority: p1
issue_id: "002"
tags: [udeck, hardware, acceptance, labwc]
dependencies: ["001"]
---

# Full-session and physical acceptance

## Problem Statement

The desktop is implemented and installed. Fullscreen display is verified in the existing session, and the user-authorized next-login defaults now select uDeck. The user accepted basic ABXY and L/R interactions on version 0.1.2; advanced physical interactions, an independent login and cold boot remain pending. Do not equate automated software checks with a usable complete device.

## Findings

- The original labwc 0.9.2 session reports maximized state but sends zero-sized xdg configure. A direct owned Qt self-maximize request reproduces this independently of uDeck's foreign-toplevel client.
- A minimal nested/headless compositor also exits 139 without uDeck rules, so it does not substitute for a real login test.
- Version 0.1.1 remains fullscreen after Home, Switcher and QuickSettings. Owned native Wayland and Xwayland windows were confirmed visibly above the shell, closed, and followed by a return to fullscreen Home.
- LightDM's effective default and automatic-login session are now `udeck`, with the original configuration backed up. The current session has not been restarted; original desktop processes remain underneath the fullscreen shell until the next login.
- Real physical direction/ABXY and L/R press/release events were collected on 2026-11-06. The user confirmed the repaired ABXY menu navigation and L/R pointer actions work. Long holds, broader shell action flows, IME/trackball mixing, real radio connections, audio playback, screen lock/blank, logout/reboot/shutdown and original-desktop return still require acceptance.

## Proposed Solutions

Follow `docs/udeck/boot-2026-11-06.md` and the remaining checklist in `docs/udeck/acceptance-2026-11-06.md` with the user physically present. Start with non-disruptive calibration, then save all work and validate the configured default session with a recovery path. Investigate actual maximized geometry without changing the existing desktop configuration or replacing the compositor without approval.

## Recommended Action

Wait for an onsite test window and explicit readiness before session/radio/power actions. Preserve the current desktop and the only SSH network route.

## Acceptance Criteria

- [x] Capture actual physical directions/ABXY/L/R press and matching release events, and save the mixed keyboard/gamepad mapping.
- [x] Obtain user confirmation of ABXY menu navigation and L/R activation/context menus on the repaired device.
- [ ] Verify direction repeats, release-on-blur and broader focus restoration onsite.
- [ ] Verify Chinese input and trackball interaction in the actual graphical session.
- [ ] Verify independent login, normal-window maximized pixel geometry, fullscreen/modal behavior and return to the original desktop.
- [ ] Verify real Wi-Fi and Bluetooth pairing/connection/reconnection separately; audio/device function requires its own test.
- [ ] Verify volume/output/brightness, lock/unlock, screen off/on and saved-work logout/reboot/shutdown onsite.
- [ ] Record full-session/cold-start performance and update the acceptance document without overstating evidence.

## Work Log

- 2026-11-06: Created from the software-delivery handoff. All physical and disruptive acceptance remains pending; no such action was performed automatically.
- 2026-11-06: Per user request, installed 0.1.1, verified genuine fullscreen with output screenshots and foreign-toplevel state, and explicitly configured automatic login with a verified backup. Both native Wayland and Xwayland owned-window visibility checks passed. No logout, display-manager restart or reboot was performed; independent-session and physical acceptance remain pending.
- 2026-11-06: The user pressed ten prompted physical keys. Captured keyboard directions 103/108/105/106, joystick ABXY 289/290/288/291 and mouse L/R 272/273. Traced failures to empty routing, calibration ignoring native keyboard directions and incomplete pointer activation/context menus; see `docs/udeck/input-2026-11-06.md`. Raw hardware events do not establish completion of the remaining functional checklist.
- 2026-11-06: After deployment of 0.1.2, the user replied that ABXY and L/R all work normally. Recorded acceptance of the prompted quick-settings/submenu/back/context-menu sequence and pointer activation/context menus. Independent-session, cold-start and other remaining hardware checks are still pending.
