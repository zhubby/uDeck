# uDeck native contract patch

The vendored tree is already patched. The patch applies with `patch -p1` to the
upstream commit recorded in `../UPSTREAM.json`; do not apply it again here.

`0001-udeck-native-contract.patch` exposes bounded history, per-session environment,
literal search and explicit close; preserves exact program/cwd/argv without
expansion; reports PTY startup errors and abnormal exits; closes owned foreground
and background process groups; and adds cell-based keyboard selection/search and
frozen-text bracketed paste. It also forwards input-method cursor/font queries
and updates candidate positioning when terminal output moves the cursor. IME
cursor/anchor offsets use UTF-16 positions, including wide and combining text.
Changes are GPL-2.0-or-later. Existing per-file
copyright and license notices remain in place.

Build with the target's Qt 6.8 and `tools/build-terminal-plugin`. Run
`UDECK_REQUIRE_NATIVE=1 python3 -m pytest -q tests/test_terminal_native.py` after
building. A successful QML load alone does not validate a real PTY or device IME.
