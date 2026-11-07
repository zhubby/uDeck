# Input prompts

The **Kenney Input Prompts** PNGs in this directory come from the
**Keyboard & Mouse** and **Nintendo Gamecube** sets. The downloaded archive is
`kenney_input-prompts_1.5.zip`; its original license identifies the content as
`Input Prompts (1.5A)`, licensed under **CC0-1.0**.

Source: <https://kenney.nl/assets/input-prompts>

`License.txt` is the unmodified upstream notice. `manifest.json` records the
archive hash, original archive paths and hashes of all 27 selected PNGs.
25 images are unmodified `Double` exports (128×128 with transparent padding).
X and Y use the circular white B silhouette with its letter cutout filled,
then the original X/Y letter cutout applied at its original position and size.
These two adaptations keep the 128×128 canvas; their upstream inputs and
transformations are recorded separately in the manifest.
They ship in the base package and wheel, with no network requests or SVG
runtime dependencies.

Shared QML components are `InputIcon.qml`, `InputPrompt.qml` and `InputHints.qml`.
`InputIcon` decodes PNGs at their physical display size, including screen pixel
ratio, so the software renderer receives smoothly resampled small images.
Wide keyboard caps and the arrow cluster scale proportionally to match the
visible height of square keys. Their layout slots grow with the artwork;
the original PNGs, shapes and letter cutouts remain unchanged.
The design prototype keeps byte-identical copies; resource tests check parity.
See `docs/design/input-prompts.md` for mapping, sizing and accessibility rules.
