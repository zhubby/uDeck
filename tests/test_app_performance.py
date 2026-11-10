import importlib
import json
import os
import shutil
import subprocess
import sys
import threading

import pytest
from PySide6.QtCore import QCoreApplication

from udeck.apps.common.controller import AppController
from udeck.apps.common.state import AppState


@pytest.mark.parametrize('app', ['reader', 'terminal'])
def test_launch_forwarding_and_shell_requests_use_independent_dbus_service(tmp_path, app):
    if sys.platform != 'linux' or not shutil.which('dbus-run-session'):
        pytest.skip('Requires a Linux session bus')
    result = subprocess.run(['dbus-run-session', '--', sys.executable, 'tests/app_forwarding_probe.py', app],
                            env={**os.environ, 'PYTHONPATH': 'src'}, capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize('format', ['pdf', 'text'])
def test_reader_content_surface_is_deferred_and_retained_after_first_use(format):
    result = subprocess.run([sys.executable, 'tests/app_lazy_surface_probe.py', format],
                            env={**os.environ, 'PYTHONPATH': 'src', 'QT_QPA_PLATFORM': 'offscreen',
                                 'QT_QUICK_BACKEND': 'software', 'QTWEBENGINE_DISABLE_SANDBOX': '1'},
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("module", ["udeck.apps.main", "udeck.terminal.main"])
def test_launch_entry_can_be_loaded_without_graphical_or_media_libraries(module):
    result = subprocess.run([sys.executable, "-c", f"""
import importlib, sys
importlib.import_module({module!r})
assert not any(name in sys.modules for name in (
    'PySide6.QtGui', 'PySide6.QtQuick', 'PySide6.QtQml',
    'PySide6.QtWidgets', 'PySide6.QtMultimedia', 'PySide6.QtWebEngineQuick'))
"""], env={**os.environ, "PYTHONPATH": "src"}, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_selection_and_progress_updates_do_not_rebuild_or_serialize_the_library(tmp_path):
    application = QCoreApplication.instance() or QCoreApplication([])
    controller = AppController("reader", tmp_path, tmp_path / "settings.json")
    controller.library.items = [{"id": str(i), "sourceId": "books", "title": f"Book {i}",
                                 "format": "PDF", "folder": "/books"} for i in range(10000)]
    try:
        controller.publish()
        model = controller.cardModel
        assert model.rowCount() == 10000
        resets = []
        model.modelReset.connect(lambda: resets.append(True))
        original_rows = controller.rows
        controller.rows = lambda: pytest.fail("Unchanged collection rebuilt during selection")
        controller.select("9999")
        compact = json.loads(controller.viewSnapshotJson)
        assert "cards" not in compact and len(controller.viewSnapshotJson) < 2048
        assert controller.selectedIndex == 9999
        assert controller.selectedItem["title"] == "Book 9999"
        assert not resets
        controller.rows = original_rows
        controller.library.items = controller.library.items[:-1]
        controller.library.changed.emit()
        assert controller.selectedIndex == 9998
        assert controller.selectedItem["title"] == "Book 9998"
        assert len(resets) == 1
        assert application
    finally:
        controller.close()


def test_repeated_queue_tracks_keep_the_original_first_match_selection(tmp_path):
    application = QCoreApplication.instance() or QCoreApplication([])
    controller = AppController('music', tmp_path, tmp_path / 'settings.json')
    rows = [{'id': identifier, 'title': identifier} for identifier in ('track-a', 'track-b', 'track-a')]
    controller.rows = lambda: rows
    try:
        controller.publish()
        controller.select('track-a')
        assert controller.cardModel.rowCount() == 3
        assert controller.selectedIndex == 0
        assert application
    finally:
        controller.close()


def test_background_save_keeps_ui_free_and_flushes_latest_state_without_rewriting_index(tmp_path, monkeypatch):
    state = AppState("music", tmp_path)
    state.data["index"] = [{"id": "track", "title": "Original"}]
    state.data["positions"]["track"] = 12
    entered, release = threading.Event(), threading.Event()
    real_fsync = os.fsync

    def delayed_fsync(fd):
        entered.set()
        assert release.wait(3)
        return real_fsync(fd)

    monkeypatch.setattr("udeck.apps.common.state.os.fsync", delayed_fsync)
    try:
        state.save_async()
        assert entered.wait(2)
        state.data["positions"]["track"] = 18
        state.save_async()
    finally:
        release.set()
    state.flush()
    index = tmp_path / "music.index.json"
    before = index.stat().st_mtime_ns
    state.data["positions"]["track"] = 24
    state.save_async()
    state.close()
    assert index.stat().st_mtime_ns == before
    assert "index" not in json.loads(state.path.read_text())
    restored = AppState("music", tmp_path)
    assert restored.data["positions"] == {"track": 24}
    assert restored.data["index"] == [{"id": "track", "title": "Original"}]


def test_legacy_index_migrates_only_after_successful_atomic_save(tmp_path, monkeypatch):
    path = tmp_path / "reader.json"
    path.write_text(json.dumps({"version": 1, "index": [{"id": "book"}], "positions": {"book": 9}}))
    original = path.read_bytes()
    state = AppState("reader", tmp_path)
    replace = os.replace

    def fail_runtime(source, destination):
        if destination == state.path:
            raise OSError("storage full")
        return replace(source, destination)

    monkeypatch.setattr("udeck.apps.common.state.os.replace", fail_runtime)
    state.save_async()
    with pytest.raises(OSError, match="storage full"):
        state.flush()
    assert path.read_bytes() == original
    assert AppState("reader", tmp_path).data["index"] == [{"id": "book"}]
    monkeypatch.setattr("udeck.apps.common.state.os.replace", replace)
    state.save_async()
    state.close()
    assert AppState("reader", tmp_path).data["positions"] == {"book": 9}


def test_index_edits_survive_sync_save_and_explicit_background_replacement(tmp_path):
    state = AppState('reader', tmp_path)
    state.data['index'] = [{'id': 'book', 'title': 'Before'}]
    state.save()
    state.data['index'][0]['title'] = 'Edited in place'
    state.save()
    assert AppState('reader', tmp_path).data['index'][0]['title'] == 'Edited in place'
    state = AppState('reader', tmp_path, background=True)
    state.data['index'][0]['title'] = 'Updated scan'
    state.set_index(state.data['index'])
    state.save()
    state.close()
    assert AppState('reader', tmp_path).data['index'][0]['title'] == 'Updated scan'


def test_background_writer_recovers_after_serialization_and_error_callback_failure(tmp_path):
    state = AppState('music', tmp_path, background=True)

    def failed_notification(_error):
        raise RuntimeError('notification receiver unavailable')

    state.on_error = failed_notification
    state.data['positions']['track'] = object()
    state.save().result(timeout=2)
    with pytest.raises(TypeError):
        state.flush()
    state.data['positions']['track'] = 42
    state.save().result(timeout=2)
    state.close()
    assert AppState('music', tmp_path).data['positions']['track'] == 42


def test_save_failure_reaches_controller_only_through_gui_event_loop(tmp_path, monkeypatch):
    application = QCoreApplication.instance() or QCoreApplication([])
    controller = AppController('reader', tmp_path, tmp_path / 'settings.json')
    real_fsync = os.fsync

    def failed_fsync(_fd):
        raise OSError('Storage unavailable')

    try:
        monkeypatch.setattr('udeck.apps.common.state.os.fsync', failed_fsync)
        controller.persist()
        with pytest.raises(OSError, match='Storage unavailable'):
            controller.store.flush()
        assert controller.error == ''
        application.processEvents()
        assert 'Storage unavailable' in str(controller.error)
    finally:
        monkeypatch.setattr('udeck.apps.common.state.os.fsync', real_fsync)
        controller.close()


def test_corrupt_split_index_is_preserved_without_losing_playback_state(tmp_path):
    state = AppState('reader', tmp_path)
    state.data['positions']['book'] = {'fraction': .5}
    state.save()
    state.index_path.write_bytes(b'{truncated index')
    recovered = AppState('reader', tmp_path)
    assert recovered.data['positions'] == {'book': {'fraction': .5}}
    recovered.set_index([{'id': 'rescanned'}])
    recovered.save()
    assert state.index_path.with_suffix('.recovery.json').read_bytes() == b'{truncated index'
    assert AppState('reader', tmp_path).data['index'] == [{'id': 'rescanned'}]


def test_startup_trace_retains_first_frame_and_distinguishes_activation_generations():
    trace_class = importlib.import_module("udeck.performance").StartupTrace
    now = [10.0]
    trace = trace_class(started=9.0, clock=lambda: now[0])
    trace.mark("runtimeImported")
    now[0] = 10.2
    trace.mark("firstFrame")
    now[0] = 10.3
    trace.mark("firstFrame")
    trace.request_activation()
    now[0] = 10.35
    trace.active_changed(True)
    trace.frame_swapped()
    report = trace.snapshot()
    assert report["stages"]["firstFrame"] == pytest.approx(1.2)
    assert report["activation"]["toActiveMs"] == pytest.approx(50)
    assert report["activation"]["toFrameMs"] == pytest.approx(50)
    trace.request_activation()
    assert trace.snapshot()["activation"]["generation"] == 2
    assert trace.snapshot()["activation"]["toFrameMs"] is None
