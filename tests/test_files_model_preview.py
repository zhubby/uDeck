import base64
import importlib
import struct

from PySide6.QtCore import QModelIndex
from PySide6.QtGui import QColor, QImage


def test_file_model_fetches_rows_incrementally_and_preserves_marks():
    module = importlib.import_module("udeck.file_model")
    model = module.FileListModel()
    entries = [{"id": str(index), "name": f"file{index}.txt"} for index in range(1000)]
    model.set_entries(entries)
    assert model.rowCount() == 200
    assert model.canFetchMore(QModelIndex())
    model.fetchMore(QModelIndex())
    assert model.rowCount() == 400
    model.set_marks({"2"}, {"3"})
    role = next(role for role, name in model.roleNames().items() if bytes(name) == b"entry")
    assert model.data(model.index(2), role)["marked"]
    assert model.data(model.index(3), role)["cut"]
    model.ensure_index(999)
    assert model.rowCount() == 1000
    assert not model.canFetchMore(QModelIndex())


def test_text_preview_is_bounded_plain_text_and_does_not_follow_symlinks(tmp_path):
    module = importlib.import_module("udeck.file_preview")
    path = tmp_path / "example.txt"
    path.write_text("<script>literal</script>\n" + "a" * 100000)
    result = module.preview(path)
    assert result["previewText"].startswith("<script>literal</script>")
    assert len(result["previewText"]) <= 65536
    assert result["truncated"]
    link = tmp_path / "link.txt"
    link.symlink_to(path)
    result = module.preview(link)
    assert result.get("previewText", "") == ""
    assert result["linkTarget"] == str(path)


def test_binary_preview_does_not_render_binary_bytes(tmp_path):
    module = importlib.import_module("udeck.file_preview")
    path = tmp_path / "binary.txt"
    path.write_bytes(b"hello\x00world")
    result = module.preview(path)
    assert not result.get("previewText")
    assert result["previewType"] == "metadata"


def test_image_preview_is_scaled_and_svg_and_large_images_stay_metadata_only(tmp_path):
    module = importlib.import_module("udeck.file_preview")
    image = QImage(1600, 800, QImage.Format.Format_RGB32)
    image.fill(QColor("#EDB866"))
    path = tmp_path / "image.png"
    assert image.save(str(path))
    result = module.preview(path)
    assert result["previewType"] == "image"
    assert result["previewImage"].startswith("data:image/png;base64,")
    svg = tmp_path / "image.svg"
    svg.write_text('<svg xmlns="http://www.w3.org/2000/svg"><image href="https://invalid.example/image.png"/></svg>')
    assert module.preview(svg)["previewType"] == "metadata"
    with path.open("wb") as writer:
        writer.truncate(8 * 1024 * 1024 + 1)
    assert module.preview(path)["previewType"] == "metadata"


def test_image_preview_bounds_apply_after_exif_rotation(tmp_path):
    module = importlib.import_module("udeck.file_preview")
    image = QImage(1600, 800, QImage.Format.Format_RGB32)
    image.fill(QColor("#EDB866"))
    path = tmp_path / "rotated.jpg"
    assert image.save(str(path))
    original = path.read_bytes()
    exif = b"Exif\x00\x00II\x2a\x00\x08\x00\x00\x00\x01\x00\x12\x01\x03\x00\x01\x00\x00\x00\x06\x00\x00\x00\x00\x00\x00\x00"
    path.write_bytes(original[:2] + b"\xff\xe1" + struct.pack(">H", len(exif) + 2) + exif + original[2:])
    result = module.preview(path)
    rendered = QImage.fromData(base64.b64decode(result["previewImage"].partition(",")[2]))
    assert 0 < rendered.width() <= 840
    assert 0 < rendered.height() <= 420
