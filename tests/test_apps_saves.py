import json
import zipfile
from urllib.error import HTTPError
from urllib.request import urlopen

import pytest

from udeck.apps.emulator.catalog import CoreCatalog
from udeck.apps.emulator.controller import SaveStore, content_hash, preflight, stock_controls
from udeck.apps.reader.server import BookServer


def test_save_group_rejects_wrong_core_and_content_and_detects_corruption(tmp_path):
    engine_file = tmp_path / "engine-state"
    engine_file.write_bytes(b"Original serialized core state")
    store = SaveStore(tmp_path / "saves")
    store.publish("1", engine_file, {"contentHash": "game-a", "coreHash": "core-1"})
    path, metadata = store.load("1", "game-a", "core-1")
    assert path.read_bytes() == engine_file.read_bytes()
    assert metadata["version"] == 1
    with pytest.raises(ValueError, match="another game or core"):
        store.load("1", "game-a", "core-2")
    with pytest.raises(ValueError, match="another game or core"):
        store.load("1", "game-b", "core-1")
    path.write_bytes(b"damaged")
    with pytest.raises(ValueError, match="damaged"):
        store.load("1", "game-a", "core-1")


def test_failed_new_save_retains_previous_slot_and_auto_is_separate(tmp_path, monkeypatch):
    source = tmp_path / "state"
    source.write_bytes(b"first")
    store = SaveStore(tmp_path / "saves")
    meta = {"contentHash": "a", "coreHash": "b"}
    store.publish("1", source, meta)
    store.publish("auto", source, meta)
    previous = store.manifest()
    source.write_bytes(b"second")
    original = __import__("os").replace
    def fail_manifest(a, b):
        if str(b).endswith("slots.json"):
            raise OSError("disk full")
        return original(a, b)
    monkeypatch.setattr("udeck.apps.common.state.os.replace", fail_manifest)
    with pytest.raises(OSError):
        store.publish("1", source, meta)
    assert store.manifest() == previous
    assert store.load("1", "a", "b")[0].read_bytes() == b"first"
    assert store.load("auto", "a", "b")[0].read_bytes() == b"first"


def test_empty_or_forged_slot_cannot_be_loaded(tmp_path):
    store = SaveStore(tmp_path)
    with pytest.raises(ValueError, match="empty"):
        store.load("2", "a", "b")
    (tmp_path / "slots.json").write_text(json.dumps({"1": "../../secret"}))
    with pytest.raises(ValueError, match="empty"):
        store.load("1", "a", "b")


def test_invalid_save_manifest_is_rejected_without_replacing_it(tmp_path):
    manifest = tmp_path / "slots.json"
    manifest.write_text("[]")
    store = SaveStore(tmp_path)
    with pytest.raises(ValueError, match="damaged"):
        store.manifest()
    assert manifest.read_text() == "[]"


def test_stock_mapping_requires_exact_connected_device_identity(tmp_path):
    device = tmp_path / "js2/device"
    (device / "id").mkdir(parents=True)
    (device / "id/vendor").write_text("1eaf")
    (device / "id/product").write_text("0024")
    (device / "uniq").write_text("other-firmware")
    (device / "name").write_text("ClockworkPI uConsole")
    assert stock_controls(tmp_path) == {}
    (device / "uniq").write_text("20230713")
    mapping = stock_controls(tmp_path)
    assert mapping["input_player1_joypad_index"] == "2"
    assert mapping["input_player1_a_btn"] == '"1"'
    assert mapping["input_player1_b_btn"] == '"2"'
    assert mapping["input_player1_left_btn"] == '"h0left"'


def test_preflight_reports_missing_core_firmware_and_disc_tracks(tmp_path):
    cue = tmp_path / "disc.cue"
    cue.write_text('FILE "track.bin" BINARY\n')
    core = tmp_path / "pcsx_rearmed_libretro.so"
    core.write_bytes(b"core-placeholder-only-for-preflight")
    core.with_suffix(".info").write_text('supported_extensions = "cue|bin"\n')
    preferences = {"coreDirectory": str(tmp_path), "firmwareDirectory": str(tmp_path)}
    catalog = CoreCatalog.discover(preferences)
    catalog.apply_probe("pcsx_rearmed", {"status": "available"})
    item = {"platform": "PS1", "path": str(cue), "format": "CUE"}
    checks = preflight(item, preferences, "/usr/bin/retroarch", catalog=catalog, validate_native=False)
    assert not checks["ready"]
    assert any("scph5501.bin" in str(e) for e in checks["errors"])
    assert any("track.bin" in str(e) for e in checks["errors"])
    (tmp_path / "scph5501.bin").write_bytes(b"fixture")
    (tmp_path / "track.bin").write_bytes(b"fixture")
    assert preflight(item, preferences, "retroarch", catalog=catalog, validate_native=False)["ready"]


def test_disc_save_identity_includes_track_content_when_cue_is_unchanged(tmp_path):
    cue = tmp_path / "disc.cue"
    cue.write_text('FILE "track 1.bin" BINARY\nFILE track2.bin BINARY\n')
    one, two = tmp_path / "track 1.bin", tmp_path / "track2.bin"
    one.write_bytes(b"original disc one")
    two.write_bytes(b"original disc two")
    item = {"path": str(cue), "format": "CUE"}
    original = content_hash(item)
    two.write_bytes(b"replaced disc two")
    assert content_hash(item) != original


def test_book_server_is_token_scoped_and_csp_disables_book_scripts(tmp_path):
    path = tmp_path / "book.txt"
    path.write_text("Original <script> text")
    book = BookServer({"path": str(path), "format": "TXT", "title": "Original"}, {}, {})
    try:
        with urlopen(book.url) as response:
            csp = response.headers["Content-Security-Policy"]
            assert "'strict-dynamic'" in csp and "'unsafe-eval'" not in csp
            assert "connect-src 'self' blob:" in csp and "form-action 'none'" in csp
        with urlopen(book.url.replace("index.html", "text.txt")) as response:
            assert response.read().decode() == "Original <script> text"
        for suffix in ("../../../../etc/passwd", "foliate/LICENSE", "book/missing"):
            with pytest.raises(HTTPError):
                urlopen(book.url.replace("index.html", suffix))
        with pytest.raises(HTTPError):
            urlopen(book.url.replace(book.token, "wrong-token"))
    finally:
        book.close()
    assert book.closed


def test_epub_zip_slip_and_bomb_entries_are_rejected_without_extraction(tmp_path):
    path = tmp_path / "bad.epub"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("../outside", "bad")
    with pytest.raises(ValueError, match="Invalid EPUB"):
        BookServer({"path": str(path), "format": "EPUB", "title": "Bad"}, {}, {})
    assert not (tmp_path.parent / "outside").exists()
