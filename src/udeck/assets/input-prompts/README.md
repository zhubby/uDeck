# Input prompts

The original **Kenney Input Prompts** PNGs in this directory come from the
**Keyboard & Mouse** and **Nintendo Gamecube** sets. The downloaded archive is
`kenney_input-prompts_1.5.zip`; its original license identifies the content as
`Input Prompts (1.5A)`, licensed under **CC0-1.0**.

Source: <https://kenney.nl/assets/input-prompts>

`License.txt` is the unmodified upstream notice. `manifest.json` records the
archive hash, original archive paths and hashes of all 27 selected PNGs. The
images are unmodified `Double` exports (128×128 with transparent padding).
They ship in the base package and wheel, with no network requests or SVG
runtime dependencies.

Shared QML components are `InputIcon.qml`, `InputPrompt.qml` and `InputHints.qml`.
The design prototype keeps byte-identical copies; resource tests check parity.
See `docs/design/input-prompts.md` for mapping, sizing and accessibility rules.
