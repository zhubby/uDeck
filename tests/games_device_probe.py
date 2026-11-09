"""Run original GB/NES/GBA programs through the complete Games launch/save path.

Run explicitly on the device's graphical session, without a second Games or
RetroArch session. Results verify the software path, not physical buttons/audio.
The default no-content cases are 2048 and Mr.Boom; extra core IDs may follow the
evidence directory argument for separate platform compatibility checks.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

from game_fixtures import create_original_roms
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from udeck.apps.common.state import AppState
from udeck.apps.emulator.catalog import probe_core
from udeck.apps.emulator.controller import EmulatorController


def run(root, extra_cores=()):
    root.mkdir(parents=True, exist_ok=True)
    application = QApplication([])
    paths = create_original_roms(root / "Games")
    state = AppState("emulator", root / "state")
    state.data["preferences"]["romRoot"] = str(root / "Games")
    state.save()
    controller = EmulatorController(root / "state", root / "settings.json")
    controller.isolated = True
    errors, events, reports = [], [], []
    controller.engine.failed.connect(lambda error: errors.append(str(error)))
    controller.engine.saved.connect(lambda slot: events.append("saved:" + slot))
    controller.engine.loaded.connect(lambda: events.append("loaded"))

    def wait(condition, seconds=35):
        deadline = time.monotonic() + seconds
        while not condition() and not errors and time.monotonic() < deadline:
            application.processEvents()
            QTest.qWait(20)
        if not condition() or errors:
            (root / "failure.json").write_text(json.dumps({"errors": errors, "state": json.loads(controller.snapshotJson),
                                                         "log": controller.engine.log}, indent=2))
            raise AssertionError(str(errors) + " · " + str(controller.error) + " · " + controller.engine.log[-1200:])

    try:
        for identifier in ("gambatte", "nestopia", "mgba"):
            core = controller.catalog.cores[identifier]
            result = probe_core(core.path)
            assert result["status"] == "available", result
            controller.catalog.apply_probe(identifier, result)
        controller.library.configure_root(root / "Games")
        wait(lambda: not controller.library.pending)
        assert len(controller.library.items) == 3
        for path in paths:
            item = next(i for i in controller.library.items if i["path"] == str(path.resolve()))
            controller.open_item(item["id"])
            controller.start_game()
            wait(lambda: controller.engine.status == "playing")
            QTest.qWait(300)
            pid = controller.engine.process.processId()
            identifier = controller.checks["coreId"]
            # Changing core settings must not change the running process or save owner.
            controller.toggle_core(identifier, False, item["platform"])
            wait(lambda: not controller.library.pending)
            assert controller.engine.process.processId() == pid and controller.engine.running()
            controller.engine.pause()
            wait(lambda: controller.engine.status == "paused")
            assert controller.require_current()["id"] == item["id"]
            controller.engine.save("1")
            wait(lambda: "saved:1" in events)
            store = controller.engine.store
            state, metadata = store.load("1", controller.engine.metadata["contentHash"], controller.engine.metadata["coreHash"])
            assert state.stat().st_size > 100
            controller.engine.load("1")
            wait(lambda: "loaded" in events)
            wait(lambda: controller.engine.status == "playing")
            if os.environ.get("WAYLAND_DISPLAY"):
                subprocess.run(["grim", str(root / (item["platform"] + "-original.png"))], check=True, timeout=10)
            controller.engine.pause()
            wait(lambda: controller.engine.status == "paused")
            controller.save_exit()
            wait(lambda: not controller.engine.running())
            controller.start_game(True)
            assert controller.menus[-1]["title"] == "Resume uses another core"
            controller.choose(0)  # Restore the disabled original core, with explicit confirmation.
            events.clear()
            wait(lambda: "loaded" in events and controller.engine.status == "playing")
            controller.engine.quit()
            wait(lambda: not controller.engine.running())
            reports.append({"platform": item["platform"], "core": identifier, "stateBytes": state.stat().st_size,
                            "saveDirectory": str(store.root), "sramDirectory": str(store.sram_root),
                            "thumbnail": metadata["thumbnail"], "checks": ["launch", "settings-preserve-pid", "pause",
                            "save", "load", "save-return", "restore-disabled-core", "resume-after-restart"]})
            (root / (item["platform"] + "-retroarch.log")).write_text(controller.engine.log)
            events.clear()
            print(json.dumps(reports[-1]), flush=True)
        for identifier in ("2048", "mrboom", *extra_cores):
            core = controller.catalog.cores.get(identifier)
            if not core or not core.no_content:
                continue
            result = probe_core(core.path)
            assert result["status"] == "available", result
            controller.catalog.apply_probe(core.id, result)
            controller.run_core(core.id)
            wait(lambda: controller.engine.status == "playing")
            controller.engine.pause()
            wait(lambda: controller.engine.status == "paused")
            if core.savestate:
                controller.engine.save("1")
                wait(lambda: "saved:1" in events)
                state, _ = controller.engine.store.load("1", controller.engine.metadata["contentHash"],
                                                        controller.engine.metadata["coreHash"])
                assert state.stat().st_size > 0
                controller.engine.load("1")
                wait(lambda: "loaded" in events)
                wait(lambda: controller.engine.status == "playing")
                controller.engine.pause()
                wait(lambda: controller.engine.status == "paused")
                controller.save_exit()
                wait(lambda: not controller.engine.running())
                events.clear()
                controller.start_game(True)
                wait(lambda: "loaded" in events and controller.engine.status == "playing")
            state_name = controller.engine.state_path.name
            controller.engine.quit()
            wait(lambda: not controller.engine.running())
            reports.append({"platform": controller.current["platform"], "core": core.id,
                            "libraryName": core.library_name, "stateName": state_name,
                            "checks": ["no-content-launch", "pause", "normal-exit"] +
                            (["save", "load", "save-return", "resume-after-restart"] if core.savestate else [])})
            (root / (core.id + "-retroarch.log")).write_text(controller.engine.log)
            events.clear()
            print(json.dumps(reports[-1]), flush=True)
        (root / "result.json").write_text(json.dumps({"reports": reports, "errors": errors}, indent=2))
    finally:
        controller.close()


if __name__ == "__main__":
    run(Path(sys.argv[1]).resolve(), sys.argv[2:])
