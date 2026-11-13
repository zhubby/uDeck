"""Fixed local RetroArch Monochrome artwork, independent of desktop themes."""

import json
from pathlib import Path

ICON_ROOT = Path(__file__).with_name("resources") / "platform-icons"
MANIFEST = json.loads((ICON_ROOT / "manifest.json").read_text())


def platform_icon(platform):
    name = MANIFEST["platforms"].get(platform, "generic")
    return (ICON_ROOT / (name + ".svg")).as_uri()
