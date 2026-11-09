import threading

from udeck.file_jobs import FileJob, distinct_sources
from udeck.files import FileOperations


def test_batch_preparation_reports_missing_item_but_copies_other_sources(tmp_path):
    source = tmp_path / "valid.txt"
    source.write_text("valid")
    destination = tmp_path / "destination"
    destination.mkdir()
    result = FileJob(FileOperations(), "copy", [str(tmp_path / "missing"), str(source)], str(destination),
                     threading.Event(), lambda update: None).run()
    assert result["state"] == "failed"
    assert result["completedItems"] == 1
    assert (destination / source.name).read_text() == "valid"
    assert len(result["errors"]) == 1


def test_cancellation_keeps_finished_items_sources_and_no_staging_files(tmp_path):
    sources = [tmp_path / "first", tmp_path / "second"]
    for path in sources:
        path.write_bytes(b"x" * (2 * 1024 * 1024))
    destination = tmp_path / "destination"
    destination.mkdir()
    cancelled = threading.Event()

    def progress(update):
        if update["completedItems"] == 1:
            cancelled.set()

    result = FileJob(FileOperations(), "copy", [str(path) for path in sources], str(destination), cancelled, progress).run()
    assert result["state"] == "cancelled"
    assert result["completedItems"] == 1
    assert (destination / "first").read_bytes() == sources[0].read_bytes()
    assert not (destination / "second").exists()
    assert all(path.exists() for path in sources)
    assert not list(destination.glob(".udeck-transfer-*"))


def test_skip_progress_and_same_filesystem_move_are_accurate(tmp_path):
    sources = [tmp_path / "skip", tmp_path / "move"]
    for path in sources:
        path.write_bytes(b"abc")
    destination = tmp_path / "destination"
    destination.mkdir()
    (destination / "skip").write_text("keep")
    result = FileJob(FileOperations(), "move", [str(path) for path in sources], str(destination),
                     threading.Event(), lambda update: None, policy="skip").run()
    assert result["state"] == "completed"
    assert result["doneBytes"] == result["totalBytes"] == 3
    assert result["doneFiles"] == result["totalFiles"] == 1
    assert result["skippedItems"] == 1
    assert (destination / "skip").read_text() == "keep"
    assert sources[0].exists() and not sources[1].exists()


def test_distinct_sources_removes_nested_items_without_following_symlinks(tmp_path):
    directory = tmp_path / "folder"
    directory.mkdir()
    child = directory / "file"
    child.touch()
    alias = tmp_path / "alias"
    alias.symlink_to(directory, target_is_directory=True)
    assert distinct_sources([child, directory, alias]) == [str(directory), str(alias)]
    assert distinct_sources([alias, alias / "file"]) == [str(alias), str(alias / "file")]


def test_cancelling_in_the_middle_of_a_file_removes_only_its_staging_copy(tmp_path):
    source = tmp_path / "source"
    source.write_bytes(b"content" * 1024 * 1024)
    destination = tmp_path / "destination"
    destination.mkdir()
    cancelled = threading.Event()

    class CancellingOperations(FileOperations):
        def transfer(self, *arguments, progress=None, **options):
            def update(value):
                progress(value)
                cancelled.set()
            return super().transfer(*arguments, progress=update, **options)

    result = FileJob(CancellingOperations(), "copy", [str(source)], str(destination), cancelled, lambda update: None).run()
    assert result["state"] == "cancelled"
    assert result["completedItems"] == 0
    assert list(destination.iterdir()) == []
    assert source.stat().st_size == 7 * 1024 * 1024
