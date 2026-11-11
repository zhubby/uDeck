# EPUB and MOBI renderer

foliate-js: https://github.com/johnfactotum/foliate-js

Pinned commit: `78914aef4466eb960965702401634c2cb348e9b1` (2026-11-07 retrieval).
The ten JavaScript modules in `foliate/` are unmodified upstream files, MIT licensed;
see `foliate/LICENSE`. The EPUB/MOBI loaders, paginator, CFI, search and fixed-layout
dependencies are used. ZIP access is implemented by Python's standard library.
The MOBI module was retrieved from the same pin on 2026-11-10. MOBI6/KF8 parsing,
PalmDOC and HUFF/CDIC decompression are provided by upstream; compressed embedded
fonts use Chromium's native `DecompressionStream('deflate')`. No conversion tools,
zip.js, fflate, PDF.js or other upstream format loaders are distributed.

`reader.js` and `index.html` are uDeck integration code under GPL-2.0-or-later.
The tokenized loopback server exposes only the selected book and these modules.
Its CSP trusts a per-session nonce on the renderer module graph and blocks book
scripts, network access, objects and forms. The reading profile is separate from
the browser's persistent profile.

MOBI records are read through bounded byte slices of the selected open descriptor.
The server validates the PDB table and MOBI headers before opening the renderer,
rejects encrypted books and changed files, and limits book size to 512 MiB,
individual records/requests to 64 MiB and declared uncompressed text to 128 MiB.
