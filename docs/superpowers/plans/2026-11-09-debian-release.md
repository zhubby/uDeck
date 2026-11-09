# uDeck Debian Release Implementation Plan

**Goal:** Release the complete uDeck desktop suite for CM4 v3.1 arm64 through GitHub Releases.

**Architecture:** One standard native Debian source package, four binary packages, system Python/Qt and a private target-built terminal plugin. GitHub Actions runs only on `release: published`, validates the tag against the source/changelog version, builds on arm64 in Debian 13 and attaches verified binary/source assets.

**Constraints:** Python 3.11–3.13; Qt 6.8; labwc >= 0.9 from the base image/Raspberry Pi source. No automatic login/default-terminal changes, system upgrades, firmware updates or physical acceptance claims. Old XFCE image receives backup/migration guidance.

**Package naming:** Per the user's clarification, `udeck` installs the whole suite; `udeck-shell` owns the desktop payload and migrates files from old `udeck` versions with Debian Breaks/Replaces.

## Tasks

- [x] Add behavioral tests for compatibility detection, missing dependencies, unsupported systems and release version checks.
- [x] Add stdlib-only preflight and installed-system doctor details.
- [x] Replace ad hoc package assembly with debhelper multi-binary packaging and synchronize terminal version.
- [x] Add a single build/release assembly entrypoint and Release-only GitHub workflow.
- [x] Validate native plugin, complete packages, source checksums and install/upgrade/remove/reinstall behavior.
- [x] Document exact system dependencies, installation, release procedure and remaining raw-image/physical verification.

Validation: 1097 native arm64 tests passed; four-package installation, legacy ownership migration, remove/reinstall, installed PTY, 315 matching source/resource files and preserved login/default-terminal fixtures passed. See `docs/udeck/debian-release-2026-11-09.md`. The original SD image, physical device and a published GitHub Release run remain separately unverified.
