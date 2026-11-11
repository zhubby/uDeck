---
status: ready
priority: p2
issue_id: "015"
tags: [udeck, python, uv, release]
dependencies: []
---

# Reproducible Python development with uv

## Problem Statement

Development dependencies have no lockfile, and the main checkout's virtual environment points to a removed Homebrew Python. Implement the user-approved uv plan while preserving unrelated work and the Debian/APT runtime.

## Findings

- The package uses setuptools, Python >=3.11,<3.14, PySide6 >=6.8,<6.9 and the existing `dev` extra.
- Release Actions run only on published releases; Debian's builder compiles the terminal plugin and runs native tests with system Python/Qt.
- The source release builder explicitly enumerates root files, so the uv lock and interpreter pin must be included there.

## Proposed Solutions

Use uv 0.13.7 and managed Python 3.13.18 for local development and Release host checks. Keep setuptools, dependency extras and Debian build/install behavior. Generate the first lock using existing principal package versions.

## Recommended Action

Implement sequentially on `codex/udeck-uv` from `3087b837284c567ac4d1bd4dce38d74ee631ad98`. Create a fresh isolated environment; retain the main checkout's existing environment and business changes. Commit the scoped implementation without publishing a Release.

## Acceptance Criteria

- [x] Baseline checks and existing dependency versions are recorded.
- [x] Python pin, uv version requirement and lockfile support reproducible development.
- [x] Existing Release workflow checks lock consistency, sync and Ruff before Debian builds.
- [x] Development documentation covers setup, commands, updates and environment recovery.
- [x] Source archives include the Python pin and lockfile.
- [x] Fresh/repeated sync and stale-lock detection behave as documented.
- [x] Ruff, QML smoke, workflow validation, wheel and focused release/CLI checks are verified.
- [ ] Full Python tests and Debian arm64 build/install lifecycle pass without unresolved failures.
- [x] Final diff is reviewed and a scoped commit is created.

## Work Log

### 2026-11-11

- User approved the implementation plan and selected development plus existing Release checks, without new daily CI.
- Created a managed worktree and branch; main checkout and other worktrees remain separate.
- Confirmed the main `.venv` interpreter is missing; uv-managed Python 3.13.18 is installed.
- Baseline packages: PySide6 6.8.3, pytest 9.2.0, Ruff 0.17.3, build 1.6.1 and dbus-next 0.2.3.
- Generated an official-PyPI universal lock (16 packages), preserved the existing extras/backend/runtime range and added the pinned uv requirement.
- Fresh and repeated macOS sync succeeded; stale-lock mutation was rejected without changing the lock. Ruff, actionlint, wheel build and 26 focused CLI/release/safety tests passed.
- macOS baseline: 1,310 passed, 5 skipped, 2 failures (PDF probe timeout and video sink); both failures passed targeted recheck. The full uv-driven rerun recorded 1,309 passed, 5 skipped and 3 failures (two Files completion assertions and QML shutdown warnings); the same three tests then passed a focused recheck.
- Debian arm64 release builds compiled the native plugin but twice crashed at `tests/test_reader_layout.py:61` during fixture event processing. Reader alone (4 tests), Files + Reader (42 tests), and the reduced Qt module prefix (430 tests) pass. Runtime sources and Debian rules/control remain identical to the base commit.
- Additional Linux uv check confirmed evdev needs Python headers when using system Python; documented the prerequisite. Package downloads encountered timeouts, with detailed logs retained under `artifacts/uv/`.
- Exercised actual release source staging, built and extracted the Debian source archive, and byte-compared uv.lock, .python-version and pyproject.toml. Source-only evidence is in dist/uv-source-check/; this does not establish binary installation acceptance.
- Resolved setup-uv's v7 annotated tag to its actual commit and verified all configured action inputs. Final lock/sync checks, Ruff, Actionlint and diff whitespace checks pass.
- Added docs/udeck/uv-development-2026-11-11.md with reproducible commands, exact results and remaining gates. Detailed logs stay under ignored artifacts/uv/.
- Unmodified baseline Debian build passed all 1,317 tests and built packages. Repeated equivalent QML smoke on the original source reproduced the null context shutdown warning on its second run, confirming that warning predates this migration.
- Final migrated Debian build recorded 1,316 passed and 1 failed (QML shutdown warning). It did not reproduce the Reader crash, whose cause remains unresolved. No migrated binary release was produced, so the install/remove/reinstall probe remains pending.
- Downloaded uv-managed Linux Python 3.13.18 using the host and ran it in the native arm64 container; interpreter discovery, bundled headers and offline lock consistency all passed. Host-side prefetch of the missing Linux wheels also timed out; full Linux uv sync remains unverified.
- Reviewed and prepared the scoped branch commit. Full-suite stability and Debian binary lifecycle acceptance remain open; release test requirements are unchanged.
