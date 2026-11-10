# uDeck duck badge

## Approved logo

The user approved the v6 drawing on 2026-11-10, then requested theme-aware colors in the running interface. The gray/white SVG remains the canonical standalone and installation artwork.

- [Canonical SVG](../../../src/udeck/assets/branding/udeck.svg)
- [Transparent PNG, 1024 × 1024](udeck-logo.png)
- [Installation icon](../../../packaging/udeck.svg)

`BrandLogo.qml` uses the identical v6 SVG geometry in the shell header, startup loading screen, native app headers and terminal header. It binds the SVG's two color roles to the shared palette: Classic uses the warm accent with the current surface background, and Dark uses the light text color with the current surface background. The SVG data URL updates immediately when the theme changes, without recreating windows or app sessions. When changing the artwork, keep the canonical SVG and this vector template in sync.

The standalone SVG and desktop installation icon retain the original gray/white colors. The wheel includes the QML component and asset, and the Debian package installs both the runtime asset and scalable desktop icon.

The numbered files below retain the design iterations.

See [integration verification](verification.md) for the rendering and package checks.

## v6 — goggles turned right

The goggles move slightly to the right, with a narrower far lens, a longer side strap and an adjusted bridge to suggest a rightward turn. The head, neck, bill and badge retain the v5 drawing.

- `udeck-duck-v6.svg`: editable vector master.
- `udeck-duck-v6.png`: transparent 1024 × 1024 PNG.
- `udeck-duck-v6-preview.png`: 640 × 640 preview.
- `provenance-v6.json`: output checksums and validation.

## v5 — lower crown and wider neck

The head has a lower, wider crown and fuller cheeks, with a smoother connection to the bill. The neck and white throat are wider again, with less indentation at either side. The circular badge, colors and round goggles retain the previous design.

- `udeck-duck-v5.svg`: editable vector master.
- `udeck-duck-v5.png`: transparent 1024 × 1024 PNG.
- `udeck-duck-v5-preview.png`: 640 × 640 preview.
- `provenance-v5.json`: output checksums and validation.

## v4 — fuller neck

The neck outline and white throat are wider, with a fuller transition into the chest. The goggles, bill, highlights and circular badge retain the v3 drawing.

- `udeck-duck-v4.svg`: editable vector master.
- `udeck-duck-v4.png`: transparent 1024 × 1024 PNG.
- `udeck-duck-v4-preview.png`: 640 × 640 preview.
- `provenance-v4.json`: output checksums and validation.

## v3 — proportion adjustment

The revised portrait uses a smaller head and goggles, a shorter bill with more space from the circular edge, and a broader lower silhouette with curved chest contours. The badge geometry and colors are unchanged.

- `udeck-duck-v3.svg`: editable vector master.
- `udeck-duck-v3.png`: transparent 1024 × 1024 PNG.
- `udeck-duck-v3-preview.png`: 640 × 640 preview.
- `provenance-v3.json`: output checksums and validation.

## v2 — redesigned duck portrait

The new draft redraws the head, bill and neck in three-quarter profile. It keeps the circular badge, round goggles, lens reflections and warm gray / white palette, with no lettering. The longer projecting bill and curved neck establish the duck silhouette.

- `udeck-duck-v2.svg`: editable vector master.
- `udeck-duck-v2.png`: transparent 1024 × 1024 PNG.
- `udeck-duck-v2-preview.png`: 640 × 640 preview.
- `provenance-v2.json`: output checksums and validation.

## v1

Design brief: retain the supplied reference's circular badge, warm gray / white palette, round goggles, strap, head highlight and portrait composition. Replace the penguin with a duck with a broad rounded bill. Remove every word around the circumference. The canvas outside the badge is transparent.

Files:

- `udeck-duck-v1.svg`: editable vector master, 280 × 280 viewBox.
- `udeck-duck-v1.png`: 1024 × 1024 PNG with an alpha channel.
- `udeck-duck-v1-preview.png`: 640 × 640 preview on a light background.
- `provenance.json`: source attachment checksum, rendering method and output checksums.

Created by directly drawing SVG paths and rasterizing with Sharp. No image generation model or API was used.

The reference was the ClockworkPi penguin badge supplied in the user's image attachment `codex-clipboard-9df3a6fc-f3eb-416e-9668-eac4f3194ffc.png`.
