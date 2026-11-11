import json
import struct
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen

import pytest
from mobi_fixture import mobi_bytes

from udeck.apps.common.library import Source, scan
from udeck.apps.reader.server import BookServer
from udeck.desktop import DesktopCatalog
from udeck.files import file_kind


def book_item(path):
    return {"path": str(path), "format": "MOBI", "title": "Original MOBI"}


def test_mobi_is_indexed_with_stable_identity_and_classified_as_book(tmp_path):
    path = tmp_path / "Original.MOBI"
    path.write_bytes(mobi_bytes())
    source = Source.create(tmp_path)
    items = scan(source, "reader")
    assert len(items) == 1 and items[0]["format"] == "MOBI"
    assert scan(source, "reader")[0]["id"] == items[0]["id"]
    assert file_kind(path.name)[:2] == ("book", "application/x-mobipocket-ebook")


@pytest.mark.parametrize("compression", [1, 2])
def test_mobi_server_serves_original_records_with_session_isolation(tmp_path, compression):
    path = tmp_path / "original.mobi"
    original = mobi_bytes(compression)
    path.write_bytes(original)
    server = BookServer(book_item(path), {"cfi": "saved"}, {"fontFamily": "serif"})
    try:
        config = json.loads(server.resource("config.json")[0])
        assert config["format"] == "MOBI" and config["mobiSize"] == len(original)
        assert config["position"]["cfi"] == "saved"
        assert config["preferences"]["fontFamily"] == "serif"
        data, mime, csp = server.resource("mobi/60/68")
        assert data == b"BOOKMOBI" and mime == "application/octet-stream"
        assert "default-src 'none'" in csp and "connect-src 'self' blob:" in csp
        with urlopen(server.url.replace("index.html", "mobi/0/78")) as response:
            assert response.read() == original[:78]
        with pytest.raises(HTTPError) as error:
            urlopen(server.url.replace(server.token, "wrong").replace("index.html", "mobi/0/78"))
        assert error.value.code == 404
        for route in ("text.txt", "book/../private", "mobi/-1/5", "mobi/0/999999999",
                      "mobi/12/10", "mobi/0/1/private", "foliate/../server.py"):
            with pytest.raises((KeyError, ValueError)):
                server.resource(route)
        assert b"class MOBI" in server.resource("foliate/mobi.js")[0]
    finally:
        server.close()
    with pytest.raises((KeyError, OSError, ValueError)):
        server.resource("mobi/0/78")
    assert path.read_bytes() == original


def test_mobi_over_txt_limit_is_read_in_bounded_slices(tmp_path):
    path = tmp_path / "large.mobi"
    raw = bytearray(mobi_bytes())
    count = struct.unpack_from(">H", raw, 76)[0]
    table_end = 78 + count * 8
    raw[table_end:table_end] = b"\0" * 16
    struct.pack_into(">H", raw, 76, count + 2)
    for i in range(count):
        offset = struct.unpack_from(">I", raw, 78 + i * 8)[0]
        struct.pack_into(">I", raw, 78 + i * 8, offset + 16)
    # Two sparse resource records keep each record below the slice limit.
    struct.pack_into(">IIII", raw, table_end, len(raw), count, 40 * 1024 * 1024, count + 1)
    path.write_bytes(raw)
    with path.open("r+b") as stream:
        stream.truncate(74 * 1024 * 1024)
    server = BookServer(book_item(path), {}, {})
    try:
        assert server.resource("mobi/60/68")[0] == b"BOOKMOBI"
        with pytest.raises((KeyError, ValueError)):
            server.resource(f"mobi/0/{path.stat().st_size}")
    finally:
        server.close()


def test_packaged_reader_is_available_as_mobi_handler(tmp_path, monkeypatch):
    desktop = Path("packaging/apps/io.github.zhubby.uDeck.Reader.desktop")
    (tmp_path / desktop.name).write_text(desktop.read_text())
    monkeypatch.setattr("udeck.desktop.shutil.which", lambda name: "/usr/bin/" + name)
    catalog = DesktopCatalog([tmp_path])
    catalog.entries()
    assert [entry["id"] for entry in catalog.handlers(file_kind("book.mobi")[1])] == [desktop.name]


def test_mobi_cannot_follow_a_symbolic_link(tmp_path):
    original = tmp_path / "original.mobi"
    original.write_bytes(mobi_bytes())
    link = tmp_path / "link.mobi"
    link.symlink_to(original)
    with pytest.raises(OSError):
        BookServer(book_item(link), {}, {})


@pytest.mark.parametrize("damage", ["magic", "truncated", "offset", "order", "drm", "compression", "text-size"])
def test_invalid_mobi_is_rejected_before_starting_renderer(tmp_path, damage):
    raw = bytearray(mobi_bytes())
    first = struct.unpack_from('>I', raw, 78)[0]
    expected = "Invalid MOBI"
    if damage == "magic":
        raw[60:68] = b"NOTMOBI!"
    elif damage == "truncated":
        raw = raw[:100]
    elif damage == "offset":
        struct.pack_into('>I', raw, 78, len(raw) + 1)
    elif damage == "order":
        struct.pack_into('>I', raw, 86, first)
    elif damage == "drm":
        struct.pack_into('>H', raw, first + 12, 2)
        expected = "DRM"
    elif damage == "compression":
        struct.pack_into('>H', raw, first, 999)
        expected = "compression"
    else:
        struct.pack_into('>I', raw, first + 4, 0xffffffff)
        expected = "too large"
    path = tmp_path / "broken.mobi"
    path.write_bytes(raw)
    with pytest.raises(ValueError, match=expected):
        BookServer(book_item(path), {}, {})


def test_mobi_read_rejects_in_place_file_change(tmp_path):
    path = tmp_path / "original.mobi"
    path.write_bytes(mobi_bytes())
    server = BookServer(book_item(path), {}, {})
    try:
        path.write_bytes(b"replaced book")
        with pytest.raises(OSError):
            server.resource("mobi/0/78")
    finally:
        server.close()
