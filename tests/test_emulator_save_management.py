"""Native bytes, recoverable history and cross-device progress are the contract."""

import hashlib
import json
import shutil

import pytest


def context(game="local-game", name="Original", core_hash="a" * 64):
    return {"gameId": game, "title": name, "basename": name, "platform": "gb",
            "contentHash": "b" * 64, "coreId": "gambatte", "coreHash": core_hash}


def test_native_state_round_trip_preserves_bytes_and_backs_up_overwritten_slot(tmp_path):
    from udeck.emulator_saves.native import SaveManager

    manager = SaveManager(tmp_path / "data")
    ctx = context()
    first = tmp_path / "Original.state"
    first.write_bytes(b"RASTATE\x00original serialized core bytes")
    with pytest.raises(ValueError, match="confirm"):
        manager.import_native(ctx, first, slot="1")
    manager.import_native(ctx, first, slot="1", confirmed=True)
    second = tmp_path / "Original.state7"
    second.write_bytes(b"RASTATE\x00second serialized core bytes")
    manager.import_native(ctx, second, slot="1", confirmed=True)
    exported = manager.export_native(ctx, tmp_path / "导出", slot="1")
    assert [p.name for p in exported] == ["Original.state1"]
    assert exported[0].read_bytes() == second.read_bytes()
    entries = manager.history.entries(ctx)
    assert len(entries) == 2
    original = next(e for e in entries if e["files"]["Original.state1"]["sha256"] == hashlib.sha256(first.read_bytes()).hexdigest())
    manager.restore(ctx, original["id"])
    assert manager.store(ctx).load("1", "b" * 64, "a" * 64)[0].read_bytes() == first.read_bytes()
    with pytest.raises(FileExistsError):
        manager.export_native(ctx, tmp_path / "导出", slot="1")


def test_sram_rtc_round_trip_and_running_game_lock(tmp_path):
    from udeck.emulator_saves.native import SaveManager

    manager = SaveManager(tmp_path / "data")
    ctx = context()
    sram = tmp_path / "Foreign name.srm"
    sram.write_bytes(b"battery backed memory\x00")
    sram.with_suffix(".rtc").write_bytes(b"clock bytes\x01")
    manager.import_native(ctx, sram, confirmed=True)
    exported = manager.export_native(ctx, tmp_path / "out", kind="sram")
    assert {p.name: p.read_bytes() for p in exported} == {
        "Original.srm": b"battery backed memory\x00", "Original.rtc": b"clock bytes\x01"}
    with manager.session(ctx):
        with pytest.raises(RuntimeError, match="running"):
            manager.import_native(ctx, sram, confirmed=True)
        with pytest.raises(RuntimeError, match="running"):
            manager.export_native(ctx, tmp_path / "blocked", kind="sram")
    assert manager.export_native(ctx, tmp_path / "after", kind="sram")


def test_import_without_rtc_does_not_reuse_an_unrelated_clock(tmp_path):
    from udeck.emulator_saves.native import SaveManager

    manager = SaveManager(tmp_path / "data")
    first = tmp_path / "first.srm"
    first.write_bytes(b"first SRAM")
    first.with_suffix(".rtc").write_bytes(b"first clock")
    manager.import_native(context(), first, confirmed=True)
    second = tmp_path / "second.srm"
    second.write_bytes(b"second SRAM without clock")
    manager.import_native(context(), second, confirmed=True)
    exported = manager.export_native(context(), tmp_path / "out", kind="sram")
    assert [p.name for p in exported] == ["Original.srm"]
    assert any("Original.rtc" in e["files"] for e in manager.history.entries())


def test_cloud_restore_matches_content_across_local_ids_names_and_core_versions(tmp_path):
    from udeck.emulator_saves.native import SaveManager

    a, b = SaveManager(tmp_path / "a"), SaveManager(tmp_path / "b")
    original, renamed = context(), context("other-local-id", "改名 ROM")
    source = tmp_path / "game.state.auto"
    source.write_bytes(b"native auto state")
    a.import_native(original, source, slot="auto", confirmed=True)
    shutil.copytree(a.history.snapshots, b.history.snapshots, dirs_exist_ok=True)
    assert b.reconcile(renamed)["applied"] == 1
    assert b.store(renamed).load("auto", "b" * 64, "a" * 64)[0].read_bytes() == b"native auto state"
    assert b.export_native(renamed, tmp_path / "out", slot="auto")[0].name == "改名 ROM.state.auto"
    incompatible = context("third", "Original", "c" * 64)
    result = b.reconcile(incompatible)
    assert result["incompatible"]
    assert b.store(incompatible).manifest() == {}


def test_offline_branches_remain_until_explicit_resolution_and_then_converge(tmp_path):
    from udeck.emulator_saves.native import SaveManager

    a, b = SaveManager(tmp_path / "a"), SaveManager(tmp_path / "b")
    ctx = context()
    source = tmp_path / "game.state"
    source.write_bytes(b"base")
    a.import_native(ctx, source, slot="1", confirmed=True)
    shutil.copytree(a.history.snapshots, b.history.snapshots, dirs_exist_ok=True)
    b.reconcile(ctx)
    source.write_bytes(b"offline A")
    a.import_native(ctx, source, slot="1", confirmed=True)
    source.write_bytes(b"offline B")
    b.import_native(ctx, source, slot="1", confirmed=True)
    shutil.copytree(a.history.snapshots, b.history.snapshots, dirs_exist_ok=True)
    result = b.reconcile(ctx)
    assert len(result["conflicts"]) == 1
    assert b.store(ctx).load("1", "b" * 64, "a" * 64)[0].read_bytes() == b"offline B"
    candidates = result["conflicts"][0]["versions"]
    chosen = next(v for v in candidates if v["deviceId"] == a.history.device_id)
    b.restore(ctx, chosen["id"])
    shutil.copytree(b.history.snapshots, a.history.snapshots, dirs_exist_ok=True)
    assert a.reconcile(ctx)["conflicts"] == []
    assert a.store(ctx).load("1", "b" * 64, "a" * 64)[0].read_bytes() == b"offline A"
    assert len(a.history.entries(ctx)) == 4


def test_damaged_snapshot_and_symlink_import_cannot_replace_good_state(tmp_path):
    from udeck.emulator_saves.native import SaveManager

    manager = SaveManager(tmp_path / "data")
    ctx = context()
    source = tmp_path / "game.state"
    source.write_bytes(b"good state")
    manager.import_native(ctx, source, slot="2", confirmed=True)
    entry = manager.history.entries(ctx)[0]
    directory = manager.history.directory(entry["id"])
    (directory / "Original.state2").write_bytes(b"damaged")
    with pytest.raises(ValueError, match="damaged"):
        manager.restore(ctx, entry["id"])
    link = tmp_path / "link.state"
    link.symlink_to(source)
    with pytest.raises((ValueError, OSError)):
        manager.import_native(ctx, link, confirmed=True)
    assert manager.store(ctx).load("2", "b" * 64, "a" * 64)[0].read_bytes() == b"good state"


def test_failed_import_preserves_previous_slot_and_history(tmp_path, monkeypatch):
    from udeck.emulator_saves.native import SaveManager

    manager = SaveManager(tmp_path / "data")
    ctx = context()
    source = tmp_path / "game.state"
    source.write_bytes(b"first")
    manager.import_native(ctx, source, confirmed=True)
    source.write_bytes(b"second")
    import udeck.apps.common.state as state
    replace = state.os.replace

    def no_space(src, dst):
        if str(dst).endswith("slots.json"):
            raise OSError("disk full")
        return replace(src, dst)

    monkeypatch.setattr(state.os, "replace", no_space)
    with pytest.raises(OSError, match="disk full"):
        manager.import_native(ctx, source, confirmed=True)
    assert manager.store(ctx).load("1", "b" * 64, "a" * 64)[0].read_bytes() == b"first"


def test_snapshot_paths_and_metadata_are_validated_before_restore(tmp_path):
    from udeck.emulator_saves.native import SaveManager

    manager = SaveManager(tmp_path / "data")
    source = tmp_path / "game.state"
    source.write_bytes(b"native bytes")
    manager.import_native(context(), source, confirmed=True)
    entry = manager.history.entries()[0]
    manifest = manager.history.directory(entry["id"]) / "manifest.json"
    data = json.loads(manifest.read_text())
    data["files"]["../../escaped"] = next(iter(data["files"].values()))
    manifest.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        manager.restore(context(), entry["id"])
    assert not (tmp_path / "escaped").exists()


@pytest.mark.parametrize("clean", [True, False])
def test_only_clean_frontend_exit_promotes_runtime_sram(tmp_path, clean):
    from PySide6.QtCore import QProcess

    from udeck.apps.emulator.controller import RetroEngine, SaveStore

    engine = RetroEngine()
    engine.store = SaveStore(tmp_path / "committed")
    engine.store.prepare_sram()
    (engine.store.sram_root / "Original.srm").write_bytes(b"last good SRAM")
    engine.sram_runtime = tmp_path / "runtime"
    engine.sram_runtime.mkdir()
    (engine.sram_runtime / "Original.srm").write_bytes(b"new SRAM")
    try:
        engine.exited(0 if clean else 1, QProcess.ExitStatus.NormalExit if clean else QProcess.ExitStatus.CrashExit)
        assert (engine.store.sram_root / "Original.srm").read_bytes() == (b"new SRAM" if clean else b"last good SRAM")
        assert engine.sram_committed is clean
    finally:
        engine.close()


def test_unqueued_local_progress_is_preserved_as_a_branch_before_cloud_restore(tmp_path):
    from udeck.emulator_saves.native import SaveManager

    a, b = SaveManager(tmp_path / "a"), SaveManager(tmp_path / "b")
    ctx = context()
    source = tmp_path / "Original.state"
    source.write_bytes(b"base")
    a.import_native(ctx, source, confirmed=True)
    shutil.copytree(a.history.snapshots, b.history.snapshots, dirs_exist_ok=True)
    b.reconcile(ctx)
    source.write_bytes(b"new cloud progress")
    a.import_native(ctx, source, confirmed=True)
    source.write_bytes(b"saved locally before background backup ran")
    b.store(ctx).publish("1", source, {"contentHash": "b" * 64, "coreHash": "a" * 64})
    shutil.copytree(a.history.snapshots, b.history.snapshots, dirs_exist_ok=True)
    assert len(b.reconcile(ctx)["conflicts"]) == 1
    assert b.store(ctx).load("1", "b" * 64, "a" * 64)[0].read_bytes() == source.read_bytes()


def test_each_local_rom_copy_tracks_its_own_applied_head(tmp_path):
    from udeck.emulator_saves.native import SaveManager

    a, b = SaveManager(tmp_path / "a"), SaveManager(tmp_path / "b")
    source = tmp_path / "Original.state"
    source.write_bytes(b"first")
    a.import_native(context(), source, confirmed=True)
    shutil.copytree(a.history.snapshots, b.history.snapshots, dirs_exist_ok=True)
    for ctx in (context("copy-one"), context("copy-two", "Renamed")):
        b.reconcile(ctx)
    source.write_bytes(b"second")
    a.import_native(context(), source, confirmed=True)
    shutil.copytree(a.history.snapshots, b.history.snapshots, dirs_exist_ok=True)
    for ctx in (context("copy-one"), context("copy-two", "Renamed")):
        b.reconcile(ctx)
        assert b.store(ctx).load("1", "b" * 64, "a" * 64)[0].read_bytes() == b"second"


def test_interrupted_sram_directory_swap_recovers_before_runtime_seed(tmp_path):
    from udeck.emulator_saves.store import SaveStore

    store = SaveStore(tmp_path / "committed")
    store.prepare_sram()
    (store.sram_root / "Original.srm").write_bytes(b"last committed generation")
    store.sram_root.rename(store.sram_root.with_name(".sram-previous"))
    store.prepare_sram()
    assert (store.sram_root / "Original.srm").read_bytes() == b"last committed generation"


def test_export_overwrite_preserves_all_previous_native_files(tmp_path):
    from udeck.emulator_saves.native import SaveManager

    manager = SaveManager(tmp_path / "data")
    source = tmp_path / "foreign.srm"
    source.write_bytes(b"new SRAM")
    source.with_suffix(".rtc").write_bytes(b"new RTC")
    manager.import_native(context(), source, confirmed=True)
    output = tmp_path / "export"
    output.mkdir()
    (output / "Original.srm").write_bytes(b"old SRAM")
    (output / "Original.rtc").write_bytes(b"old RTC")
    manager.export_native(context(), output, kind="sram", overwrite=True)
    assert (output / "Original.srm").read_bytes() == b"new SRAM"
    assert (output / "Original.rtc").read_bytes() == b"new RTC"
    assert {p.read_bytes() for p in output.glob(".retroarch-save-backups/*/*")} == {b"old SRAM", b"old RTC"}


@pytest.mark.parametrize("change", [
    {"context": None}, {"created": None}, {"created": float("inf")},
    {"deviceName": []}, {"kind": "sram", "slot": "1"}, {"parents": [None]},
    {"files": {"missing.state1": {"size": 1, "sha256": "a" * 64}}},
])
def test_malformed_snapshot_metadata_never_replaces_progress(tmp_path, change):
    from udeck.emulator_saves.native import SaveManager

    manager = SaveManager(tmp_path / "data")
    source = tmp_path / "Original.state"
    source.write_bytes(b"good state")
    manager.import_native(context(), source, confirmed=True)
    entry = manager.history.entries()[0]
    manifest = manager.history.directory(entry["id"]) / "manifest.json"
    data = json.loads(manifest.read_text())
    data.update(change)
    manifest.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="damaged"):
        manager.restore(context(), entry["id"])
    assert manager.store(context()).load("1", "b" * 64, "a" * 64)[0].read_bytes() == b"good state"


def test_identical_parallel_saves_merge_before_subsequent_progress(tmp_path):
    from udeck.emulator_saves.native import SaveManager

    a, b = SaveManager(tmp_path / "a"), SaveManager(tmp_path / "b")
    source = tmp_path / "Original.state"
    source.write_bytes(b"identical independent saves")
    a.import_native(context(), source, confirmed=True)
    b.import_native(context(), source, confirmed=True)
    shutil.copytree(a.history.snapshots, b.history.snapshots, dirs_exist_ok=True)
    assert b.reconcile(context())["conflicts"] == []
    source.write_bytes(b"continued progress")
    b.import_native(context(), source, confirmed=True)
    shutil.copytree(b.history.snapshots, a.history.snapshots, dirs_exist_ok=True)
    assert a.reconcile(context())["conflicts"] == []
    assert a.store(context()).load("1", "b" * 64, "a" * 64)[0].read_bytes() == b"continued progress"


def test_explicit_saves_and_backups_publish_independent_immutable_snapshots(tmp_path):
    from udeck.emulator_saves.native import SaveManager

    manager = SaveManager(tmp_path / "data")
    source = tmp_path / "Original.state"
    source.write_bytes(b"same native bytes")
    first = manager.import_native(context(), source, confirmed=True)
    original_manifest = (manager.history.directory(first["id"]) / "manifest.json").read_bytes()
    second = manager.import_native(context(), source, confirmed=True)
    manager.backup(context())
    entries = manager.history.entries()
    assert len(entries) == 3 and first["id"] != second["id"]
    assert entries[0]["parents"] == [second["id"]]
    assert (manager.history.directory(first["id"]) / "manifest.json").read_bytes() == original_manifest


@pytest.mark.parametrize("slot", ["0", "4", "../invalid"])
def test_invalid_target_slot_cannot_change_the_save_index(tmp_path, slot):
    from udeck.emulator_saves.native import SaveManager

    manager = SaveManager(tmp_path / "data")
    source = tmp_path / "Original.state"
    source.write_bytes(b"good progress")
    manager.import_native(context(), source, confirmed=True)
    before = manager.store(context()).manifest()
    with pytest.raises(ValueError, match="slot"):
        manager.import_native(context(), source, slot=slot, confirmed=True)
    assert manager.store(context()).manifest() == before
