import json
import threading

import pytest
from PySide6.QtCore import QCoreApplication
from test_games_catalog import installed

from udeck.apps.common.library import Source, scan
from udeck.apps.common.state import AppState
from udeck.apps.emulator.controller import EmulatorController, SaveStore


@pytest.fixture
def application():
    return QCoreApplication.instance() or QCoreApplication([])


def test_switch_root_preserves_current_app_favorites_and_rejects_invalid_choice(application, tmp_path):
    from udeck.apps.emulator.library import EmulatorLibrary, scan_games

    old = tmp_path / "Old"
    (old / "gb").mkdir(parents=True)
    (old / "gb/original.gb").write_bytes(b"original")
    source = Source.create(old)
    catalog = installed(tmp_path, {"gambatte": {"supported_extensions": "gb"}})
    item = scan_games(source, catalog).items[0]
    state = AppState("emulator", tmp_path / "state")
    state.data.update(sources=[source.to_dict()], index=[item], favorites=[item["id"]])
    library = EmulatorLibrary(state, catalog)
    library.refresh = lambda: None
    new = tmp_path / "New"
    new.mkdir()
    try:
        library.configure_root(new)
        before = json.loads(json.dumps(state.data))
        with pytest.raises(OSError):
            library.configure_root(tmp_path / "missing")
        assert state.data == before
        assert library.items[0]["id"] == item["id"]
        assert state.data["favorites"] == [item["id"]]
        assert source.id in {s.id for s in library.sources}
    finally:
        library.close()


def test_old_scan_completion_cannot_replace_new_root_or_cancelled_results(application, tmp_path):
    from udeck.apps.emulator.library import EmulatorLibrary

    state = AppState("emulator", tmp_path / "state")
    library = EmulatorLibrary(state, installed(tmp_path, {}))
    library.generation = 3
    library.items = [{"id": "new", "path": "/new", "sourceId": "new"}]
    library._done(2, "old", [{"id": "stale"}], {"error": "", "hints": []})
    assert [i["id"] for i in library.items] == ["new"]
    library.close()
    library._done(3, "old", [{"id": "stale"}], {"error": "", "hints": []})
    assert [i["id"] for i in library.items] == ["new"]


def test_platform_scan_does_not_import_old_loose_games_from_cache(application, tmp_path):
    from udeck.apps.emulator.library import GameScanTask

    root = tmp_path / "Old"
    root.mkdir()
    (root / "original.gb").write_bytes(b"original")
    source = Source.create(root)
    item = {**scan(source, "emulator")[0], "legacyOrigin": True}
    catalog = installed(tmp_path, {"gambatte": {"supported_extensions": "gb"}})
    results = []
    task = GameScanTask(1, source, catalog, threading.Event(), {item["path"]: item})
    task.signals.done.connect(lambda generation, source_id, items, report: results.extend(items))
    task.run()
    assert results == []


def test_emulator_does_not_read_or_migrate_games_state(application, tmp_path):
    previous = tmp_path / "games.json"
    previous.write_text(json.dumps({"version": 1, "favorites": ["old-game"], "recent": ["old-game"]}))
    original = previous.read_bytes()
    controller = EmulatorController(tmp_path, tmp_path / "settings.json")
    try:
        assert controller.store.path == tmp_path / "emulator.json"
        assert controller.store.data["favorites"] == [] and controller.store.data["recent"] == []
        controller.persist()
        assert previous.read_bytes() == original
        controller.settings()
        assert not any(row["title"] == "Legacy sources" for row in controller.menus[-1]["options"])
    finally:
        controller.close()


def test_core_and_hash_scoped_states_share_only_the_same_cores_sram(tmp_path):
    from udeck.apps.emulator.controller import CoreSaveStore

    root = tmp_path / "game"
    source = tmp_path / "serialized"
    source.write_bytes(b"serialized original")
    a = CoreSaveStore(root, "mgba", "a" * 64)
    b = CoreSaveStore(root, "mgba", "b" * 64)
    other = CoreSaveStore(root, "vbam", "a" * 64)
    a.publish("auto", source, {"coreId": "mgba", "coreHash": "a" * 64, "contentHash": "game"})
    assert "auto" in a.manifest() and not b.manifest() and not other.manifest()
    assert a.sram_root == b.sram_root and a.sram_root != other.sram_root


def test_old_saves_and_sram_are_not_read_or_migrated(tmp_path):
    from udeck.apps.emulator.controller import CoreSaveStore, latest_save

    root = tmp_path / "game"
    source = tmp_path / "serialized"
    source.write_bytes(b"legacy original")
    legacy = SaveStore(root)
    legacy.publish("auto", source, {"core": "/old/mgba_libretro.so", "coreHash": "a" * 64, "contentHash": "game"})
    legacy.prepare_sram()
    (legacy.sram_root / "original.srm").write_bytes(b"original SRAM")
    original = {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    store = CoreSaveStore(root, "mgba", "a" * 64)
    assert not store.manifest() and latest_save(root) == (None, None)
    with pytest.raises(ValueError, match="empty"):
        store.load("auto", "game", "a" * 64)
    store.prepare_sram()
    assert list(store.sram_root.iterdir()) == []
    assert not (store.root / "slots.json").exists()
    assert all((root / name).read_bytes() == value for name, value in original.items())
    assert not CoreSaveStore(root, "vbam", "b" * 64).manifest()


def test_new_scoped_save_does_not_expose_old_slots(tmp_path):
    from udeck.apps.emulator.controller import CoreSaveStore

    root = tmp_path / "game"
    source = tmp_path / "serialized"
    source.write_bytes(b"legacy original")
    legacy = SaveStore(root)
    for slot in ("1", "auto"):
        legacy.publish(slot, source, {"coreHash": "a" * 64, "contentHash": "game"})
    original = (root / "slots.json").read_bytes()
    store = CoreSaveStore(root, "mgba", "a" * 64)
    store.publish("1", source, {"coreId": "mgba", "coreHash": "a" * 64, "contentHash": "game"})
    assert set(json.loads((store.root / "slots.json").read_text())) == {"1"}
    assert set(store.manifest()) == {"1"} and (root / "slots.json").read_bytes() == original


def test_stale_launch_completion_cannot_start_a_game(application, tmp_path):
    controller = EmulatorController(tmp_path, tmp_path / "settings.json")
    try:
        generation = controller.launch_generation
        controller.cancel_launch()
        controller.launch_finished(generation, {"ready": True})
        assert not controller.engine.running() and not controller.launching
    finally:
        controller.close()


def test_opening_settings_cancels_a_launch_that_is_still_being_prepared(application, tmp_path):
    controller = EmulatorController(tmp_path, tmp_path / "settings.json")
    controller.launching = True
    generation = controller.launch_generation
    try:
        controller.settings()
        controller.launch_finished(generation, {"ready": True})
        assert not controller.launching and not controller.engine.running()
    finally:
        controller.close()


def test_open_details_keep_their_source_when_a_core_switch_removes_the_index_entry(application, tmp_path):
    controller = EmulatorController(tmp_path / "state", tmp_path / "settings.json")
    rom = tmp_path / "original.gb"
    rom.write_bytes(b"original")
    source = Source.create(tmp_path)
    item = scan(source, "emulator")[0]
    controller.library.sources = [source]
    controller.current = item
    controller.library.items = []
    try:
        assert controller.require_current()["id"] == item["id"]
    finally:
        controller.close()


def test_picker_cancel_and_enter_path_validation_preserve_configuration(application, tmp_path):
    controller = EmulatorController(tmp_path, tmp_path / "settings.json")
    before = json.loads(json.dumps(controller.store.data["preferences"]))
    try:
        controller.settings()
        controller.rom_picker()
        assert controller.menus[-1]["picker"]
        controller.dispatch("back")
        assert controller.store.data["preferences"] == before
        assert controller.menus[-1]["title"] == "Settings"
    finally:
        controller.close()


def test_unreadable_rom_root_does_not_replace_the_configuration(application, tmp_path, monkeypatch):
    controller = EmulatorController(tmp_path / "state", tmp_path / "settings.json")
    before = json.loads(json.dumps(controller.store.data["preferences"]))
    def denied(path):
        raise PermissionError("unreadable root")
    try:
        monkeypatch.setattr("udeck.apps.emulator.library.os.scandir", denied)
        with pytest.raises(PermissionError):
            controller.library.configure_root(tmp_path)
        assert controller.store.data["preferences"] == before
    finally:
        controller.close()


def test_unsupported_state_core_pause_menu_offers_normal_exit(application, tmp_path):
    controller = EmulatorController(tmp_path, tmp_path / "settings.json")
    controller.engine.running = lambda: True
    controller.engine.metadata = {"savestate": False}
    try:
        controller.pause_menu()
        titles = [str(o["title"]) for o in controller.menus[-1]["options"]]
        assert "Save state" not in titles and "Load state" not in titles
        assert "Return to library" in titles
    finally:
        controller.engine.running = lambda: False
        controller.close()


def test_creating_platform_folders_merges_existing_without_overwriting_roms(tmp_path):
    from udeck.apps.emulator.library import create_platform_directories

    catalog = installed(tmp_path, {"mgba": {"supported_extensions": "gba"}})
    root = tmp_path / "Games"
    (root / "gba").mkdir(parents=True)
    rom = root / "gba" / "original.gba"
    rom.write_bytes(b"preserve me")
    create_platform_directories(root, catalog)
    assert rom.read_bytes() == b"preserve me"
    (root / "gb").rmdir()
    (root / "gb").symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ValueError):
        create_platform_directories(root, catalog)


def test_inventory_worker_cancel_does_not_publish_an_obsolete_result(application, tmp_path):
    from udeck.apps.emulator.services import CoreInventoryTask

    catalog = installed(tmp_path, {"gambatte": {"supported_extensions": "gb"}})
    cancel = threading.Event()
    cancel.set()
    results = []
    task = CoreInventoryTask(2, catalog.preferences, {}, cancel)
    task.signals.done.connect(lambda *args: results.append(args))
    task.run()
    assert not results
