"""Journalled relocation preserves original bytes, identities, and native saves."""

import errno
import json
import zipfile
from pathlib import Path

import pytest
from test_games_catalog import installed

from udeck.apps.common.library import Source
from udeck.apps.common.state import AppState
from udeck.apps.emulator.library import scan_games


def legacy_library(tmp_path):
    root = tmp_path / "Legacy"
    (root / "gb/subfolder").mkdir(parents=True)
    (root / "gb/subfolder/Original.gb").write_bytes(b"original game")
    (root / "gb/subfolder/Readme.txt").write_bytes(b"keep this resource")
    catalog = installed(tmp_path, {"gambatte": {"supported_extensions": "gb|gbc"}})
    item = scan_games(Source.create(root), catalog).items[0]
    state = AppState("emulator", tmp_path / "state")
    state.data.update(index=[item], favorites=[item["id"]], recent=[item["id"]],
                      positions={item["id"]: {"seconds": 42}})
    state.data["preferences"].update(romRoot=str(root), emulatorSchema=2,
                                      gameCores={item["id"]: "gambatte"})
    state.save()
    save = state.path.parent / "emulator-saves" / item["id"] / "cores/gambatte/sram/Original.srm"
    save.parent.mkdir(parents=True)
    save.write_bytes(b"native SRAM")
    return root, catalog, item, state, save


def test_migration_moves_sidecars_and_preserves_game_records_and_save_bytes(tmp_path):
    from udeck.apps.emulator.controller import CoreSaveStore, content_hash
    from udeck.apps.emulator.migration import MigrationTransaction, plan_migration
    from udeck.apps.emulator.playlists import ContentIdentities, read_library

    root, catalog, item, state, save = legacy_library(tmp_path)
    serialized = tmp_path / "native.state"
    serialized.write_bytes(b"native instant save")
    saved = CoreSaveStore(state.path.parent / "emulator-saves" / item["id"], "gambatte", "a" * 64)
    saved.publish("auto", serialized, {"contentHash": content_hash(item), "coreHash": "a" * 64})
    plan = plan_migration(root, tmp_path / "Games", catalog, [item])
    assert not plan.issues and not plan.choices
    assert Path(item["path"]).is_file()
    transaction = MigrationTransaction(state.path.parent / "emulator-migration.json")
    transaction.execute(plan, state)
    target = tmp_path / "Games/roms/Nintendo - Game Boy/subfolder/Original.gb"
    assert target.read_bytes() == b"original game" and not Path(item["path"]).exists()
    assert target.with_name("Readme.txt").read_bytes() == b"keep this resource"
    assert save.read_bytes() == b"native SRAM"
    assert state.data["favorites"] == [item["id"]] and state.data["recent"] == [item["id"]]
    assert state.data["positions"][item["id"]]["seconds"] == 42
    identities = ContentIdentities(state.path.parent / "emulator-identities.json")
    result = read_library(tmp_path / "Games/playlists", target.parents[2], catalog, identities)
    assert result.items[0]["id"] == item["id"]
    assert result.items[0]["playlistCoreId"] == "gambatte"
    assert saved.load("auto", content_hash(result.items[0]), "a" * 64)[0].read_bytes() == b"native instant save"
    assert state.data["preferences"]["emulatorSchema"] == 3


def test_preflight_refuses_conflicts_without_moving_anything(tmp_path):
    from udeck.apps.emulator.migration import plan_migration

    root, catalog, item, _, _ = legacy_library(tmp_path)
    target = tmp_path / "Games/roms/Nintendo - Game Boy/subfolder/Original.gb"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"other game")
    plan = plan_migration(root, tmp_path / "Games", catalog, [item])
    assert plan.issues and Path(item["path"]).read_bytes() == b"original game"
    assert target.read_bytes() == b"other game"


def test_ambiguous_combined_platform_requires_explicit_mapping(tmp_path):
    from udeck.apps.emulator.migration import plan_migration

    root = tmp_path / "Legacy"
    (root / "gamecube").mkdir(parents=True)
    (root / "gamecube/Original.iso").write_bytes(b"disc")
    catalog = installed(tmp_path, {"dolphin": {"supported_extensions": "iso"}})
    plan = plan_migration(root, tmp_path / "Games", catalog, [])
    assert str(root / "gamecube") in plan.choices
    plan = plan_migration(root, tmp_path / "Games", catalog, [],
                          mappings={str(root / "gamecube"): "Nintendo - Wii"})
    assert not plan.choices and not plan.issues
    assert plan.moves[0]["target"].endswith("Nintendo - Wii/Original.iso")


def test_missing_disc_dependency_stops_preflight(tmp_path):
    from udeck.apps.emulator.migration import plan_migration

    root = tmp_path / "Legacy"
    (root / "ps1").mkdir(parents=True)
    (root / "ps1/Game.cue").write_text('FILE "missing.bin" BINARY\n')
    catalog = installed(tmp_path, {"pcsx_rearmed": {"supported_extensions": "cue|bin"}})
    plan = plan_migration(root, tmp_path / "Games", catalog, [])
    assert plan.issues
    assert (root / "ps1/Game.cue").exists()


def test_failure_rolls_back_files_and_configuration(tmp_path, monkeypatch):
    from udeck.apps.emulator.migration import MigrationTransaction, plan_migration

    root, catalog, item, state, save = legacy_library(tmp_path)
    before = state.path.read_bytes()
    plan = plan_migration(root, tmp_path / "Games", catalog, [item])
    transaction = MigrationTransaction(state.path.parent / "emulator-migration.json")
    original = transaction._transfer
    calls = []

    def fail_second(move):
        calls.append(move)
        if len(calls) == 2:
            raise OSError("injected disk failure")
        return original(move)

    monkeypatch.setattr(transaction, "_transfer", fail_second)
    with pytest.raises(OSError, match="disk failure"):
        transaction.execute(plan, state)
    assert Path(item["path"]).read_bytes() == b"original game"
    assert state.path.read_bytes() == before and save.read_bytes() == b"native SRAM"
    assert not list((tmp_path / "Games/roms").rglob("Original.gb"))


def test_interrupted_move_recovers_even_before_completion_is_journalled(tmp_path, monkeypatch):
    from udeck.apps.emulator.migration import MigrationTransaction, plan_migration

    root, catalog, item, state, _ = legacy_library(tmp_path)
    plan = plan_migration(root, tmp_path / "Games", catalog, [item])
    journal = state.path.parent / "emulator-migration.json"
    transaction = MigrationTransaction(journal)
    original = transaction._transfer

    def crash(move):
        original(move)
        raise KeyboardInterrupt("simulated process death")

    monkeypatch.setattr(transaction, "_transfer", crash)
    with pytest.raises(KeyboardInterrupt):
        transaction.execute(plan, state)
    MigrationTransaction(journal).rollback()
    assert Path(item["path"]).read_bytes() == b"original game"
    assert json.loads(journal.read_text())["status"] == "rolled-back"


def test_cross_filesystem_copy_is_verified_before_removing_source(tmp_path, monkeypatch):
    from udeck.apps.emulator import migration

    root, catalog, item, state, _ = legacy_library(tmp_path)
    plan = migration.plan_migration(root, tmp_path / "Games", catalog, [item])
    real_link = migration.os.link

    def cross_device(source, target):
        if str(source).startswith(str(root)):
            raise OSError(errno.EXDEV, "different filesystems")
        return real_link(source, target)

    monkeypatch.setattr(migration.os, "link", cross_device)
    migration.MigrationTransaction(state.path.parent / "emulator-migration.json").execute(plan, state)
    target = tmp_path / "Games/roms/Nintendo - Game Boy/subfolder/Original.gb"
    assert target.read_bytes() == b"original game" and not Path(item["path"]).exists()


def test_cross_filesystem_destination_race_never_deletes_an_existing_file(tmp_path, monkeypatch):
    from udeck.apps.emulator import migration

    root, catalog, item, state, _ = legacy_library(tmp_path)
    plan = migration.plan_migration(root, tmp_path / "Games", catalog, [item])
    real_link = migration.os.link
    racing = []

    def race(source, target):
        if str(source).startswith(str(root)):
            Path(target).write_bytes(b"another application created this")
            racing.append(Path(target))
            raise OSError(errno.EXDEV, "different filesystems")
        return real_link(source, target)

    monkeypatch.setattr(migration.os, "link", race)
    with pytest.raises(OSError):
        migration.MigrationTransaction(state.path.parent / "emulator-migration.json").execute(plan, state)
    assert racing[0].read_bytes() == b"another application created this"
    assert Path(item["path"]).read_bytes() == b"original game"


@pytest.mark.parametrize("installed_core", [True, False])
def test_preflight_rechecks_disc_dependencies_instead_of_trusting_old_index(tmp_path, installed_core):
    from udeck.apps.emulator.migration import plan_migration

    root = tmp_path / "Legacy"
    (root / "ps1").mkdir(parents=True)
    cue = root / "ps1/Game.cue"
    cue.write_text('FILE "Original.bin" BINARY\n')
    (cue.parent / "Original.bin").write_bytes(b"original track")
    catalog = installed(tmp_path, {"pcsx_rearmed": {"supported_extensions": "cue|bin"}})
    old = scan_games(Source.create(root), catalog).items
    cue.write_text('FILE "Missing.bin" BINARY\n')
    if not installed_core:
        catalog.cores.clear()
    plan = plan_migration(root, tmp_path / "Games", catalog, old)
    assert plan.issues and "Missing.bin" in str(plan.issues)
    assert cue.is_file()


def test_controller_recovery_restores_all_configuration_after_publication_crash(tmp_path, monkeypatch):
    from PySide6.QtCore import QCoreApplication
    from test_emulator_playlist_browser import wait_for

    from udeck.apps.emulator.controller import EmulatorController
    from udeck.apps.emulator.migration import MigrationTransaction, plan_migration

    application = QCoreApplication.instance() or QCoreApplication([])
    root, catalog, item, state, save = legacy_library(tmp_path)
    state.data["preferences"].update(playlistDirectory=str(tmp_path / "Original lists"),
                                      thumbnailDirectory=str(tmp_path / "Original images"))
    state.save()
    plan = plan_migration(root, tmp_path / "Games", catalog, [item])
    journal = state.path.parent / "emulator-migration.json"
    transaction = MigrationTransaction(journal)
    publish = transaction._publish_library

    def crash(plan, state):
        publish(plan, state)
        raise KeyboardInterrupt("death after configuration publication")

    monkeypatch.setattr(transaction, "_publish_library", crash)
    with pytest.raises(KeyboardInterrupt):
        transaction.execute(plan, state)
    state.close()
    controller = EmulatorController(tmp_path / "state", tmp_path / "settings.json")
    published = state.path.read_bytes()
    controller.close()
    assert state.path.read_bytes() == published, "Closing recovery must preserve the journal's configuration version"
    controller = EmulatorController(tmp_path / "state", tmp_path / "settings.json")
    try:
        assert application and controller.migration_pending
        assert controller.library.root_path == str(tmp_path / "Games/roms")
        controller.recover_migration()
        wait_for(lambda: controller.library_task is None and not controller.library.pending)
        assert not controller.error and not controller.migration_pending
        assert controller.library.root_path == str(root)
        assert controller.library.playlist_path == str(tmp_path / "Original lists")
        assert controller.library.thumbnail_path == str(tmp_path / "Original images")
        assert all(s.path != str(tmp_path / "Games/roms") for s in controller.library.sources)
        assert controller.library.identities.identifier(item["path"]) == item["id"]
        assert save.read_bytes() == b"native SRAM" and Path(item["path"]).is_file()
    finally:
        controller.close()


def test_migration_keeps_each_archive_member_identity_and_launch_path(tmp_path):
    from udeck.apps.emulator.migration import MigrationTransaction, plan_migration
    from udeck.apps.emulator.playlists import ContentIdentities, read_library

    root, catalog, item, state, _ = legacy_library(tmp_path)
    Path(item["path"]).unlink()
    archive = root / "gb/subfolder/Pack.zip"
    with zipfile.ZipFile(archive, "w") as stream:
        stream.writestr("First.gb", b"first")
        stream.writestr("nested/Second.gb", b"second")
    games = [{**item, "path": str(archive), "id": "first-game", "archiveMember": "First.gb"},
             {**item, "path": str(archive), "id": "second-game", "archiveMember": "nested/Second.gb"}]
    plan = plan_migration(root, tmp_path / "Games", catalog, games)
    MigrationTransaction(state.path.parent / "emulator-migration.json").execute(plan, state)
    result = read_library(tmp_path / "Games/playlists", tmp_path / "Games/roms", catalog,
                          ContentIdentities(state.path.parent / "emulator-identities.json"))
    assert {i["id"] for i in result.items} == {"first-game", "second-game"}
    assert {i["archiveMember"] for i in result.items} == {"First.gb", "nested/Second.gb"}
    assert all("Pack.zip#" in i["contentPath"] for i in result.items)


def test_insufficient_space_blocks_preflight(tmp_path, monkeypatch):
    from udeck.apps.emulator import migration

    root, catalog, item, _, _ = legacy_library(tmp_path)
    usage = migration.shutil.disk_usage(root)
    monkeypatch.setattr(migration.shutil, "disk_usage", lambda path: usage._replace(free=0))
    plan = migration.plan_migration(root, tmp_path / "Games", catalog, [item])
    assert plan.issues and Path(item["path"]).is_file()
