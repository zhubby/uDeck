# Kenney Interface Sounds

Source: <https://kenney.nl/assets/interface-sounds>.

The official `kenney_interface-sounds.zip` contains Interface Sounds 1.0 under
CC0-1.0. `License.txt` is retained byte-for-byte. `manifest.json` records the
archive SHA-256, original OGG hashes, converted WAV hashes, duration and gain.

Eight selected sounds are converted offline to mono 48 kHz, 16-bit PCM WAV for
Qt SoundEffect. Only a constant gain is applied: no trimming, time stretching or
pitch changes. Peak levels range from -18 to -13 dBFS, including headroom for
Vorbis reconstruction peaks. No decoder executable or network access is needed
at runtime. The original archive is not bundled.

| Event | Source | Peak dBFS |
| --- | --- | ---: |
| Focus movement | `Audio/tick_001.ogg` | -18 |
| Activate | `Audio/select_001.ogg` | -14 |
| Open or change page | `Audio/open_001.ogg` | -16 |
| Back or cancel | `Audio/back_001.ogg` | -15 |
| Enable | `Audio/toggle_001.ogg` | -16 |
| Disable | `Audio/toggle_002.ogg` | -16 |
| Completed operation | `Audio/confirmation_003.ogg` | -16 |
| Failed operation | `Audio/error_008.ogg` | -13 |

Interaction rules and acceptance boundaries are documented in
`docs/design/interface-sounds.md` at the repository root.
