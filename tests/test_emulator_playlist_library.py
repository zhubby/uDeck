"""
[INPUT]: 依赖真实列表、封面目录和 Qt 工作线程。
[OUTPUT]: 验证列表保留、封面后台解析和过期结果隔离。
[POS]: EmulatorLibrary 的数据发布与持久化边界回归。
[PROTOCOL]: Update this header on change, then check AGENTS.md
"""

import json
import os
import threading
import time
from pathlib import Path

import pytest
from PySide6.QtCore import QCoreApplication
from PySide6.QtTest import QTest
from test_emulator_playlists import entry, write_playlist
from test_games_catalog import installed

from udeck.apps.common.state import AppState
from udeck.apps.emulator.library import EmulatorLibrary


@pytest.fixture
def application():
    return QCoreApplication.instance() or QCoreApplication([])


def refresh(library):
    library.refresh()
    deadline = time.monotonic() + 5
    while library.pending and time.monotonic() < deadline:
        QTest.qWait(10)
    assert not library.pending


def test_refresh_never_scans_unlisted_roms_and_keeps_missing_list_entries(application, tmp_path):
    root = tmp_path / "roms/Nintendo - Game Boy"
    root.mkdir(parents=True)
    (root / "Unlisted.gb").write_bytes(b"original")
    lists = tmp_path / "playlists"
    write_playlist(lists / "Favorites.lpl", [entry(root / "Missing.gb")])
    state = AppState("emulator", tmp_path / "state")
    state.data["preferences"].update(romRoot=str(root.parent), playlistDirectory=str(lists), emulatorSchema=3)
    library = EmulatorLibrary(state, installed(tmp_path, {}))
    try:
        refresh(library)
        assert len(library.items) == 1 and library.items[0]["path"].endswith("Missing.gb")
        assert library.items[0]["contentError"]
        assert library.playlists[0]["title"] == "Favorites"
    finally:
        library.close()
        state.close()


def test_refresh_keeps_last_good_collection_when_its_json_becomes_invalid(application, tmp_path):
    game = tmp_path / "roms/Original.gb"
    game.parent.mkdir()
    game.write_bytes(b"original")
    path = write_playlist(tmp_path / "playlists/Custom.lpl", [entry(game)])
    state = AppState("emulator", tmp_path / "state")
    state.data["preferences"].update(romRoot=str(game.parent), playlistDirectory=str(path.parent), emulatorSchema=3)
    library = EmulatorLibrary(state, installed(tmp_path, {}))
    try:
        refresh(library)
        identity = library.items[0]["id"]
        path.write_text("broken")
        refresh(library)
        assert library.items[0]["id"] == identity
        assert library.playlists[0]["error"]
    finally:
        library.close()
        state.close()


def test_corrupt_identity_registry_blocks_refresh_and_preserves_the_file(application, tmp_path):
    state = AppState("emulator", tmp_path / "state")
    state.path.parent.mkdir(parents=True)
    registry = state.path.parent / "emulator-identities.json"
    registry.write_text("{broken registry")
    library = EmulatorLibrary(state, installed(tmp_path, {}))
    try:
        refresh(library)
        assert library.errors and "emulator-identities.json" in str(library.errors)
        assert registry.read_text() == "{broken registry"
    finally:
        library.close()
        state.close()


def thumbnail_library(tmp_path):
    root = tmp_path / 'roms/Nintendo - Game Boy'
    root.mkdir(parents=True)
    game = root / 'Original.gb'
    game.write_bytes(b'original')
    playlist = write_playlist(tmp_path / 'playlists/Custom.lpl', [entry(game)])
    state = AppState('emulator', tmp_path / 'state')
    state.data['preferences'].update(romRoot=str(root.parent), playlistDirectory=str(playlist.parent),
                                     thumbnailDirectory=str(tmp_path / 'thumbnails'), emulatorSchema=3)
    library = EmulatorLibrary(state, installed(tmp_path, {}))
    boxart = tmp_path / 'thumbnails/Nintendo - Game Boy/Named_Boxarts/Original.png'
    boxart.parent.mkdir(parents=True)
    boxart.write_bytes(b'boxart')
    return library, state, game, playlist, boxart


def wait_for(predicate):
    deadline = time.monotonic() + 5
    while not predicate() and time.monotonic() < deadline:
        QTest.qWait(10)
    assert predicate()


def test_playlist_thumbnail_probes_run_outside_the_gui_thread(application, tmp_path, monkeypatch):
    library, state, _, _, boxart = thumbnail_library(tmp_path)
    root = tmp_path / 'thumbnails'
    gui_thread, probe_threads = threading.get_ident(), []
    original_stat, original_scandir = os.stat, os.scandir

    def stat(path, *args, **kwargs):
        if isinstance(path, (str, bytes, os.PathLike)) and Path(path).is_relative_to(root):
            probe_threads.append(threading.get_ident())
        return original_stat(path, *args, **kwargs)

    def scandir(path):
        if Path(path).is_relative_to(root):
            probe_threads.append(threading.get_ident())
        return original_scandir(path)

    monkeypatch.setattr(os, 'stat', stat)
    monkeypatch.setattr(os, 'scandir', scandir)
    try:
        refresh(library)
        assert library.items[0]['cover'] == boxart.as_uri()
        assert probe_threads and gui_thread not in probe_threads
    finally:
        library.close()
        state.close()


def block_first_thumbnail(monkeypatch):
    from udeck.apps.emulator import thumbnails

    entered, release = threading.Event(), threading.Event()
    original = thumbnails.find_thumbnails

    def find(*args, **kwargs):
        if not entered.is_set():
            entered.set()
            assert release.wait(5), 'The test must release the thumbnail worker'
        return original(*args, **kwargs)

    monkeypatch.setattr(thumbnails, 'find_thumbnails', find)
    return entered, release


def test_cancelled_thumbnail_scan_never_publishes_or_saves_its_old_entries(application, tmp_path, monkeypatch):
    library, state, game, playlist, _ = thumbnail_library(tmp_path)
    replacement = game.with_name('Replacement.gb')
    replacement.write_bytes(b'replacement')
    entered, release = block_first_thumbnail(monkeypatch)
    try:
        library.refresh()
        wait_for(entered.is_set)
        write_playlist(playlist, [entry(replacement)])
        library.refresh()
        wait_for(lambda: not library.pending)
        release.set()
        wait_for(lambda: not library.tasks)
        assert [item['path'] for item in library.items] == [str(replacement)]
        assert [item['path'] for item in state.data['index']] == [str(replacement)]
        persisted = json.loads(library.identities.path.read_text())['identities']
        assert all('Original.gb' not in key for key in persisted)
        assert any('Replacement.gb' in key for key in persisted)
    finally:
        release.set()
        library.close()
        state.close()


def test_thumbnail_scan_publishes_the_latest_preferred_kind(application, tmp_path, monkeypatch):
    library, state, _, _, boxart = thumbnail_library(tmp_path)
    snap = boxart.parent.parent / 'Named_Snaps/Original.png'
    snap.parent.mkdir()
    snap.write_bytes(b'snap')
    entered, release = block_first_thumbnail(monkeypatch)
    try:
        library.refresh()
        wait_for(entered.is_set)
        state.data['preferences']['thumbnailType'] = 'Named_Snaps'
        release.set()
        wait_for(lambda: not library.pending)
        assert library.items[0]['cover'] == snap.as_uri()
    finally:
        release.set()
        library.close()
        state.close()


def block_completed_thumbnail_snapshot(monkeypatch):
    from udeck.apps.emulator import thumbnails

    entered, release = threading.Event(), threading.Event()
    original = thumbnails.apply_library_thumbnails
    gui_thread = threading.get_ident()
    scans = []

    def apply(*args, **kwargs):
        result = original(*args, **kwargs)
        if threading.get_ident() != gui_thread:
            scans.append(True)
            if not entered.is_set():
                entered.set()
                assert release.wait(5), 'The test must release the completed thumbnail snapshot'
        return result

    monkeypatch.setattr(thumbnails, 'apply_library_thumbnails', apply)
    return entered, release, scans


def test_refresh_cannot_overwrite_a_cover_reloaded_after_its_snapshot(application, tmp_path, monkeypatch):
    library, state, _, _, boxart = thumbnail_library(tmp_path)
    boxart.unlink()
    refresh(library)
    assert library.items[0]['cover'] == ''
    entered, release, _ = block_completed_thumbnail_snapshot(monkeypatch)
    try:
        library.refresh()
        wait_for(entered.is_set)
        boxart.write_bytes(b'new download')
        library.reload_thumbnails()
        assert library.items[0]['cover'] == boxart.as_uri()
        release.set()
        wait_for(lambda: not library.pending and not library.tasks)
        assert library.items[0]['cover'] == boxart.as_uri()
        assert state.data['index'][0]['cover'] == boxart.as_uri()
    finally:
        release.set()
        library.close()
        state.close()


def test_close_prevents_a_stale_thumbnail_snapshot_from_restarting_refresh(application, tmp_path, monkeypatch):
    library, state, _, _, boxart = thumbnail_library(tmp_path)
    boxart.unlink()
    refresh(library)
    entered, release, scans = block_completed_thumbnail_snapshot(monkeypatch)
    try:
        library.refresh()
        wait_for(entered.is_set)
        boxart.write_bytes(b'new download')
        library.reload_thumbnails()
        library.close()
        release.set()
        wait_for(lambda: not library.tasks)
        QTest.qWait(30)
        assert len(scans) == 1
        assert library.items[0]['cover'] == boxart.as_uri()
    finally:
        release.set()
        library.close()
        state.close()
