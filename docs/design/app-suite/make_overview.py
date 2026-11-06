"""Compose six verified screenshots. Pillow is an optional review-time dependency."""

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
PANELS = (
    ("Music / Your collection", "music-en-1280-home.png"),
    ("Video / Playback", "video-en-1280-player.png"),
    ("Browser / Page navigation", "browser-en-1280-page.png"),
    ("Reader / Time for a few pages", "reader-en-1280-reading.png"),
    ("Games / Your next adventure", "games-en-1280-home.png"),
    ("Games / Pause and save", "games-en-1280-pause.png"),
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--screens", type=Path, default=ROOT.parents[2] / "artifacts/app-suite/verification")
    parser.add_argument("--output", type=Path, default=ROOT / "images/overview.webp")
    parser.add_argument("--font", type=Path)
    args = parser.parse_args()
    candidates = (
        args.font,
        Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    )
    font_path = next((x for x in candidates if x and x.is_file()), None)

    def font(size):
        return ImageFont.truetype(str(font_path), size) if font_path else ImageFont.load_default(size=size)

    canvas = Image.new("RGB", (1536, 1560), "#101315")
    draw = ImageDraw.Draw(canvas)
    draw.text((32, 26), "uDeck / Application studies", font=font(38), fill="#f1eee7")
    draw.text((32, 78), "Five applications. One familiar set of controls.", font=font(23), fill="#a8acae")
    for i, (title, filename) in enumerate(PANELS):
        x, y = 32 + (i % 2) * 748, 140 + (i // 2) * 454
        draw.text((x, y), title, font=font(24), fill="#edb866")
        with Image.open(args.screens / filename) as source:
            canvas.paste(source.convert("RGB").resize((724, 407), Image.Resampling.LANCZOS), (x, y + 34))
        draw.rectangle((x, y + 34, x + 723, y + 440), outline="#3c4242", width=1)
    draw.text((32, 1520), "Original offline content / Interactive UI prototype / Playback and games are simulated", font=font(22), fill="#a8acae")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(args.output, quality=90, method=6)
    print(args.output)


if __name__ == "__main__":
    main()
