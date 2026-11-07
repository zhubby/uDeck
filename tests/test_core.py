import json

import pytest

from udeck.core import ConfigStore, Navigation, move_index
from udeck.desktop import DesktopCatalog, parse_exec
from udeck.files import CollisionError, FileOperations, InvalidName


@pytest.mark.parametrize(
    ("index", "direction", "count", "columns", "expected"),
    [
        (0, "left", 12, 5, 0),
        (4, "right", 12, 5, 4),
        (5, "left", 12, 5, 5),
        (3, "down", 12, 5, 8),
        (8, "down", 12, 5, 11),
        (11, "down", 12, 5, 11),
        (7, "up", 12, 5, 2),
        (0, "up", 12, 1, 0),
        (0, "down", 0, 5, -1),
    ],
)
def test_spatial_navigation(index, direction, count, columns, expected):
    assert move_index(index, direction, count, columns) == expected


def test_navigation_restores_page_focus_and_modal_owner():
    navigation = Navigation()
    navigation.set_page("apps")
    navigation.select(7)
    navigation.open_modal()
    navigation.close_modal()
    assert navigation.index == 7
    navigation.set_page("files")
    navigation.select(2)
    navigation.set_page("apps")
    assert navigation.index == 7


def test_top_row_enters_tabs_and_down_restores_selection():
    navigation = Navigation()
    navigation.select(2)
    navigation.move("up", 12, 5)
    assert navigation.zone == "tabs"
    navigation.move("down", 12, 5)
    assert navigation.zone == "content"
    assert navigation.index == 2


def test_config_is_atomic_private_and_survives_invalid_input(tmp_path):
    config_path = tmp_path / "config" / "settings.json"
    store = ConfigStore(config_path)
    store.favorite("terminal.desktop", True)
    store.remember("terminal.desktop")
    assert ConfigStore(config_path).data["favorites"] == ["terminal.desktop"]
    assert config_path.stat().st_mode & 0o777 == 0o600
    config_path.write_text("not json")
    assert ConfigStore(config_path).data["favorites"] == []


def test_config_rejects_wrong_shapes(tmp_path):
    config_path = tmp_path / "settings.json"
    config_path.write_text(json.dumps({"favorites": "oops", "recent": [5], "focus": []}))
    store = ConfigStore(config_path)
    assert store.data["favorites"] == []
    assert store.data["recent"] == []
    assert store.data["focus"] == {}


def test_catalog_localization_visibility_and_user_override(tmp_path, monkeypatch):
    system_directory = tmp_path / "system"
    user_directory = tmp_path / "user"
    system_directory.mkdir()
    user_directory.mkdir()
    (system_directory / "app.desktop").write_text(
        "[Desktop Entry]\nType=Application\nName=Terminal\nName[zh_CN]=终端\n"
        "Exec=/bin/echo %U\nCategories=System;TerminalEmulator;\n"
    )
    (system_directory / "hidden.desktop").write_text(
        "[Desktop Entry]\nType=Application\nName=Hidden\nExec=/bin/echo\nNoDisplay=true\n"
    )
    catalog = DesktopCatalog([user_directory, system_directory], locale="zh_CN")
    assert [entry["name"] for entry in catalog.entries()] == ["终端"]
    (user_directory / "app.desktop").write_text("[Desktop Entry]\nHidden=true\n")
    assert catalog.entries() == []


def test_exec_field_codes_are_not_shell_commands():
    assert parse_exec('"/path with spaces/tool" --name %c %i %U %%', "中文", "icon") == [
        "/path with spaces/tool", "--name", "中文", "--icon", "icon", "%"
    ]


def test_files_are_directory_first_and_keep_unicode_paths(tmp_path):
    (tmp_path / "中文 文件.txt").write_text("hello")
    (tmp_path / "文件夹").mkdir()
    (tmp_path / ".private").touch()
    entries = FileOperations().list_directory(tmp_path)
    assert [entry["name"] for entry in entries] == ["文件夹", "中文 文件.txt"]
    assert entries[1]["path"] == str(tmp_path / "中文 文件.txt")


@pytest.mark.parametrize("name", ["", " ", ".", "..", "../outside", "a/b", "bad\x00name"])
def test_file_names_cannot_escape_parent(tmp_path, name):
    with pytest.raises(InvalidName):
        FileOperations().mkdir(tmp_path, name)


def test_copy_requires_explicit_overwrite_and_preserves_source(tmp_path):
    source_directory = tmp_path / "source"
    target_directory = tmp_path / "target"
    source_directory.mkdir()
    target_directory.mkdir()
    source = source_directory / "文件.txt"
    source.write_text("new")
    target = target_directory / source.name
    target.write_text("old")
    operations = FileOperations()
    with pytest.raises(CollisionError):
        operations.transfer(source, target_directory)
    assert target.read_text() == "old"
    operations.transfer(source, target_directory, replace=True)
    assert target.read_text() == "new"
    assert source.read_text() == "new"


def test_copy_does_not_follow_symlinks_and_rejects_recursive_destination(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "file").write_text("value")
    (source / "link").symlink_to("file")
    destination = tmp_path / "destination"
    destination.mkdir()
    operations = FileOperations()
    result = operations.transfer(source, destination)
    assert (result / "link").is_symlink()
    with pytest.raises(ValueError):
        operations.transfer(source, source)


def test_cancelled_copy_cleans_staging_files(tmp_path):
    import threading

    source = tmp_path / "source"
    source.write_bytes(b"content")
    destination = tmp_path / "destination"
    destination.mkdir()
    cancelled = threading.Event()
    cancelled.set()
    with pytest.raises(InterruptedError):
        FileOperations().transfer(source, destination, cancelled=cancelled)
    assert list(destination.iterdir()) == []


def test_rename_never_overwrites_without_confirmation(tmp_path):
    source = tmp_path / "source"
    source.write_text("original")
    (tmp_path / "target").write_text("keep")
    with pytest.raises(CollisionError):
        FileOperations().rename(source, "target")
    assert source.read_text() == "original"


def test_move_on_same_filesystem_is_atomic_not_copy_delete(tmp_path):
    source = tmp_path / "source"
    source.write_text("original")
    inode = source.stat().st_ino
    destination = tmp_path / "destination"
    destination.mkdir()
    result = FileOperations().transfer(source, destination, move=True)
    assert result.stat().st_ino == inode
    assert not source.exists()


def test_rename_cannot_clobber_a_file_created_after_preflight(tmp_path, monkeypatch):
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.write_text("original")
    target.write_text("keep")
    monkeypatch.setattr("udeck.files.os.path.lexists", lambda path: False)
    with pytest.raises(CollisionError):
        FileOperations().rename(source, "target")
    assert target.read_text() == "keep"


def test_shell_desktop_entry_is_not_recursively_launchable(tmp_path):
    (tmp_path / "io.github.zhubby.uDeck.desktop").write_text(
        "[Desktop Entry]\nType=Application\nName=uDeck\nExec=udeck\n"
    )
    assert DesktopCatalog([tmp_path]).entries() == []


def test_preferences_are_saved_and_validated(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"preferences": {"showHidden": True, "category": "Game"}}))
    config = ConfigStore(path)
    assert config.data["preferences"] == {"showHidden": True, "category": "Game", "language": "en", "theme": "classic"}


def test_dbus_activatable_desktop_entry_does_not_require_exec(tmp_path):
    (tmp_path / "org.example.DBusApp.desktop").write_text(
        "[Desktop Entry]\nType=Application\nName=DBus App\nDBusActivatable=true\n"
    )
    assert DesktopCatalog([tmp_path]).entries()[0]["name"] == "DBus App"
