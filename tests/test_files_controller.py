import json
import threading
import time
from pathlib import Path

import pytest
from PySide6.QtCore import QCoreApplication, QEvent
from test_files_locations_trash import make_trash

from udeck.controller import ShellController
from udeck.core import ConfigStore
from udeck.file_trash import TrashStore
from udeck.mock import MockBackend


def wait_until(application, predicate, timeout=5):
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        application.processEvents()
        time.sleep(0.005)
    application.processEvents()
    assert predicate()


@pytest.fixture(scope="session")
def file_application():
    return QCoreApplication.instance() or QCoreApplication([])


@pytest.fixture
def controller(tmp_path, file_application):
    application = file_application
    directory = tmp_path / "files"
    directory.mkdir()
    for name in ("a.txt", "b.txt", "c.txt", "track10.flac", "track2.flac"):
        (directory / name).write_text(name)
    instance = ShellController(MockBackend(), config=ConfigStore(tmp_path / "config.json"), mock=True)
    instance.mock = False
    instance.data["directory"] = str(directory)
    instance.data["files"] = instance.operations.list_directory(directory)
    instance.setPage("files")
    wait_until(application, lambda: not instance.busy)
    yield instance, application, directory
    instance.close()
    instance.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def test_rename_keeps_focus_on_the_renamed_item(controller):
    instance, application, directory = controller
    instance.select(0)
    instance._execute_option({"action": "rename", "item": instance._items()[0]})
    instance.editText("z.txt")
    instance.dispatch("accept")
    wait_until(application, lambda: not instance.busy)
    assert instance._items()[instance.navigation.index]["path"] == str(directory / "z.txt")


def test_returning_to_files_refreshes_external_changes(controller):
    instance, application, directory = controller
    instance.setPage("home")
    (directory / "external.txt").write_text("new")
    instance.setPage("files")
    wait_until(application, lambda: any(entry["name"] == "external.txt" for entry in instance._items()))


def test_files_search_filters_files_and_never_switches_to_apps(controller):
    instance, application, directory = controller
    instance.dispatch("search")
    instance.editText("track")
    instance.dispatch("accept")
    assert instance.navigation.page == "files"
    assert [entry["name"] for entry in instance._items()] == ["track2.flac", "track10.flac"]


def test_compact_view_omits_file_arrays_without_changing_external_snapshot(controller):
    instance, application, directory = controller
    public = json.loads(instance.snapshotJson)
    compact = json.loads(instance.viewSnapshotJson)
    assert public["items"] == public["files"]
    assert compact["items"] == []
    assert "files" not in compact
    assert compact["fileState"]["count"] == len(public["items"])
    assert instance.fileModel.rowCount() == len(public["items"])
    instance.setPage("home")
    assert "files" not in json.loads(instance.viewSnapshotJson)


def test_bookmarks_and_sort_preferences_survive_other_application_saves(controller):
    instance, application, directory = controller
    stale = ConfigStore(instance.config.path)
    instance.fileAction("bookmark", "")
    instance.fileAction("sort", "size")
    stale.data["focus"]["home"] = 2
    stale.save()
    loaded = ConfigStore(instance.config.path)
    assert str(directory) in loaded.data["fileManager"]["bookmarks"]
    assert loaded.data["fileManager"]["sort"] == "size"


def test_multi_selection_captures_all_paths_and_can_exit_without_changing_clipboard(controller):
    instance, application, directory = controller
    instance.fileAction("selection", "")
    instance.dispatch("accept")
    instance.dispatch("right")
    instance.dispatch("accept")
    instance.fileAction("copy", "")
    assert {Path(path).name for path in instance.clipboard["paths"]} == {"a.txt", "b.txt"}
    instance.dispatch("back")
    assert len(instance.clipboard["paths"]) == 2


def test_batch_keep_both_does_not_overwrite_and_can_run_in_background(controller):
    instance, application, directory = controller
    destination = directory / "destination"
    destination.mkdir()
    (destination / "a.txt").write_text("keep")
    instance.clipboard = {"path": str(directory / "a.txt"), "paths": [str(directory / "a.txt"), str(directory / "b.txt")], "move": False}
    instance._browse(destination)
    wait_until(application, lambda: not instance.busy)
    instance.fileAction("paste-keep", "")
    instance.dispatch("accept")
    instance.setPage("home")
    wait_until(application, lambda: instance.file_task.get("state") in ("completed", "failed"))
    assert instance.file_task["state"] == "completed"
    assert (destination / "a.txt").read_text() == "keep"
    assert (destination / "a (2).txt").read_text() == "a.txt"
    assert (destination / "b.txt").read_text() == "b.txt"
    assert instance.navigation.page == "home"
    assert not instance.busy


def test_grid_and_breadcrumb_navigation_preserve_global_page_switching(controller):
    instance, application, directory = controller
    instance.dispatch("left")
    assert instance.navigation.index == 0
    assert instance.file_section == "list"
    instance.dispatch("right")
    assert instance.navigation.index == 1
    instance.dispatch("up")
    assert json.loads(instance.viewSnapshotJson)["fileState"]["section"] == "breadcrumbs"
    instance.dispatch("previous-page")
    assert instance.navigation.page == "windows"


def test_empty_selection_never_falls_back_to_current_item(controller):
    instance, application, directory = controller
    instance.fileAction("selection", "")
    assert instance._file_selected() == []
    instance.fileAction("copy", "")
    instance.fileAction("trash", "")
    assert instance.clipboard is None
    assert not instance.modal


def test_filter_clears_hidden_marks_and_keeps_counts_consistent(controller):
    instance, application, directory = controller
    instance.fileAction("select-all", "")
    instance.fileAction("filter", "audio")
    selected = instance._file_selected()
    assert {entry["name"] for entry in selected} == {"track2.flac", "track10.flac"}
    assert len(instance.file_marked) == len(selected) == 2


def test_background_errors_do_not_open_a_modal_or_steal_focus(controller):
    instance, application, directory = controller
    instance.setPage("home")
    instance.file_task = {"id": "background", "action": "copy", "directory": str(directory), "state": "running"}
    instance._file_job_finished(("background", {"state": "failed", "phase": "finished", "completed": [], "skipped": [],
                                              "errors": [{"path": str(directory / "gone"), "reason": "missing"}]}))
    assert not instance.modal
    assert instance.navigation.page == "home"
    instance.fileAction("task", "")
    assert instance.modal["kind"] == "menu"
    assert instance.modal["options"][0]["subtitle"] == "missing"


def test_finishing_move_never_consumes_a_new_clipboard(controller):
    instance, application, directory = controller
    source = str(directory / "a.txt")
    instance._file_job_clipboard = {"path": source, "paths": [source], "move": True}
    instance.clipboard = {"path": source, "paths": [source], "move": True}
    instance.setPage("home")
    instance.file_task = {"id": "move", "action": "move", "directory": str(directory), "state": "running"}
    instance._file_job_finished(("move", {"state": "completed", "phase": "finished", "completed": [{"source": source}],
                                        "skipped": [], "errors": []}))
    assert instance.clipboard["paths"] == [source]


def test_refresh_does_not_leave_breadcrumb_focus(controller):
    instance, application, directory = controller
    instance.dispatch("up")
    instance._refresh_files()
    wait_until(application, lambda: not instance.busy)
    assert instance.file_section == "breadcrumbs"


def test_mock_rename_changes_identity_and_preserves_focus(tmp_path, file_application):
    instance = ShellController(MockBackend(), config=ConfigStore(tmp_path / "mock.json"), mock=True)
    try:
        instance.setPage("files")
        instance.select(0)
        old_path = instance._file_current()["path"]
        instance.fileAction("rename", "")
        instance.editText("renamed")
        instance.dispatch("accept")
        item = instance._file_current()
        assert item["name"] == "renamed"
        assert item["path"] == item["id"] == str(Path(old_path).with_name("renamed"))
        assert instance.fileModel.entries[instance.navigation.index]["name"] == "renamed"
    finally:
        instance.close()
        instance.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def test_conflict_replacement_requires_an_extra_confirmation_and_preserves_folders(controller):
    instance, application, directory = controller
    source = directory / "a.txt"
    instance.clipboard = {"path": str(source), "paths": [str(source)], "move": False}
    instance.fileAction("paste", "")
    assert instance.modal["title"] == "Name conflicts"
    replace_index = next(index for index, entry in enumerate(instance.modal["options"]) if entry.get("command") == "confirm-replace")
    instance.chooseModal(replace_index)
    assert instance.modal["kind"] == "confirm" and instance.modal["index"] == 0
    instance.dispatch("accept")
    assert not instance.file_task
    folder = directory / "folder"
    folder.mkdir()
    instance.clipboard = {"path": str(folder), "paths": [str(folder)], "move": False}
    instance.fileAction("paste", "")
    assert not any(entry.get("command") == "confirm-replace" for entry in instance.modal["options"])
    assert source.read_text() == "a.txt" and folder.is_dir()


def test_open_with_default_uses_the_system_handler_even_for_a_folder(controller, monkeypatch):
    instance, application, directory = controller
    opened = []
    monkeypatch.setattr(instance.operations, "open", lambda path: opened.append(path))
    instance._file_open_with({"path": str(directory), "name": directory.name, "directory": True, "mime": "inode/directory"})
    instance.chooseModal(0)
    wait_until(application, lambda: not instance.busy)
    assert opened == [str(directory)]


def test_busy_scan_discards_stale_results_and_opens_the_latest_requested_folder(controller, monkeypatch):
    instance, application, directory = controller
    first, second = directory / "first", directory / "second"
    first.mkdir()
    second.mkdir()
    (second / "latest.txt").write_text("latest")
    started, release = threading.Event(), threading.Event()
    read = instance.operations.list_directory

    def delayed(path, hidden=False):
        if Path(path) == first:
            started.set()
            assert release.wait(5)
        return read(path, hidden)

    monkeypatch.setattr(instance.operations, "list_directory", delayed)
    instance._browse(first)
    assert started.wait(5)
    instance._browse(second)
    release.set()
    wait_until(application, lambda: not instance.busy and instance.data["directory"] == str(second))
    assert [entry["name"] for entry in instance.data["files"]] == ["latest.txt"]


def test_selected_file_watcher_refreshes_metadata_without_losing_focus(controller):
    instance, application, directory = controller
    instance.select(1)
    selected = instance._file_current()["path"]
    Path(selected).write_bytes(b"changed" * 100)
    wait_until(application, lambda: any(entry["path"] == selected and entry["size"] == 700 for entry in instance.data["files"]))
    assert instance._file_current()["path"] == selected


def test_trash_location_restores_a_selected_item_via_a_real_background_job(controller):
    instance, application, directory = controller
    original = directory / "restored.txt"
    root = make_trash(directory, original)
    instance.trash_store = TrashStore(roots=[{"path": str(root), "top": str(directory), "home": True}])
    instance._browse("trash:///")
    wait_until(application, lambda: not instance.busy)
    assert instance._file_current()["trash"]
    instance.fileAction("restore", "")
    instance.chooseModal(1)
    instance.dispatch("accept")
    wait_until(application, lambda: instance.file_task.get("state") in ("completed", "failed"))
    assert instance.file_task["state"] == "completed"
    assert original.read_text() == "recovered content"
    assert instance.trash_store.entries() == []


def test_unmount_is_blocked_while_a_transfer_uses_the_device(controller):
    instance, application, directory = controller
    instance.file_task = {"id": "busy", "state": "running", "sources": [str(directory / "a.txt")], "directory": ""}
    with pytest.raises(ValueError, match="file task"):
        instance._file_unmount({"path": str(directory)})


def test_leaving_an_unmounted_location_clears_its_search_and_selection(controller, monkeypatch):
    instance, application, directory = controller
    instance.file_query = "a"
    instance.file_selection = True
    instance.file_marked = {instance._file_current()["id"]}
    monkeypatch.setattr(instance, "_run", lambda *arguments, **options: None)
    instance._file_unmount({"path": str(directory)})
    assert instance.data["directory"] == str(Path.home())
    assert instance.file_query == ""
    assert not instance.file_marked and not instance.file_selection


def test_opening_the_current_location_enters_the_list_but_refresh_does_not(controller):
    instance, application, directory = controller
    instance._file_places_base = [{"path": str(directory), "name": "Current folder", "id": "current"}]
    instance.dispatch("up")
    instance.fileAction("locations", "")
    instance.dispatch("accept")
    wait_until(application, lambda: not instance.busy)
    assert instance.file_section == "list"


@pytest.mark.parametrize("columns, start, action, target", [
    (4, 0, "left", 0), (4, 0, "right", 1), (4, 3, "right", 3),
    (4, 1, "down", 5), (4, 5, "up", 1), (4, 7, "down", 10),
    (4, 10, "right", 10), (4, 10, "down", 10),
    (5, 4, "right", 4), (5, 4, "down", 9), (5, 9, "down", 10),
])
def test_icon_grid_navigation_moves_rows_and_stops_at_edges(controller, columns, start, action, target):
    instance, application, directory = controller
    for index in range(6):
        (directory / f"extra{index}.txt").write_text("grid")
    instance._browse(directory)
    wait_until(application, lambda: not instance.busy)
    instance.setFileGridColumns(columns)
    instance.select(start)
    instance.dispatch(action)
    assert instance.navigation.index == target
    assert instance.file_section == "list"


def test_grid_resize_preserves_current_file_and_marks(controller):
    instance, application, directory = controller
    instance.setFileGridColumns(4)
    instance.select(3)
    instance.fileAction("mark", "")
    selected = instance._file_current()["id"]
    instance.setFileGridColumns(5)
    assert instance._file_current()["id"] == selected
    assert instance.file_marked == {selected}
    instance.dispatch("right")
    assert instance.navigation.index == 4


def test_locations_menu_keeps_bookmarks_trash_and_unmount_reachable(controller):
    instance, application, directory = controller
    instance.fileAction("bookmark", "")
    instance._file_places_base.append({"id": "usb", "path": "/media/demo/USB", "name": "USB",
                                      "details": "12 GiB free", "mount": True})
    instance.dispatch("context")
    assert instance.modal["options"][0]["command"] == "locations"
    instance.dispatch("accept")
    locations = instance.modal["options"]
    assert any(option.get("value") == str(directory) for option in locations)
    assert any(option.get("value") == "trash:///" for option in locations)
    assert any(option.get("subtitle") == "12 GiB free · /media/demo/USB" for option in locations)
    for _step in range(len(locations) - 1):
        instance.dispatch("down")
    instance.dispatch("accept")
    assert len(instance.modal["options"]) == 1
    assert instance.modal["options"][0]["place"]["id"] == "usb"
    instance.dispatch("accept")
    assert instance.modal["kind"] == "confirm"
    assert instance.modal["option"]["command"] == "unmount-confirm"


def test_compact_bulk_confirmation_keeps_operation_payload_out_of_qml(controller):
    instance, application, directory = controller
    instance.data["files"] = [{"id": str(directory / str(index)), "path": str(directory / str(index)),
                               "name": str(index), "directory": False} for index in range(1000)]
    instance._publish()
    instance.fileAction("select-all", "")
    instance.fileAction("trash", "")
    public = json.loads(instance.snapshotJson)
    compact = json.loads(instance.viewSnapshotJson)
    assert len(public["modal"]["option"]["items"]) == 1000
    assert "option" not in compact["modal"] and "items" not in compact["modal"]
    assert len(instance.viewSnapshotJson.encode()) < 30000


def test_user_requested_file_jobs_report_their_actual_completion_sound(controller):
    instance, application, directory = controller
    destination = directory / "destination"
    destination.mkdir()
    source = str(directory / "a.txt")
    instance.clipboard = {"path": source, "paths": [source], "move": False}
    instance._browse(destination)
    wait_until(application, lambda: not instance.busy)
    events = []
    instance.soundRequested.connect(events.append)
    instance.fileAction("paste", "")
    instance.dispatch("accept")
    wait_until(application, lambda: not instance._file_active())
    assert instance.file_task["state"] == "completed"
    assert events[-1] == "success"
