"""Regressions for Games catalogue changes and the RetroArch boundary."""

import copy
import sys
import time
from pathlib import Path

import pytest
from PySide6.QtCore import QCoreApplication, QThreadPool
from PySide6.QtTest import QTest
from test_games_catalog import installed

from udeck.apps.common.library import Source
from udeck.apps.common.state import AppState
from udeck.apps.emulator.catalog import CoreCatalog
from udeck.apps.emulator.controller import EmulatorController, RetroEngine, SaveStore, preflight
from udeck.apps.emulator.library import EmulatorLibrary, content_dependencies, scan_games


@pytest.fixture
def application():
    return QCoreApplication.instance() or QCoreApplication([])


def wait_for(predicate, seconds=3):
    deadline = time.monotonic() + seconds
    while not predicate() and time.monotonic() < deadline:
        QTest.qWait(20)
    assert predicate()


@pytest.mark.parametrize("ignores_quit", [False, True])
@pytest.mark.parametrize("close", [False, True])
def test_paused_frontend_quits_without_focus_or_spurious_pipe_errors(application, tmp_path, ignores_quit, close):
    frontend = tmp_path / "frontend.py"
    commands, cleanup = tmp_path / "commands", tmp_path / "cleanup"
    frontend.write_text('''import os, signal, sys
from pathlib import Path
commands, cleanup = map(Path, sys.argv[1:3])
def terminate(signum, frame):
    cleanup.write_text("terminated")
    signal.signal(signal.SIGTERM, signal.SIG_DFL)
    os.kill(os.getpid(), signal.SIGTERM)
signal.signal(signal.SIGTERM, terminate)
print("GET_STATUS PAUSED", flush=True)
for command in sys.stdin:
    with commands.open("a") as log: log.write(command)
    if command.strip() == "QUIT" and sys.argv[3] == "False":
        cleanup.write_text("quit")
        break
    if command.strip() == "GET_STATUS":
        print("GET_STATUS PAUSED", flush=True)
''')
    engine = RetroEngine()
    engine.resume_on_start = False
    failures = []
    engine.failed.connect(lambda error: failures.append(str(error)))
    engine.process.setProgram(sys.executable)
    engine.process.setArguments([str(frontend), str(commands), str(cleanup), str(ignores_quit)])
    engine.process.start()
    engine.timer.start()
    try:
        wait_for(lambda: engine.status == "paused")
        if close:
            engine.close()
        else:
            engine.quit()
        wait_for(lambda: not engine.running(), seconds=3)
        assert engine.status == "idle" and not failures
        assert cleanup.read_text() == ("terminated" if ignores_quit else "quit")
        lines = commands.read_text().splitlines()
        assert lines[lines.index("QUIT"):] == ["QUIT"]
    finally:
        if engine.running():
            engine.process.kill()
            engine.process.waitForFinished(1000)
        engine.close()


def test_requested_quit_still_reports_an_unexpected_exit(application, tmp_path):
    frontend = tmp_path / "frontend.py"
    frontend.write_text('''import os, sys
print("GET_STATUS PAUSED", flush=True)
for command in sys.stdin:
    if command.strip() == "QUIT": os._exit(7)
''')
    engine = RetroEngine()
    engine.resume_on_start = False
    failures = []
    engine.failed.connect(lambda error: failures.append(str(error)))
    engine.process.setProgram(sys.executable)
    engine.process.setArguments([str(frontend)])
    engine.process.start()
    try:
        wait_for(lambda: engine.status == "paused")
        engine.quit()
        wait_for(lambda: not engine.running())
        assert failures and "7" in failures[-1]
    finally:
        engine.close()


def test_quit_actions_uncover_frontend_and_return_to_details(application, tmp_path, monkeypatch):
    controller = EmulatorController(tmp_path / "state", tmp_path / "settings.json")
    events = []

    class Window:
        def showMinimized(self):
            events.append("uncover")

    controller.window = Window()
    monkeypatch.setattr(controller.engine, "quit", lambda: events.append("quit"))
    monkeypatch.setattr(controller.engine, "running", lambda: True)
    controller.present.connect(lambda: events.append("present"))
    try:
        controller.confirm_quit()
        controller.dispatch("accept")
        assert events == ["quit", "uncover"]
        controller.game_exited(0)
        assert events[-1] == "present" and controller.page == "game-details" and not controller.menus
        events.clear()
        controller.exit_after_save = True
        controller.save_done("auto")
        assert events == ["quit", "uncover"]
        events.clear()
        controller.engine.metadata["savestate"] = False
        controller.pause_menu()
        controller.choose(1)
        assert events[-2:] == ["quit", "uncover"]
    finally:
        monkeypatch.undo()
        controller.window = None
        controller.close()


@pytest.mark.parametrize("library_name", ["Original Core", "Mr.Boom"])
def test_no_content_state_uses_native_library_name_through_save_and_load(application, tmp_path, library_name):
    catalog = installed(tmp_path, {"original_core": {"supports_no_game": "true"}})
    catalog.apply_probe("original_core", {"status": "available", "name": library_name,
                                           "version": "1", "coreHash": "a" * 64})
    # A separate process follows RetroArch's no-content naming and stdin protocol.
    frontend = tmp_path / "frontend"
    frontend.write_text(f"#!{sys.executable}\nstate_name = {library_name + '.state'!r}\n" + '''
import pathlib, re, sys
args = sys.argv[1:]
config = pathlib.Path(args[args.index("--appendconfig") + 1]).read_text()
root = pathlib.Path(re.search(r'^savestate_directory = "(.*)"$', config, re.M)[1])
state = root / state_name
for command in sys.stdin:
    command = command.strip()
    if command == "QUIT":
        break
    if command == "GET_STATUS":
        print("GET_STATUS PAUSED", flush=True)
    elif command == "SAVE_STATE":
        state.write_bytes(b"original serialized state")
        print(f'[State]: Saving state "{state}", 25 bytes.', file=sys.stderr, flush=True)
    elif command == "LOAD_STATE":
        assert state.read_bytes() == b"original serialized state"
        print(f'[State]: Loading state "{state}"', file=sys.stderr, flush=True)
    elif command == "VERSION":
        print("1.20.0", flush=True)
''')
    frontend.chmod(0o700)
    item = {"id": "core:original_core", "platform": "original-core", "coreId": "original_core",
            "noContent": True, "path": "", "format": ""}
    checks = preflight(item, catalog.preferences, executable=str(frontend), catalog=catalog,
                       validate_native=False)
    engine, store = RetroEngine(), SaveStore(tmp_path / "saves")
    saved, loaded, failures = [], [], []
    engine.saved.connect(saved.append)
    engine.loaded.connect(lambda: loaded.append(True))
    engine.failed.connect(lambda error: failures.append(str(error)))
    try:
        assert checks["ready"], checks
        engine.start(item, checks, store)
        wait_for(lambda: engine.status == "paused" or failures)
        engine.save("1")
        wait_for(lambda: saved or failures)
        assert not failures and saved == ["1"]
        assert store.load("1", engine.metadata["contentHash"], "a" * 64)[0].read_bytes() == b"original serialized state"
        engine.load("1")
        wait_for(lambda: loaded or failures)
        assert loaded and not failures
    finally:
        engine.close()


def test_refresh_discovers_a_rom_root_created_after_startup(application, tmp_path):
    root = tmp_path / "Games"
    state = AppState("emulator", tmp_path / "state")
    state.data["preferences"]["romRoot"] = str(root)
    catalog = installed(tmp_path, {"mgba": {"supported_extensions": "gba"}})
    library = EmulatorLibrary(state, catalog)
    (root / "gba").mkdir(parents=True)
    rom = root / "gba/original.gba"
    rom.write_bytes(b"original")
    try:
        library.refresh()
        wait_for(lambda: not library.pending)
        assert [item["path"] for item in library.items] == [str(rom)]
        identifier = library.items[0]["id"]
        library.refresh()
        wait_for(lambda: not library.pending)
        assert library.items[0]["id"] == identifier
        assert len(library.sources) == 1
        restored = EmulatorLibrary(AppState("emulator", tmp_path / "state"), catalog)
        try:
            assert restored.root_id == library.root_id
        finally:
            restored.close()
    finally:
        library.close()
        QThreadPool.globalInstance().waitForDone(3000)


@pytest.mark.parametrize("view", ["catalog", "detail", "search"])
def test_replacing_catalogue_removes_stale_core_menus(application, tmp_path, view):
    old = installed(tmp_path, {"removed": {"systemid": "unique-console", "supported_extensions": "rom"},
                               "gambatte": {"supported_extensions": "gb"}})
    controller = EmulatorController(tmp_path / "state", tmp_path / "settings.json")
    controller.catalog = controller.library.catalog = old
    controller.core_management()
    if view == "detail":
        controller.platform_cores_menu("unique-console")
        controller.core_details("removed", "unique-console")
    elif view == "search":
        controller.prompt("Search cores", controller.core_search)
        controller.core_search("removed")
    (tmp_path / "cores/removed_libretro.so").unlink()
    new = CoreCatalog.discover(old.preferences, info_directories=[tmp_path / "info"])
    try:
        controller.catalog_discovered(controller.core_generation, new)
        assert all("unique-console/" not in str(row["subtitle"])
                   for menu in controller.menus if menu.get("coreView") == "catalog"
                   for row in menu["options"])
        controller.catalog_finished(controller.core_generation, {})
        assert all(menu.get("coreId") != "removed" and menu.get("platformId") != "unique-console"
                   for menu in controller.menus)
        assert all("unique-console/" not in str(row["subtitle"]) and str(row["title"]) != "removed"
                   for menu in controller.menus for row in menu["options"])
        controller.choose(controller.menus[-1]["index"])
        assert not controller.error
    finally:
        controller.close()
        QThreadPool.globalInstance().waitForDone(3000)


def test_catalogue_refresh_preserves_an_open_search_draft(application, tmp_path):
    catalog = installed(tmp_path, {"gambatte": {"supported_extensions": "gb"}})
    controller = EmulatorController(tmp_path / "state", tmp_path / "settings.json")
    controller.catalog = controller.library.catalog = catalog
    try:
        controller.core_management()
        controller.prompt("Search cores", controller.core_search, "Game Boy")
        controller.catalog_discovered(controller.core_generation, copy.deepcopy(catalog))
        assert controller.menus[-1]["input"] and controller.menus[-1]["draft"] == "Game Boy"
        controller.submit("gambatte")
        assert [str(row["title"]) for row in controller.menus[-1]["options"]] == ["gambatte"]
    finally:
        controller.close()


def test_core_check_preserves_the_focused_action(application, tmp_path):
    catalog = installed(tmp_path, {"gambatte": {"supported_extensions": "gb"}})
    catalog.cores["gambatte"].status = "unverified"
    controller = EmulatorController(tmp_path / "state", tmp_path / "settings.json")
    controller.catalog = controller.library.catalog = catalog
    try:
        controller.core_details("gambatte", "gb")
        menu = controller.menus[-1]
        menu["index"] = next(i for i, row in enumerate(menu["options"]) if str(row["title"]) == "Back")
        controller.core_progress(controller.core_generation, "gambatte", {"status": "available"})
        menu = controller.menus[-1]
        assert str(menu["options"][menu["index"]]["title"]) == "Back"
    finally:
        controller.close()


@pytest.mark.parametrize("platform", [None, "atari800"])
def test_no_content_uses_the_enabled_platform(application, tmp_path, monkeypatch, platform):
    catalog = installed(tmp_path, {"a5200": {"supported_extensions": "a52"},
                                   "atari800": {"supported_extensions": "atr", "supports_no_game": "true"}})
    controller = EmulatorController(tmp_path / "state", tmp_path / "settings.json")
    controller.store.data["preferences"] = catalog.preferences
    controller.catalog = controller.library.catalog = catalog
    tasks = []
    monkeypatch.setattr(QThreadPool.globalInstance(), "start", tasks.append)
    try:
        controller.core_details("atari800", platform)
        index = next(i for i, row in enumerate(controller.menus[-1]["options"])
                     if str(row["title"]) == "Run core without content")
        controller.choose(index)
        assert len(tasks) == 1 and tasks[0].item["platform"] == "atari800"
        checks = preflight(tasks[0].item, catalog.preferences, executable="/fixture/retroarch",
                           catalog=catalog, validate_native=False)
        assert checks["ready"], checks
        assert "coreEnabled" not in catalog.preferences
    finally:
        controller.close()


def test_nested_playlists_parse_each_descriptor_once(tmp_path, monkeypatch):
    (tmp_path / "disc.bin").write_bytes(b"original")
    (tmp_path / "0.m3u").write_text("disc.bin\n")
    for index in range(1, 6):
        (tmp_path / f"{index}.m3u").write_text((f"{index - 1}.m3u\n") * 6)
    reads = []
    original = Path.read_text
    def read(path, *args, **kwargs):
        reads.append(path.name)
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, "read_text", read)
    dependencies = content_dependencies(tmp_path / "5.m3u", tmp_path)
    assert {p.name for p in dependencies} == {"0.m3u", "1.m3u", "2.m3u", "3.m3u", "4.m3u", "disc.bin"}
    assert sorted(reads) == ["0.m3u", "1.m3u", "2.m3u", "3.m3u", "4.m3u", "5.m3u"]


def test_repeated_disc_references_have_a_total_work_limit(tmp_path):
    (tmp_path / "disc.bin").write_bytes(b"original")
    playlist = tmp_path / "original.m3u"
    playlist.write_text("disc.bin\n" * 100_000)
    with pytest.raises(ValueError, match="Too many disc references"):
        content_dependencies(playlist, tmp_path)


def test_disc_dependency_walk_honors_cancellation(tmp_path):
    playlist = tmp_path / "original.m3u"
    playlist.write_text("disc.bin\n" * 100)
    checks = []
    def cancelled():
        checks.append(True)
        return len(checks) >= 5
    with pytest.raises(OSError, match="Scan cancelled"):
        content_dependencies(playlist, tmp_path, cancelled=cancelled)


def test_disc_descriptors_have_a_combined_size_limit(tmp_path):
    (tmp_path / "disc.bin").write_bytes(b"original")
    for index in range(5):
        (tmp_path / f"{index}.m3u").write_text("#" + "original " * 200_000 + "\ndisc.bin\n")
    playlist = tmp_path / "original.m3u"
    playlist.write_text("".join(f"{index}.m3u\n" for index in range(5)))
    with pytest.raises(ValueError, match="Disc descriptor is too large"):
        content_dependencies(playlist, tmp_path)


@pytest.mark.parametrize("operation", ["scan", "preflight"])
def test_cancellation_reaches_disc_parsing_from_its_callers(tmp_path, monkeypatch, operation):
    catalog = installed(tmp_path, {"pcsx_rearmed": {"supported_extensions": "m3u|cue|bin"}})
    folder = tmp_path / "Games/psx"
    folder.mkdir(parents=True)
    first, second = folder / "a.m3u", folder / "b.m3u"
    first.write_text("b.m3u\n")
    second.write_text("disc.bin\n")
    (folder / "disc.bin").write_bytes(b"original")
    reads = []
    original = Path.read_text
    def read(path, *args, **kwargs):
        reads.append(path.name)
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, "read_text", read)
    def cancelled():
        return bool(reads)
    if operation == "scan":
        assert not scan_games(Source.create(tmp_path / "Games"), catalog, cancelled=cancelled).items
    else:
        checks = preflight({"id": "original", "platform": "psx", "path": str(first)}, catalog.preferences,
                           executable="/fixture/retroarch", catalog=catalog, validate_native=False,
                           cancelled=cancelled)
        assert not checks["ready"]
        assert any("Scan cancelled" in str(error) for error in checks["errors"])
    assert reads == ["a.m3u"]


@pytest.mark.parametrize("identifier", ["genesis_plus_gx", "genesis_plus_gx_wide", "picodrive"])
def test_sega_cd_requires_a_region_bios_without_blocking_cartridges(tmp_path, identifier):
    values = {"supported_extensions": "md|iso", "firmware_count": "3"}
    for index, region in enumerate(("E", "U", "J")):
        values.update({f"firmware{index}_path": f"bios_CD_{region}.bin", f"firmware{index}_opt": "true"})
    catalog = installed(tmp_path, {identifier: values})
    system = tmp_path / "system"
    system.mkdir()
    rom = tmp_path / "original.iso"
    rom.write_bytes(b"original")
    prefs = {**catalog.preferences, "firmwareDirectory": str(system)}
    item = {"id": "original", "platform": "segacd", "path": str(rom)}
    checks = preflight(item, prefs, executable="/fixture/retroarch", catalog=catalog, validate_native=False)
    assert not checks["ready"]
    assert "bios_CD_E.bin" in "\n".join(map(str, checks["errors"]))
    assert not catalog.firmware_check(catalog.cores[identifier], "megadrive", system)["required"]
    (system / "bios_CD_U.bin").write_bytes(b"original BIOS fixture")
    assert preflight(item, prefs, executable="/fixture/retroarch", catalog=catalog,
                     validate_native=False)["ready"]
