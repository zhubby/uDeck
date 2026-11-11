
import pytest
from PySide6.QtGui import QImage

from udeck.screenshot import capture_screen


def install_grim(tmp_path, monkeypatch, content):
    source = tmp_path / 'screen.png'
    source.write_bytes(content)
    tool = tmp_path / 'grim'
    tool.write_text('#!/usr/bin/python3\nimport sys\nfrom pathlib import Path\n'
                    'assert sys.argv[1:] == ["-t", "png", "-"]\n'
                    f'sys.stdout.buffer.write(Path({str(source)!r}).read_bytes())\n')
    tool.chmod(0o700)
    monkeypatch.setenv('PATH', str(tmp_path))


def test_capture_uses_full_output_and_unique_private_png_files(tmp_path, monkeypatch):
    image = QImage(120, 80, QImage.Format.Format_RGB32)
    image.fill(0xff24875a)
    source = tmp_path / 'fixture.png'
    image.save(str(source))
    install_grim(tmp_path, monkeypatch, source.read_bytes())
    folder = tmp_path / 'Pictures/Screenshots'
    first, second = capture_screen(folder), capture_screen(folder)
    assert first != second and first.parent == folder and first.suffix == '.png'
    assert first.stat().st_mode & 0o777 == 0o600
    loaded = QImage(str(first))
    assert loaded.width() == 120 and loaded.height() == 80
    assert loaded.pixelColor(50, 30).name() == '#24875a'
    assert len(list(folder.iterdir())) == 2


def test_invalid_capture_never_reports_or_leaves_a_saved_image(tmp_path, monkeypatch):
    install_grim(tmp_path, monkeypatch, b'not a screen image')
    folder = tmp_path / 'Screenshots'
    with pytest.raises(ValueError):
        capture_screen(folder)
    assert list(folder.iterdir()) == []
