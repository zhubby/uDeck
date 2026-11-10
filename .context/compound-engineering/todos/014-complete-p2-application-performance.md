---
status: complete
priority: p2
issue_id: "014"
tags: [udeck, performance, qt, cm4]
dependencies: []
---

## Problem Statement

CM4 users report slow first application launches and repeated activation. Implement the approved architecture optimization plan without changing application behavior or introducing a full C++ rewrite.

## Findings

Repeated launches initialize GUI/WebEngine before forwarding to an existing process. Hidden content surfaces load eagerly. Every application state update serializes the full library. Periodic media saves synchronously rewrite and fsync the library index on the GUI thread.

## Proposed Solutions

Keep QML and native engines; add lightweight IPC forwarding, deferred surfaces, a Qt list model with compact state, and serialized background state persistence with a separate index file. Measure before and after on CM4.

## Recommended Action

Implement sequentially in the isolated codex/udeck-app-performance worktree. Preserve desktop IDs, D-Bus methods, terminal launch arguments, focus/input ownership, existing data and atomic-save semantics.

## Acceptance Criteria

- [x] Capture CM4 source/runtime/resource and launch baseline.
- [x] Add startup-stage and window-activation diagnostics and repeatable sampling.
- [x] Existing instances receive direct asynchronous shell requests; external entrypoints forward before GUI imports.
- [x] Content surfaces are created on first use and retained for document/player/browser lifecycle.
- [x] Large collections use a Qt list model and independent selection/playback state.
- [x] Index and mutable state persist through one background writer; legacy data, failures and exit flushing are covered.
- [x] Regression tests, real QML/engine flows, independent D-Bus client and performance comparisons pass.
- [x] Record exact CM4 results and any pending physical/IME acceptance.

## Work Log

### 2026-11-10

- User approved the full plan; main checkout was clean at 1f26587a9449ccdc0714ddafb9605193c5143677.
- Created managed isolated worktree and branch codex/udeck-app-performance.
- Implemented lightweight application/terminal forwarding, asynchronous shell D-Bus calls, retained lazy content pages, virtualized cards and serialized background index/state persistence.
- Reproduced and fixed first browser navigation, lazy PDF pan restoration, duplicate queue selection, writer failure recovery and single-instance startup races.
- Linux ARM64: 84 modules / 1,231 tests passed with native terminal support; combined release-style execution also passed all 1,231 tests in 362.6 seconds.
- Completed Linux before/after measurements and 100/1,000/10,000-resource selection comparisons. Reader English/Chinese screenshots are byte-identical.
- CM4 SSH recovered. Testing private instances on the existing labwc/OpenGL session, with unique test window titles and a private activation bridge; user processes and application data are preserved.
- Built the wheel and arm64 Debian package. Unpacked package entrypoints forward/diagnose with an unavailable Qt platform, and runtime/model/QML files match source.
- Login information is kept out of repository files and evidence.

- Completed CM4 before/after: 6 apps x 3 processes x 20 repeated launches, plus independent Open calls for 5 apps. Both versions exited 0; all 300 optimized direct-activation samples were observed. Maximum per-run direct activation P95: 206.868 ms.
- CM4 Reader first frame 3.307 s to 2.917 s; PSS 187.4 MiB to 114.9 MiB. Other first launches did not universally improve; external command activation remains 0.45-0.80 s.
- Source/font hashes match local versions plus only the documented temporary title instrumentation. Original desktop, Reader and Emulator processes remain running; no test process remains.
- Retained reports, sample coverage, CPU/I/O/swap data, source hashes, migration notes, packaging evidence and all acceptance limits in docs/udeck/application-performance-2026-11-10.md.
- Implementation and automated comparisons are complete. Physical ABXY/L/R, real Chinese IME, terminal minimized restoration, installed desktop end-to-end timing and sustained real-content performance are explicitly pending; no package was installed on CM4 and no default terminal was changed.
