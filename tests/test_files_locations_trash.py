import errno
import importlib
import os
from pathlib import Path
from urllib.parse import quote

import pytest


def make_trash(tmp_path, original, name="payload"):
    root = tmp_path / "Trash"
    (root / "files").mkdir(parents=True, mode=0o700)
    (root / "info").mkdir(mode=0o700)
    root.chmod(0o700)
    (root / "files" / name).write_text("recovered content")
    (root / "info" / (name + ".trashinfo")).write_text(
        "[Trash Info]\nPath=" + quote(str(original)) + "\nDeletionDate=2026-11-08T20:00:00\n"
    )
    return root


def test_trash_restore_keeps_both_when_original_name_is_taken(tmp_path):
    module = importlib.import_module("udeck.file_trash")
    original = tmp_path / "中文 file.txt"
    original.write_text("keep original")
    root = make_trash(tmp_path, original)
    store = module.TrashStore(roots=[{"path": str(root), "top": str(tmp_path), "home": True}])
    entries = store.entries()
    assert entries[0]["name"] == original.name
    result = store.restore(entries[0])
    assert result.name == "中文 file (2).txt"
    assert original.read_text() == "keep original"
    assert result.read_text() == "recovered content"
    assert not (root / "files/payload").exists()
    assert not (root / "info/payload.trashinfo").exists()


@pytest.mark.parametrize("unsafe", ["../escape", "/outside", "a/../../escape"])
def test_external_trash_rejects_paths_outside_its_mount(tmp_path, unsafe):
    module = importlib.import_module("udeck.file_trash")
    root = make_trash(tmp_path, Path(unsafe))
    store = module.TrashStore(roots=[{"path": str(root), "top": str(tmp_path), "home": False}])
    assert store.entries() == []
    assert (root / "files/payload").is_file()


def test_trash_never_follows_metadata_symlinks_or_removes_changed_metadata(tmp_path):
    module = importlib.import_module("udeck.file_trash")
    original = tmp_path / "original.txt"
    root = make_trash(tmp_path, original)
    store = module.TrashStore(roots=[{"path": str(root), "top": str(tmp_path), "home": True}])
    entry = store.entries()[0]
    info = root / "info/payload.trashinfo"
    info.unlink()
    info.symlink_to(tmp_path / "outside")
    with pytest.raises((OSError, ValueError)):
        store.restore(entry)
    assert not original.exists()
    assert (root / "files/payload").read_text() == "recovered content"


def test_mount_inventory_decodes_spaces_and_omits_system_mounts():
    module = importlib.import_module("udeck.file_locations")
    text = "\n".join([
        "41 1 8:1 / / rw - ext4 /dev/sda1 rw",
        "42 1 0:10 / /proc rw - proc proc rw",
        r"43 1 8:17 / /media/USB\040Drive ro - vfat /dev/sdb1 ro",
    ])
    locations = module.mounted_locations(text)
    assert len(locations) == 1
    assert locations[0]["path"] == "/media/USB Drive"
    assert locations[0]["readonly"]
    assert locations[0]["mountId"] == "43"


def test_unmount_revalidates_identity_and_never_uses_force_or_sudo(monkeypatch):
    module = importlib.import_module("udeck.file_locations")
    location = {"mountId": "43", "path": "/media/USB Drive", "device": "/dev/sdb1"}
    monkeypatch.setattr(module, "mounted_locations", lambda: [location])
    calls = []
    monkeypatch.setattr(module.subprocess, "run", lambda command, **options: calls.append(command))
    module.unmount(location)
    assert calls == [["gio", "mount", "--unmount", "--", "file:///media/USB%20Drive"]]
    monkeypatch.setattr(module, "mounted_locations", lambda: [{**location, "mountId": "44"}])
    with pytest.raises(ValueError):
        module.unmount(location)
    assert len(calls) == 1
    with pytest.raises(ValueError):
        module.unmount({"mountId": "1", "path": "/", "device": "/dev/sda1"})


def test_user_locations_parse_xdg_configuration_without_running_a_shell(tmp_path):
    module = importlib.import_module("udeck.file_locations")
    config = tmp_path / "user-dirs.dirs"
    (tmp_path / "我的下载").mkdir()
    config.write_text('XDG_DOWNLOAD_DIR="$HOME/我的下载"\nXDG_DOCUMENTS_DIR="$(touch /tmp/never)"\n')
    locations = module.user_locations(home=tmp_path, configuration=config)
    assert any(item["path"] == str(tmp_path / "我的下载") for item in locations)
    assert all("$(" not in item["path"] for item in locations)
    assert locations[0]["path"] == str(tmp_path)


def test_trash_private_root_is_not_followed_when_replaced_by_a_symlink(tmp_path):
    module = importlib.import_module("udeck.file_trash")
    root = make_trash(tmp_path, tmp_path / "original")
    alias = tmp_path / "alias"
    alias.symlink_to(root, target_is_directory=True)
    store = module.TrashStore(roots=[{"path": str(alias), "top": str(tmp_path), "home": True}])
    assert store.entries() == []
    assert os.path.lexists(root / "files/payload")


def test_cross_filesystem_restore_preserves_the_trash_entry(tmp_path, monkeypatch):
    module = importlib.import_module("udeck.file_trash")
    original = tmp_path / "original.txt"
    root = make_trash(tmp_path, original)
    store = module.TrashStore(roots=[{"path": str(root), "top": str(tmp_path), "home": True}])
    entry = store.entries()[0]

    def cross_device(source, target):
        raise OSError(errno.EXDEV, "cross device")

    monkeypatch.setattr(module, "rename_noreplace", cross_device)
    with pytest.raises(ValueError, match="same file system"):
        store.restore(entry)
    assert not original.exists()
    assert store.entries()[0]["id"] == entry["id"]
    assert (root / "files/payload").read_text() == "recovered content"


def test_invalid_xdg_directory_encoding_does_not_break_locations(tmp_path):
    module = importlib.import_module("udeck.file_locations")
    configuration = tmp_path / "user-dirs.dirs"
    configuration.write_bytes(b"\xff\xfe")
    assert module.user_locations(home=tmp_path, configuration=configuration)[0]["path"] == str(tmp_path)
