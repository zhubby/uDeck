# Bundled interface fonts

- English: **Saira Semi Condensed**, Regular (400), Medium (500), SemiBold
  (600), and Bold (700). Qt reports its internal family as `Saira SemiCondensed`.
- Simplified Chinese: **LXGW WenKai Screen / 霞鹜文楷屏幕阅读版**, version
  **1.530**, internal family `LXGW WenKai Screen`.

These are unmodified upstream TTF files under the SIL Open Font License 1.1.
The full copyright and license notices are in `Saira-OFL.txt` and
`LXGW-OFL.txt`. `manifest.json` records immutable source revisions/release URLs,
file sizes and SHA-256 hashes. Assets and notices ship in the base uDeck
package and wheel; no system-wide font installation or network fetch is needed.

`qml/InterfaceFonts.qml` loads the resources and selects the interface family
from the saved language. Font bindings update existing windows in place.
Web content, document typography and Terminal fixed-width cells retain their
own fonts.
