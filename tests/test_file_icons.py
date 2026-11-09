import hashlib
import importlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from udeck.files import FileOperations, file_kind

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "src/udeck/assets/file-icons"


@pytest.mark.parametrize("name, category", [
    ("notes.txt", "text"), ("README", "markdown"), ("notes.MD", "markdown"),
    ("manual.PDF", "pdf"), ("report.doc", "word"), ("report.docx", "wordx"),
    ("report.odt", "document"), ("budget.xlsx", "excel"), ("budget.ods", "spreadsheet"),
    ("table.csv", "table"), ("slides.pptx", "powerpoint"), ("slides.odp", "presentation"),
    ("book.epub", "ebook"), ("book.azw3", "ebook"), ("comic.cbz", "comic"),
    ("photo.jpeg", "jpeg"), ("photo.PNG", "png"), ("scan.bmp", "bitmap"),
    ("photo.avif", "image"), ("camera.CR3", "raw"), ("drawing.svg", "svg"),
    ("art.eps", "vector"), ("design.psd", "design"), ("song.flac", "audio"),
    ("song.mp3", "audio"), ("concert.mkv", "video"), ("film.mts", "video"),
    ("captions.srt", "subtitle"), ("playlist.m3u8", "playlist"), ("backup.zip", "zip"),
    ("backup.tar.gz", "archive"), ("backup.tar.zst", "archive"), ("data.7z", "archive"),
    ("main.py", "code"), ("main.cpp", "code"), ("main.qml", "code"),
    ("index.html", "html"), ("style.scss", "css"), ("app.mjs", "javascript"),
    ("app.jsx", "jsx"), ("app.ts", "typescript"), ("app.tsx", "tsx"),
    ("view.vue", "vue"), ("index.php", "php"), ("main.rs", "rust"),
    ("document.xml", "xml"), ("records.ndjson", "json"), ("notebook.ipynb", "json"),
    ("config.toml", "config"), (".gitignore", "config"), (".env", "config"),
    (".env.production", "config"), ("Makefile", "script"), ("launch.sh", "script"),
    ("query.sql", "sql"), ("store.sqlite3", "database"), ("font.woff2", "font"),
    ("app.deb", "package"), ("library.whl", "package"), ("program.AppImage", "package"),
    ("program.exe", "executable"), ("libudeck.so.1", "library"), ("plugin.dll", "library"),
    ("install.iso", "disk"), ("game.gba", "game"), ("save.srm", "game"),
    ("part.stl", "model"), ("scene.glb", "model"), ("drawing.dxf", "cad"),
    ("certificate.pem", "certificate"), ("secret.age", "encrypted"), ("download.torrent", "torrent"),
    ("events.ics", "calendar"), ("contacts.vcf", "contacts"), ("notes.bak", "backup"),
    ("app.log", "log"), ("payload.bin", "binary"), ("firmware.uf2", "firmware"),
    ("model.gguf", "ai"), ("project.url", "link"), ("opaque.unrecognized", "unknown"),
])
def test_common_file_names_select_distinct_tabler_categories(name, category):
    assert file_kind(name)[2] == "udeck-file-" + category


def test_directory_icon_wins_over_its_extension_and_office_icons_do_not_enable_text_preview():
    assert file_kind("album.mp3", directory=True) == ("folder", "inode/directory", "udeck-file-folder")
    assert file_kind("report.docx")[0] == "other"
    assert file_kind("font.ttf")[0] == "other"


@pytest.mark.parametrize("mime, category", [
    ("application/pdf", "pdf"), ("application/vnd.ms-excel", "excel"),
    ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", "wordx"),
    ("application/vnd.oasis.opendocument.presentation", "presentation"),
    ("image/webp", "image"), ("audio/ogg", "audio"), ("video/webm", "video"),
    ("application/x-7z-compressed", "archive"), ("application/epub+zip", "ebook"),
    ("font/woff2", "font"), ("text/x-python", "code"), ("text/plain", "text"),
    ("application/octet-stream", "unknown"),
])
def test_mime_fallback_handles_names_without_a_known_extension(mime, category):
    module = importlib.import_module("udeck.file_icons")
    assert module.file_icon("download", mime) == "udeck-file-" + category


def test_directory_entries_expose_type_icons_without_reading_or_rewriting_contents(tmp_path):
    payloads = {"report.pdf": b"sample PDF", "budget.xlsx": b"sample spreadsheet", "font.otf": b"sample font"}
    for name, payload in payloads.items():
        (tmp_path / name).write_bytes(payload)
    entries = FileOperations().list_directory(tmp_path)
    assert {entry["name"]: entry["icon"] for entry in entries} == {
        "budget.xlsx": "udeck-file-excel", "font.otf": "udeck-file-font", "report.pdf": "udeck-file-pdf",
    }
    assert {name: (tmp_path / name).read_bytes() for name in payloads} == payloads


def test_tabler_resources_keep_original_license_and_verified_source_hashes():
    assert (ASSETS / "manifest.json").is_file()
    manifest = json.loads((ASSETS / "manifest.json").read_text())
    assert manifest["version"] == "3.51.0"
    assert manifest["archiveSha256"] == "b30108713d3fa60aee862c2a133225da8e0f309be0708fe2925763ff810c766c"
    assert manifest["license"] == "MIT"
    assert "Paweł Kuna" in (ASSETS / "LICENSE.txt").read_text()
    for name, metadata in manifest["files"].items():
        data = (ASSETS / name).read_bytes()
        assert len(data) == metadata["bytes"], name
        assert hashlib.sha256(data).hexdigest() == metadata["sha256"], name
        source = data.removesuffix(b"\n") if name.endswith(".svg") else data
        assert hashlib.sha256(source).hexdigest() == metadata["sourceSha256"], name


def test_tabler_file_icons_render_offline_and_remain_distinct_at_supported_sizes(tmp_path):
    result = subprocess.run(
        [sys.executable, str(ROOT / "tests/file_icons_probe.py"), str(tmp_path)],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen", "QT_QUICK_BACKEND": "software"},
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout.strip().splitlines()[-1])
    assert report["sizes"] == [48, 80, 144]
    assert report["allRendered"]
    assert (tmp_path / "file-icons.png").stat().st_size > 10000
