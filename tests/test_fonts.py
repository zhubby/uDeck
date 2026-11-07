import hashlib
import json
from pathlib import Path

import pytest

FONTS = Path(__file__).resolve().parents[1] / "src/udeck/fonts"
MANIFEST = json.loads((FONTS / "manifest.json").read_text())


@pytest.mark.parametrize("name", list(MANIFEST["files"]))
def test_bundled_font_assets_match_the_original_upstream_files(name):
    data = (FONTS / name).read_bytes()
    expected = MANIFEST["files"][name]
    assert len(data) == expected["bytes"]
    assert hashlib.sha256(data).hexdigest() == expected["sha256"]
    if name.endswith(".txt"):
        assert b"SIL OPEN FONT LICENSE Version 1.1" in data
