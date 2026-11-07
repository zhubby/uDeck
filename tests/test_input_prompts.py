import hashlib
import json
import struct
from pathlib import Path


def test_kenney_resources_are_bundled_with_provenance_and_license():
    root = Path(__file__).resolve().parents[1] / "src/udeck/assets/input-prompts"
    assert (root / "manifest.json").is_file(), "Bundle the selected Kenney input prompts"
    manifest = json.loads((root / "manifest.json").read_text())
    assert manifest["source"] == "https://kenney.nl/assets/input-prompts"
    assert manifest["archiveSha256"] == "ac2fcf599080b0f3ba2d174c9474db6df1a0e96ff0662580e2da79a122ab78a1"
    assert b"Creative Commons Zero, CC0" in (root / "License.txt").read_bytes()
    assert {item["kit"] for item in manifest["files"].values()} == {
        "Keyboard & Mouse", "Nintendo Gamecube",
    }
    for name, metadata in manifest["files"].items():
        content = (root / name).read_bytes()
        assert hashlib.sha256(content).hexdigest() == metadata["sha256"], name
        prototype = root.parents[3] / "docs/design/app-suite/prototype/assets/input-prompts" / name
        assert prototype.read_bytes() == content, name
        if name.endswith(".png"):
            assert content[:8] == b"\x89PNG\r\n\x1a\n", name
            assert struct.unpack(">II", content[16:24]) == (128, 128), name
