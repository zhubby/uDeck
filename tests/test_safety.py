import errno
import os
from pathlib import Path

import pytest

from udeck import files
from udeck.backend import validate_wifi_password
from udeck.files import FileOperations
from udeck.i18n import render


@pytest.mark.parametrize(("password", "security", "valid"), [
    ("short", "WPA2", False), ("12345678", "WPA2", True),
    ("a" * 64, "WPA2", True), ("z" * 64, "WPA2", False),
    ("short", "WPA3", True), ("", "WPA3", False), ("bad\x00secret", "WPA3", False),
])
def test_personal_wifi_password_rules(password, security, valid):
    if valid:
        assert validate_wifi_password(password, security) == password
    else:
        with pytest.raises(ValueError):
            validate_wifi_password(password, security)


def test_cross_filesystem_move_recycles_source_instead_of_deleting(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.write_text("original")
    destination = tmp_path / "destination"
    destination.mkdir()
    atomic_rename = files.rename_noreplace

    def cross_device(origin, target):
        if Path(origin) == source:
            raise OSError(errno.EXDEV, "cross device")
        atomic_rename(origin, target)

    recycled = tmp_path / "recycled"
    monkeypatch.setattr(files, "rename_noreplace", cross_device)
    operations = FileOperations()
    monkeypatch.setattr(operations, "trash", lambda path: path.rename(recycled))
    target = operations.transfer(source, destination, move=True)
    assert target.read_text() == "original"
    assert recycled.read_text() == "original"
    assert not source.exists()


def test_copy_of_changing_source_aborts_without_deletion(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.write_text("original")
    destination = tmp_path / "destination"
    destination.mkdir()
    copy_stat = files.shutil.copystat

    def changed(origin, target, **options):
        copy_stat(origin, target, **options)
        source.write_text("changed while copying")

    monkeypatch.setattr(files.shutil, "copystat", changed)
    with pytest.raises(RuntimeError) as failure:
        FileOperations().transfer(source, destination)
    assert "发生变化" in render(failure.value, "zh_CN")
    assert source.read_text() == "changed while copying"
    assert list(destination.iterdir()) == []


def test_copy_of_fifo_is_rejected_without_blocking(tmp_path):
    source = tmp_path / "pipe"
    os.mkfifo(source)
    destination = tmp_path / "destination"
    destination.mkdir()
    with pytest.raises(ValueError) as failure:
        FileOperations().transfer(source, destination)
    assert "管道" in render(failure.value, "zh_CN")


def test_copy_staging_is_private_before_metadata_is_applied(tmp_path, monkeypatch):
    source = tmp_path / "private"
    source.write_text("private content")
    source.chmod(0o600)
    destination = tmp_path / "destination"
    destination.mkdir()
    copy_stat = files.shutil.copystat

    def check_private(origin, target, **options):
        assert target.stat().st_mode & 0o077 == 0
        copy_stat(origin, target, **options)

    monkeypatch.setattr(files.shutil, "copystat", check_private)
    result = FileOperations().transfer(source, destination)
    assert result.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize("action", ["trash", "open"])
def test_file_service_failure_reports_reason_without_deleting_source(tmp_path, monkeypatch, action):
    command = tmp_path / "gio"
    command.write_text("#!/bin/sh\nprintf '%s\\n' 'Trashing on system internal mounts is not supported' >&2\nexit 1\n")
    command.chmod(0o700)
    monkeypatch.setenv("PATH", str(tmp_path) + os.pathsep + os.environ["PATH"])
    source = tmp_path / "source"
    source.write_text("keep this content")
    with pytest.raises(RuntimeError, match="Trashing on system internal mounts is not supported"):
        getattr(FileOperations(), action)(source)
    assert source.read_text() == "keep this content"


def test_cross_filesystem_move_reports_trash_failure_and_keeps_both_copies(tmp_path, monkeypatch):
    command = tmp_path / "gio"
    command.write_text("#!/bin/sh\nprintf '%s\\n' 'Trashing on system internal mounts is not supported' >&2\nexit 1\n")
    command.chmod(0o700)
    monkeypatch.setenv("PATH", str(tmp_path) + os.pathsep + os.environ["PATH"])
    source = tmp_path / "source"
    source.write_text("original")
    destination = tmp_path / "destination"
    destination.mkdir()
    atomic_rename = files.rename_noreplace

    def cross_device(origin, target):
        if Path(origin) == source:
            raise OSError(errno.EXDEV, "cross device")
        atomic_rename(origin, target)

    monkeypatch.setattr(files, "rename_noreplace", cross_device)
    with pytest.raises(RuntimeError, match="Trashing on system internal mounts is not supported"):
        FileOperations().transfer(source, destination, move=True)
    assert source.read_text() == "original"
    assert (destination / "source").read_text() == "original"
