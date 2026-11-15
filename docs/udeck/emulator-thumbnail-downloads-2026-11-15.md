# Emulator thumbnail downloads on uConsole — 2026-11-15

uDeck **0.2.22**, application revision
`6b68a106a11f99312d26681114f39c88f1b3f74e`, is installed on the uConsole.
The fix is merged into and pushed to `main`.

## Diagnosis and behavior

The service requires canonical image filenames. The original `F1 2002.png`
request returned 404; `F1 2002 (USA, Europe).png` returned a valid 118,075-byte
image. Most library entries used Chinese ZIP names and `crc32: "DETECT"`;
manual scanning does not identify them against a ROM database. Initially the
normal thumbnail directory contained no images.

Real HTTPS requests also encountered intermittent transfer timeouts. Version
0.2.22 allows 30 seconds without data and retries transient network failures and
HTTP 500/502/503/504 once. Timeouts after HTTP headers also retry, discarding the
partial body. Aborted replies are checked before reading.

The downloader additionally tries the official name before a trailing bracket
qualifier such as `[CRC32-copy-id]`, keeping the qualifier in the local image
filename. This applies to every platform. Existing images retain precedence and
are never overwritten. Results explain unmatched names, failures and retries;
an incomplete batch is no longer labeled “Download complete”.

## Authorized filename correction

The one-time correction uses official Libretro No-Intro GBA metadata dated
2026.11.14, containing 3,509 records, from
[libretro-database](https://raw.githubusercontent.com/libretro/libretro-database/master/metadat/no-intro/Nintendo%20-%20Game%20Boy%20Advance.dat).
The retained snapshot SHA-256 is
`6b54ff4f66f3ffdca0dd0dd4fc2bb855e016faf2dd58a5017db20c7b30171b06`.
This is operational library maintenance; manual scanning still uses `DETECT`
when no database recognition is available.

- **647 ZIP files** were renamed; compressed bytes and archive members are unchanged.
- **158** match both database CRC and member SHA-1. **489** identify the base
  game from its header code, including revisions sharing one base name. These
  variants retain a CRC/copy suffix; their exact translation or patch version
  is not inferred from the base game code.
- **79 GBA entries** with unresolved/ambiguous or explicitly modified identities
  retain their filenames. The original fixtures and PSP entry retain their paths.
- Existing native save associations exclude a game from renaming. Persistent
  IDs, Chinese labels, list order, core choices and unknown playlist fields are
  checked across publication. The state file is unchanged by the transaction.

The idle Emulator was closed during correction. Same-filesystem hard links kept
original paths available until new paths, lists and ID aliases were prepared.
SHA-256 checks preceded removal of original aliases. The committed journal and
recovery helper remain in
`~/.local/state/udeck/library-repairs/thumbnail-names-20261115/`.

The first preflight stopped on a non-ASCII header and rolled the package back
before changing any ROM path. Header comparison was corrected while retaining
the required CRC/SHA-1 verification. Six isolated cases pass on the development
host and device: resume, rollback, disk failure, destination conflict, saved-game
exclusion and a non-ASCII header. The second deployment and all corrections pass.

## Verification

- Final source runs: **47** thumbnail/release/translation tests and **19**
  thumbnail/Qt tests, with overlapping thumbnail cases. Ruff and whitespace
  checks pass. A preceding affected regression run passed 95 cases.
- The package and source archive contain **507 application files** matching the
  clean revision. Installed files match the same manifest; `dpkg --verify udeck`
  is clean.
- Installed source: **37** thumbnail/playlist tests and **4** Qt probes pass,
  English/Chinese × Classic/Dark, covering GB, GBC, GBA, NES and PSP.
- The normal installed Wayland application, using compositor key events and its
  actual menu, retrieves **27 images for 9 games** from Libretro HTTPS: CT Special
  Forces 1/2/3, F-Zero, F1 2002, two GT3 entries, Konami Wai Wai Racing and RPG
  Tsukuru. Each receives boxart, a snapshot and a title image. CT 2 succeeds after
  two automatic retries.
- Repeating F1 queues **0** downloads and retains all 27 hashes. The library has
  **730 entries in 4 playlists**, including **727 GBA entries**. All **25**
  pre-existing native save files retain their hashes; favorites, recent entries,
  records and per-game core choices are preserved. Downloads do not change
  playlist bytes. Normal-session QML errors are empty.
- The upgrade preserves **39** protected configuration/native-save files,
  **7** other desktop processes, cloud configuration and the active/enabled save
  service. These checks establish automated device behavior; they do not establish
  a new cloud-transfer or human physical-input result.

After receipts and screenshots were copied locally, deployment staging was
removed, releasing **60,563,456 bytes**. Free space is **24,959,414,272 bytes**
(24.96 GB). No uDeck build/backup paths remain under `/var/tmp` or `/var/backups`.
Installed bytes, the 39 protected files, desktop processes and save service pass
again after cleanup. The live filename recovery journal and helper are retained.

The arm64 package SHA-256 is
`9368ea33a680129d29d9b8e19d9e67b76d1774130e7ef46371fd355c553cce2f`.

Local receipts, metadata, repair scripts and screenshots are retained in the main
checkout's ignored `artifacts/thumbnail-scraping-0.2.22-20261115/` directory.
Device receipts are under `device-evidence/`, including
`filename-repair-verification.json`, `installation-verification.json`,
`installed-tests-verification.json` and `normal-session-verification.json`.
Normal application screenshots are `normal-session/gba-artwork-final.png`,
`normal-session/f1-artwork-details.png` and `normal-session/gba-library-final.png`.
