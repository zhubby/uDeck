# EPUB renderer

foliate-js: https://github.com/johnfactotum/foliate-js

Pinned commit: `78914aef4466eb960965702401634c2cb348e9b1` (2026-11-07 retrieval).
The nine JavaScript modules in `foliate/` are unmodified upstream files, MIT licensed;
see `foliate/LICENSE`. Only the EPUB loader, paginator, CFI, search and fixed-layout
dependencies are used. ZIP access is implemented by Python's standard library;
zip.js, fflate, PDF.js and other upstream format loaders are not distributed.

`reader.js` and `index.html` are uDeck integration code under GPL-2.0-or-later.
The tokenized loopback server exposes only the selected book and these modules.
Its CSP trusts a per-session nonce on the renderer module graph and blocks book
scripts, network access, objects and forms. The reading profile is separate from
the browser's persistent profile.
