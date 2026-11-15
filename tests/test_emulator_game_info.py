"""Selected-game facts and history use game identity, independently of list entries."""

import sys
import time
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QCoreApplication, QEventLoop, QTimer
from test_games_catalog import installed

from udeck.apps.common.state import AppState
from udeck.apps.emulator.controller import EmulatorController
from udeck.apps.emulator.game_info import game_info, play_time
from udeck.i18n import render


def values(item, catalog, data, language="en"):
    return {row["key"]: row["value"] for row in render(game_info(item, catalog, data), language)}


def test_entry_core_and_database_are_separate_from_shared_game_history(tmp_path):
    catalog = installed(tmp_path, {"gambatte": {"supported_extensions": "gb|gbc"},
                                   "sameboy": {"supported_extensions": "gb|gbc"}},
                        {"coreEnabled": {"sameboy": True}})
    timestamp = datetime(2026, 11, 15, 8, 20, tzinfo=UTC).timestamp()
    data = {"positions": {"game": {"seconds": 7380, "lastPlayed": timestamp}}, "recent": ["game"]}
    item = {"id": "entry-a", "gameId": "game", "platform": "gb", "format": "GBC",
            "dbName": "Nintendo - Game Boy Color", "path": "/roms/pack.zip",
            "archiveMember": "folder/original.gbc", "playlistPath": "/lists/Mixed.lpl",
            "playlistCoreId": "sameboy", "playlistDefaultCoreId": "gambatte"}
    first = values(item, catalog, data)
    second = values({**item, "id": "entry-b", "title": "Another label",
                     "playlistCoreId": "", "playlistPath": "/lists/Other.lpl"}, catalog, data)
    assert first["system"] == "Game Boy Color · GBC / ZIP"
    assert first["core"] == "sameboy" and second["core"] == "gambatte"
    assert first["lastPlayed"] == second["lastPlayed"] == datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M")
    assert first["playTime"] == second["playTime"] == "2 h 3 min"
    chinese = values(item, catalog, data, "zh_CN")
    assert chinese["playTime"] == "2 小时 3 分钟"
    assert len(game_info(item, catalog, data)) == 4


@pytest.mark.parametrize("seconds,expected", [(0, "0 min"), (1, "<1 min"), (59.9, "<1 min"),
                                             (60, "1 min"), (3599, "59 min"), (3600, "1 h 0 min"),
                                             (-1, "0 min"), (float("nan"), "0 min"),
                                             (float("inf"), "0 min"), (10 ** 1000, "0 min"),
                                             ("bad", "0 min"), (True, "0 min")])
def test_play_time_is_readable_and_rejects_invalid_records(seconds, expected):
    assert render(play_time(seconds)) == expected


def test_never_played_and_legacy_records_do_not_invent_dates(tmp_path):
    catalog = installed(tmp_path, {"mgba": {"supported_extensions": "gba"}})
    item = {"id": "entry", "gameId": "g", "platform": "gba", "format": "GBA"}
    for data, last in (({}, "Not played yet"),
                       ({"recent": ["g"]}, "Time not recorded"),
                       ({"positions": {"g": {"seconds": 60}}}, "Time not recorded"),
                       ({"positions": {"g": {"seconds": 60, "lastPlayed": 1e100}}}, "Time not recorded"),
                       ({"positions": {"g": None}}, "Not played yet")):
        assert values(item, catalog, data)["lastPlayed"] == last
    assert values(item, catalog, {}, "zh_CN")["lastPlayed"] == "尚未游玩"
    assert game_info({}, catalog, {}) == game_info({"kind": "playlist"}, catalog, {}) == []


def test_core_status_changes_do_not_claim_an_unavailable_core_is_ready(tmp_path):
    catalog = installed(tmp_path, {"mgba": {"supported_extensions": "gba"}},
                        {"gameCores": {"g": "mgba"}})
    item = {"id": "entry", "gameId": "g", "platform": "gba", "format": "GBA"}
    assert values(item, catalog, {})["core"] == "mgba"
    catalog.cores["mgba"].status = "unverified"
    assert "Checking" in values(item, catalog, {})["core"]
    catalog.preferences["coreEnabled"] = {"mgba": False}
    assert values(item, catalog, {})["core"] == "mgba · Unavailable"
    assert values({**item, "playlistPath": "/lists/Custom.lpl", "playlistCoreId": "missing"},
                  catalog, {})["core"] == "missing · Unavailable"


@pytest.mark.parametrize("fails", [False, True])
def test_history_is_persisted_only_after_frontend_confirms_content(tmp_path, monkeypatch, fails):
    application = QCoreApplication.instance() or QCoreApplication([])
    controller = EmulatorController(tmp_path / "state", tmp_path / "settings.json")
    wall = [1794720000.0]
    monkeypatch.setattr("udeck.apps.emulator.controller.time",
                        SimpleNamespace(time=lambda: wall[0], monotonic=time.monotonic))
    frontend = tmp_path / "frontend.py"
    frontend.write_text("import sys\n" + ("sys.exit(7)\n" if fails else '''
for command in sys.stdin:
    if command.strip() == "GET_STATUS":
        print("GET_STATUS PLAYING", flush=True)
    if command.strip() == "QUIT":
        break
'''))
    controller.engine.item = controller.current = {"id": "shared-game"}
    controller.engine.status = "starting"
    controller.engine.resume_on_start = False
    controller.engine.process.setProgram(sys.executable)
    controller.engine.process.setArguments([str(frontend)])

    def wait(predicate):
        deadline = time.monotonic() + 5
        while not predicate() and time.monotonic() < deadline:
            loop = QEventLoop()
            QTimer.singleShot(20, loop.quit)
            loop.exec()
        assert predicate()

    try:
        controller.engine.process.start()
        controller.engine.deadline = time.monotonic() + 5
        controller.engine.timer.start()
        assert not controller.store.data["recent"]
        if fails:
            wait(lambda: controller.engine.status == "idle")
            assert not controller.store.data["recent"] and not controller.store.data["positions"]
        else:
            wait(lambda: bool(controller.store.data["recent"]))
            assert controller.store.data["recent"] == ["shared-game"]
            assert controller.store.data["positions"]["shared-game"]["lastPlayed"] == wall[0]
            controller.store.flush()
            assert AppState("emulator", tmp_path / "state").data["positions"] == controller.store.data["positions"]
            wall[0] += 125
            controller.engine.send("GET_STATUS")
            wait(lambda: controller.engine.process.bytesToWrite() == 0)
            assert controller.store.data["positions"]["shared-game"]["lastPlayed"] != wall[0]
            controller.game_started = time.monotonic() - 125
            controller.engine.quit()
            wait(lambda: controller.engine.status == "idle")
            controller.store.flush()
            record = AppState("emulator", tmp_path / "state").data["positions"]["shared-game"]
            assert 125 <= record["seconds"] < 127 and record["lastPlayed"] == wall[0]
            assert controller.game_started is None
    finally:
        controller.close()
        application.processEvents()
