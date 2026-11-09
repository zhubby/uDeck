# Files Workspace Implementation Plan

> Execute sequentially with test-first implementation. Do not create agents, commits, branches, or deploy without a separate request.

**Goal:** Deliver all approved Files improvements: navigation, search/sort/filter, richer compact rows, cancellable background transfers, batch selection, conflict choices, previews/open-with, mounted locations, trash recovery, focus/refresh fixes, and efficient QML data delivery.

**Architecture:** Keep ShellController's external snapshot and existing navigation contracts. Add a Files mixin, an incremental Qt list model, focused filesystem/preview/trash helpers, and a Files-only QML surface. Keep mutation safety in FileOperations and long transfers on a separate single-worker executor so browsing/application launches remain available.

**Tech Stack:** Existing Python 3.11+, PySide6/Qt 6.8, QML, GIO, Linux mount metadata, Freedesktop Trash specification. No new dependencies or Qt upgrade.

**Spec:** Approved feature scope in the preceding Files assessment and the user's request to implement all features.

## Global Constraints

- Preserve four top tabs, L/R page switching, A open/confirm, B back, X context, Y quick settings, and pointer isolation.
- Preserve Classic/Dark themes and English/Chinese localization.
- Keep default applications, shell sessions, system mounts, and unrelated files untouched.
- Never permanently delete user files as a trash fallback, merge folders, silently overwrite, or bypass authorization for unmounting.
- Preserve CLI/D-Bus snapshots; use a separate compact internal view snapshot and incremental model.
- Run tests with the working temporary validation interpreter; do not repair the repository virtual environment.

## Files

- Extend `src/udeck/files.py`: metadata, query/sort/filter, transfer measurement/progress, safe conflict naming.
- Add `file_locations.py`, `file_trash.py`, `file_preview.py`: mounted locations/unmount, validated trash restore, bounded previews.
- Add `file_model.py`, `file_controller.py`: incremental Qt model and Files state/actions.
- Integrate `controller.py`, `core.py`, `desktop.py`, `qml/Main.qml`; add `qml/FilesScreen.qml`.
- Update both locale catalogs and Files documentation.
- Add core, controller, model, QML, packaging/resource regression coverage.

## Tasks

- [x] Write failing metadata/sort/filter, progress/conflict, trash and mounted-location safety tests.
- [x] Implement filesystem helpers and rerun focused core/safety tests.
- [x] Write failing focus/refresh, navigation, selection, background-job and compact-model tests.
- [x] Implement Files controller/model and retain external snapshot compatibility.
- [x] Add Files QML and keyboard shortcuts without changing global controller bindings.
- [x] Add bounded previews, installed application choices, mounted locations and recovery actions to the UI.
- [x] Complete translations and document functionality and acceptance boundaries.
- [x] Run targeted and full tests, Ruff, QML rendering across themes/languages/sizes, and wheel resource inspection.
- [x] Inspect screenshots and final diff; report any preexisting failures and physical-device acceptance gaps separately.

## Validation Record

Completed November 9, 2026. Focused tests pass on macOS and Linux arm64 (165 each). Full suite: 861 passed, 3 skipped, 2 preexisting Reader test failures independently reproduced at baseline HEAD. Scoped Ruff passes; three unrelated baseline UP038 findings remain. All eight QML combinations and unpacked wheel/Debian QML probes pass. Package resources match the current source byte-for-byte. See `docs/udeck/files-workspace-2026-11-08.md` for hashes, logs, supported recovery boundaries and pending physical-device acceptance. No Git delivery, package installation or device deployment performed.

Subsequent icon-grid and Tabler improvements are recorded in the same Files documentation. The user then separately requested commit and push of the complete scoped work to main; this does not include package installation or device deployment.
