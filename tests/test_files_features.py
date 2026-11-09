import threading

import pytest

from udeck import files
from udeck.desktop import DesktopCatalog, parse_exec
from udeck.files import FileOperations


def test_file_metadata_identifies_media_and_exposes_sortable_values(tmp_path):
    (tmp_path / "song.flac").write_bytes(b"music")
    entry = FileOperations().list_directory(tmp_path)[0]
    assert entry["kind"] == "audio"
    assert entry["mime"] == "audio/flac"
    assert entry["size"] == 5
    assert entry["modified"] > 0
    assert entry["icon"] == "udeck-file-audio"


def test_file_search_sort_and_filter_keep_directories_first(tmp_path):
    (tmp_path / "album").mkdir()
    for name in ("track10.flac", "track2.flac", "notes.txt"):
        (tmp_path / name).write_text(name)
    entries = FileOperations().list_directory(tmp_path)
    result = files.query_entries(entries, query="track", sort="name")
    assert [entry["name"] for entry in result] == ["track2.flac", "track10.flac"]
    result = files.query_entries(entries, kind="audio")
    assert [entry["name"] for entry in result] == ["album", "track2.flac", "track10.flac"]
    result = files.query_entries(entries, sort="size", descending=True)
    assert result[0]["directory"]
    assert result[1]["name"] == "track10.flac"


def test_transfer_reports_actual_bytes_and_respects_an_explicit_new_name(tmp_path):
    source = tmp_path / "source.txt"
    source.write_bytes(b"a" * (1024 * 1024 + 17))
    destination = tmp_path / "destination"
    destination.mkdir()
    updates = []
    result = FileOperations().transfer(source, destination, target_name="copy.txt", progress=updates.append)
    assert result.name == "copy.txt"
    assert result.read_bytes() == source.read_bytes()
    assert sum(update.get("bytes", 0) for update in updates) == source.stat().st_size


def test_transfer_measurement_does_not_follow_links_and_can_cancel(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "regular").write_bytes(b"abc")
    (source / "link").symlink_to(source, target_is_directory=True)
    measurement = FileOperations().measure([source])
    assert measurement == {"bytes": 3, "files": 2}
    cancelled = threading.Event()
    cancelled.set()
    with pytest.raises(InterruptedError):
        FileOperations().measure([source], cancelled=cancelled)


def test_keep_both_names_preserve_the_extension_and_never_clobber(tmp_path):
    (tmp_path / "report.epub").touch()
    (tmp_path / "report (2).epub").touch()
    assert files.available_name(tmp_path, "report.epub") == "report (3).epub"
    with pytest.raises(ValueError):
        FileOperations().transfer(tmp_path / "report.epub", tmp_path, target_name="../escape")


def test_open_with_expands_file_arguments_without_shell_interpretation(tmp_path):
    path = tmp_path / "中文 file;literal.txt"
    assert parse_exec("reader -- %F", files=[path]) == ["reader", "--", str(path)]
    assert parse_exec("reader %U", files=[path]) == ["reader", path.as_uri()]
    (tmp_path / "reader.desktop").write_text(
        "[Desktop Entry]\nType=Application\nName=Reader\nExec=reader %U\nMimeType=text/plain;application/epub+zip;\n"
    )
    catalog = DesktopCatalog([tmp_path])
    catalog.entries()
    assert [entry["id"] for entry in catalog.handlers("application/epub+zip")] == ["reader.desktop"]


def test_exec_field_expansion_is_one_pass_and_keeps_literal_filename_fields(tmp_path):
    path = tmp_path / "literal %U %c %% file.txt"
    assert parse_exec("reader --file=%f --name=%c", name="A %k app", files=[path]) == [
        "reader", "--file=" + str(path), "--name=A %k app",
    ]


def test_natural_sort_accepts_non_decimal_numeric_characters():
    entries = [{"id": name, "name": name} for name in ("note².txt", "note10.txt", "note2.txt")]
    assert [entry["name"] for entry in files.query_entries(entries)] == ["note2.txt", "note10.txt", "note².txt"]


@pytest.mark.parametrize("name", ["settings.ini", "app.conf", "launch.sh", ".bashrc", ".env", "Makefile"])
def test_common_configuration_and_script_files_support_safe_text_preview(name):
    assert files.file_kind(name)[0] == "text"
