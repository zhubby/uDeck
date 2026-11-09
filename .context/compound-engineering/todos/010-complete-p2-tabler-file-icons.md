---
status: complete
priority: p2
issue_id: "010"
tags: [files, icons, assets, handheld]
dependencies: ["009"]
---

## Problem Statement

The user requests Tabler icons covering as many common file types as practical in the icon-first Files workspace.

## Findings

Current icons distinguish only broad media/book/archive/text categories and otherwise depend on the desktop icon theme. The official @tabler/icons 3.51.0 package supplies suitable MIT-licensed outline SVGs, verified against npm's SHA-512 integrity metadata.

## Proposed Solutions

Bundle a focused SVG selection with original license and provenance. Classify common extensions, compound archives, exact configuration names and MIME fallbacks independently of existing preview/open behavior. Render the icons on the existing muted category-colored tiles with no network dependency.

## Recommended Action

Implement the approved icon enrichment, verify classification and offline rendering, inspect a contact sheet and the existing Files theme/language matrix, and check packaged resources. The user subsequently authorized scoped commit and push to main; device deployment remains separate.

## Acceptance Criteria

- [x] Distinct icons cover common office, media, code/data/config, archive, font/package, disk/game and design/model types, with a neutral unknown-file fallback.
- [x] Directory names, uppercase suffixes, compound suffixes and MIME-only cases select the intended visual category.
- [x] Bundled Tabler SVG geometry and the original MIT license are retained, with pinned version, source, archive/per-file hashes and documented terminal-newline normalization.
- [x] All selected icons render offline at small and high-density sizes without changing existing file operations or previews.
- [x] Files themes/languages, package assets and relevant tests pass; updated screenshots and mapping documentation are provided.

## Work Log

- 2026-11-09: Confirmed official @tabler/icons 3.51.0 via npm, verified archive SHA-512/SHA-1 and recorded SHA-256. GitHub raw access timed out; the same-version original LICENSE is present in the verified official package.
- 2026-11-09: Bundled 65 icons and classified 667 distinct suffixes, 55 special filenames and 100 exact MIME fallbacks. Existing file operation, preview and opening semantics remain unchanged.
- 2026-11-09: macOS and offline Linux arm64 focused suites each passed 276 tests. Linux initially lacked the already-declared qt6-svg-plugins runtime dependency; unpacking the matching Debian 6.8.2-3 plugin into the test container enabled the complete offline renderer checks.
- 2026-11-09: Inspected the full gallery and eight Files theme/language/size cases. All 65 icons rendered at 48/80/144 px without the old drawing fallback. Scoped Ruff and whitespace checks passed.
- 2026-11-09: Wheel and Debian builds passed with 305/237 byte-matched module/resource files respectively. Extracted-package QML and all-icon probes passed. Mapping, version, license, hashes and validation are documented in docs/udeck/file-icons-2026-11-09.md and the resource README. No installation, device deployment, commit or push.
