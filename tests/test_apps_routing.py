from types import SimpleNamespace

from PySide6.QtCore import QCoreApplication, QObject, Signal

from udeck.app_routing import APP_IDS
from udeck.apps.controller import AppController
from udeck.apps.games import GamesController, content_hash
from udeck.apps.input import AppInput
from udeck.apps.library import Source, scan
from udeck.compatibility import application_profile
from udeck.terminal_routing import SuiteInputBroker


class Windows(QObject):
    changed = Signal(list)
    failed = Signal(str)


class Pointer(QObject):
    shoulder = Signal(str)


def test_suite_routes_shoulders_only_to_compositor_owner_and_invalidates_focus():
    application = QCoreApplication.instance() or QCoreApplication([])
    windows, pointer = Windows(), Pointer()
    suite = SuiteInputBroker(windows, pointer)
    sent = {identifier: [] for identifier in APP_IDS.values()}
    for identifier, broker in suite.brokers.items():
        broker.sender = lambda method, args, identifier=identifier: sent[identifier].append((method, args))
    music, reader = APP_IDS["music"], APP_IDS["reader"]
    windows.changed.emit([{"id": "1", "appId": music, "active": True}])
    pointer.shoulder.emit("next-page")
    assert sent[music][-1] == ("Shoulder", [1, "next-tab"])
    assert not sent[reader]
    windows.changed.emit([{"id": "1", "appId": music, "active": False},
                          {"id": "2", "appId": reader, "active": True}])
    pointer.shoulder.emit("previous-page")
    assert sent[music][-1] == ("Route", [2, False])
    assert sent[reader][-1] == ("Shoulder", [1, "previous-tab"])
    windows.failed.emit("compositor gone")
    assert not suite.state(reader)["enabled"]
    assert not suite.state("unrecognized.app")["available"]
    assert all(application_profile(identifier)["mode"] == "native" for identifier in APP_IDS.values())
    assert application


def test_app_input_rechecks_window_focus_and_rejects_stale_generations():
    application = QCoreApplication.instance() or QCoreApplication([])
    actions, active = [], True
    controller = QObject()
    controller.window = SimpleNamespace(isActive=lambda: active)
    controller.dispatch = actions.append
    inputs = AppInput(controller, APP_IDS["reader"], {})
    inputs.foreground = True
    inputs.route(5, True)
    inputs.shoulder(4, "next-tab")
    assert not actions
    inputs.shoulder(5, "next-tab")
    active = False
    inputs.shoulder(5, "previous-tab")
    inputs.route(6, False)
    inputs.route(5, True)
    assert actions == ["next-tab"] and not inputs.routed
    inputs.close()
    assert application


def test_nested_menus_skip_disabled_rows_and_preserve_parent_focus_and_draft(tmp_path):
    application = QCoreApplication.instance() or QCoreApplication([])
    controller = AppController("browser", tmp_path, tmp_path / "settings.json")
    called = []
    controller.menu("Parent", [("Disabled", None), ("Child", lambda: controller.menu("Child", []))])
    controller.choose(0)
    assert len(controller.menus) == 1
    controller.choose(1)
    assert controller.menus[-1]["title"] == "Child"
    controller.dispatch("back")
    assert controller.menus[-1]["title"] == "Parent" and controller.menus[-1]["index"] == 1
    controller.prompt("Text", called.append, "abxy 中文")
    controller.set_language("zh_CN")
    assert controller.menus[-1]["draft"] == "abxy 中文"
    controller.dispatch("next-tab")
    assert controller.menus[-1]["draft"] == "abxy 中文"
    controller.submit("hello")
    assert called == ["hello"] and controller.menus[-1]["title"] == "Parent"
    controller.close()
    assert application


def test_library_refresh_retains_stable_focus_and_removed_item_selects_neighbor(tmp_path):
    application = QCoreApplication.instance() or QCoreApplication([])
    controller = AppController("reader", tmp_path, tmp_path / "settings.json")
    controller.library.items = [{"id": key, "sourceId": "card", "title": key, "format": "TXT", "folder": "/books"}
                                for key in ("a", "b", "c")]
    controller.selected = "b"
    assert controller.snapshot()["selected"] == "b"
    controller.library.items.insert(0, {**controller.library.items[0], "id": "z"})
    assert controller.snapshot()["selected"] == "b"
    controller.library.items = [i for i in controller.library.items if i["id"] != "b"]
    assert controller.snapshot()["selected"] == "c"
    controller.close()
    assert application


def test_loaded_game_resumes_and_source_loss_disables_save_and_load(tmp_path):
    application = QCoreApplication.instance() or QCoreApplication([])
    controller = GamesController(tmp_path, tmp_path / "settings.json")
    commands, minimized = [], []
    controller.engine.status = "paused"
    controller.engine.send = commands.append
    controller.window = SimpleNamespace(showMinimized=lambda: minimized.append(True))
    controller.menu("Confirm load", [("Confirm", lambda: None)])
    controller.load_done()
    assert commands == ["PAUSE_TOGGLE"] and minimized == [True] and not controller.menus
    controller.engine.running = lambda: True
    controller.source_missing = True
    controller.pause_menu()
    assert [row["disabled"] for row in controller.menus[-1]["options"]][:3] == [True, True, True]
    controller.engine.running = lambda: False
    controller.close()
    assert application


def test_reconnecting_same_game_source_reenables_resume_without_starting_new_game(tmp_path):
    application = QCoreApplication.instance() or QCoreApplication([])
    card = tmp_path / "card"
    card.mkdir()
    (card / "original.gb").write_bytes(b"original fixture content")
    source = Source.create(card)
    controller = GamesController(tmp_path / "state", tmp_path / "settings.json")
    controller.library.sources = [source]
    controller.library.items = scan(source, "games")
    controller.current = controller.library.items[0]
    controller.engine.metadata = {"contentHash": content_hash(controller.current)}
    controller.engine.status = "paused"
    controller.engine.running = lambda: True
    detached = tmp_path / "detached"
    card.rename(detached)
    controller.library.check_sources()
    assert controller.source_missing and controller.menus[-1]["options"][0]["disabled"]
    detached.rename(card)
    controller.poll()
    assert not controller.source_missing and not controller.menus[-1]["options"][0]["disabled"]
    assert controller.engine.status == "paused"
    controller.engine.running = lambda: False
    controller.close()
    assert application
