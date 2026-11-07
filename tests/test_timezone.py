import asyncio
import json
from copy import deepcopy
from types import SimpleNamespace

import pytest
from dbus_next.constants import MessageType
from PySide6.QtCore import QCoreApplication

from udeck.backend import SystemBackend
from udeck.controller import ShellController
from udeck.core import ConfigStore
from udeck.mock import MockBackend


@pytest.fixture
def controller(tmp_path):
    application = QCoreApplication.instance() or QCoreApplication([])
    instance = ShellController(MockBackend(), config=ConfigStore(tmp_path / "settings.json"), mock=True)
    instance._test_application = application
    yield instance
    instance.close()


@pytest.mark.parametrize("language,title,current", [("en", "Time zone", "Current time zone"), ("zh_CN", "时区", "当前时区")])
def test_timezone_selection_changes_system_state_keeps_focus_and_preferences(controller, language, title, current):
    controller.setLanguage(language)
    controller.setPage("settings")
    position = next(i for i, item in enumerate(controller._items()) if item["id"] == "timezone")
    controller.select(position)
    preferences = deepcopy(controller.config.data)
    controller.dispatch("accept")
    assert json.loads(controller.snapshotJson)["modal"]["title"] == title
    assert controller.modal["options"][controller.modal["index"]]["id"] == "Asia"
    controller.dispatch("accept")
    assert controller.modal["options"][controller.modal["index"]]["id"] == "Asia/Shanghai"
    assert current in json.loads(controller.snapshotJson)["modal"]["options"][controller.modal["index"]]["subtitle"]
    owner = controller.modal["key"]
    controller.chooseModal(next(i for i, item in enumerate(controller.modal["options"]) if item["id"] == "Asia/Tokyo"))
    assert controller.data["timezone"]["current"] == "Asia/Tokyo"
    assert controller.modal["key"] == owner
    assert controller.modal["options"][controller.modal["index"]]["id"] == "Asia/Tokyo"
    assert controller.config.data == preferences
    assert controller.backend.actions == ["timezone_set"]
    controller.dispatch("back")
    assert controller.modal["source"] == "timezone-areas"
    assert controller.modal["options"][controller.modal["index"]]["id"] == "Asia"
    controller.dispatch("back")
    assert not controller.modal
    assert (controller.navigation.page, controller.navigation.index) == ("settings", position)


def test_timezone_quick_settings_returns_to_the_existing_draft(controller):
    controller.dispatch("search")
    controller.editText("keep 中文 draft")
    draft = deepcopy(controller.modal)
    controller.dispatch("quick-settings")
    controller.chooseModal(next(i for i, o in enumerate(controller.modal["options"]) if o.get("id") == "timezone"))
    controller.dispatch("accept")
    controller.dispatch("back")
    controller.dispatch("back")
    assert controller.modal["source"] == "quick-settings"
    controller.dispatch("back")
    assert controller.modal == draft


def test_timezone_external_changes_and_service_loss_keep_the_selected_zone(controller):
    controller.activateSetting("timezone")
    controller.dispatch("accept")
    selected = controller.modal["options"][controller.modal["index"]]["id"]
    controller._update({"timezone": {**controller.data["timezone"], "current": "Asia/Tokyo"}})
    assert controller.modal["options"][controller.modal["index"]]["id"] == selected
    controller._update({"timezone": {**controller.data["timezone"], "available": False, "error": "service unavailable"}})
    controller.dispatch("accept")
    assert controller.backend.actions == []
    assert "service unavailable" in controller.toast


def test_pending_timezone_save_disables_repeat_submission_and_failure_restores_actual_state(controller):
    requests = []
    controller.backend.request = lambda action, payload: requests.append((action, payload))
    controller.activateSetting("timezone")
    controller.dispatch("accept")
    target = next(i for i, item in enumerate(controller.modal["options"]) if item["id"] == "Asia/Tokyo")
    controller.chooseModal(target)
    assert all(option["disabled"] for option in controller.modal["options"])
    controller.dispatch("accept")
    assert requests == [("timezone_set", {"timezone": "Asia/Tokyo"})]
    controller.backend.operationFailed.emit("timezone_set", "permission denied")
    assert not any(option["disabled"] for option in controller.modal["options"])
    assert controller.data["timezone"]["current"] == "Asia/Shanghai"
    assert controller.modal["options"][controller.modal["index"]]["id"] == "Asia/Tokyo"
    assert controller.toast == "permission denied"


@pytest.mark.parametrize("zone,area", [("Etc/UTC", "Other"), ("Europe/London", "Europe")])
def test_current_timezone_opens_its_region_and_reselecting_it_does_not_write(controller, zone, area):
    controller._update({"timezone": {**controller.data["timezone"], "current": zone}})
    controller.activateSetting("timezone")
    assert controller.modal["options"][controller.modal["index"]]["id"] == area
    controller.dispatch("accept")
    assert controller.modal["options"][controller.modal["index"]]["id"] == zone
    controller.dispatch("accept")
    assert controller.backend.actions == []


def test_clock_uses_the_selected_timezone_without_changing_process_timezone(controller):
    import os
    import time

    previous = os.environ.get("TZ"), time.tzname
    controller._update({"timezone": {**controller.data["timezone"], "current": "Etc/UTC"}})
    utc = controller.currentTime()
    controller._update({"timezone": {**controller.data["timezone"], "current": "Asia/Shanghai"}})
    shanghai = controller.currentTime()
    utc_minutes = int(utc[:2]) * 60 + int(utc[3:])
    shanghai_minutes = int(shanghai[:2]) * 60 + int(shanghai[3:])
    assert (shanghai_minutes - utc_minutes) % 1440 == 480
    assert (os.environ.get("TZ"), time.tzname) == previous


def test_timezone_backend_validates_before_setting_and_reads_back_actual_state():
    async def scenario():
        backend = SystemBackend()
        backend.loop.close()
        calls = []
        current = "Asia/Shanghai"

        async def get(*args):
            assert args[-1] == "Timezone"
            return current

        async def call(destination, path, interface, member, signature="", body=None, **options):
            nonlocal current
            calls.append((member, signature, body, options))
            if member == "ListTimezones":
                return [["Asia/Shanghai", "Asia/Tokyo", "Etc/UTC"]]
            if member == "SetTimezone":
                current = body[0]
                return []
            raise AssertionError(member)

        backend.get, backend.call = get, call
        await backend.refresh_timezone()
        assert backend.state["timezone"]["current"] == "Asia/Shanghai"
        for invalid in ("../../etc/passwd", "Made/Up", "", None, [], True):
            with pytest.raises(ValueError):
                await backend._execute("timezone_set", {"timezone": invalid})
        assert all(c[0] != "SetTimezone" for c in calls)
        await backend._execute("timezone_set", {"timezone": "Asia/Tokyo"})
        assert backend.state["timezone"]["current"] == "Asia/Tokyo"
        assert next(c[:3] for c in calls if c[0] == "SetTimezone") == ("SetTimezone", "sb", ["Asia/Tokyo", True])

    asyncio.run(scenario())


@pytest.mark.parametrize("failure", ["denied", "unchanged", "unavailable"])
def test_timezone_backend_never_reports_success_when_save_or_readback_fails(failure):
    async def scenario():
        backend = SystemBackend()
        backend.loop.close()
        unavailable = False

        async def get(*args):
            if unavailable:
                raise RuntimeError("service unavailable")
            return "Asia/Shanghai"

        async def call(destination, path, interface, member, *args, **options):
            nonlocal unavailable
            if member == "ListTimezones":
                return [["Asia/Shanghai", "Asia/Tokyo"]]
            if failure == "denied":
                raise PermissionError("permission denied")
            unavailable = failure == "unavailable"
            return []

        backend.get, backend.call = get, call
        await backend.refresh_timezone()
        with pytest.raises((RuntimeError, PermissionError)):
            await backend._execute("timezone_set", {"timezone": "Asia/Tokyo"})
        assert backend.state["timezone"]["current"] == "Asia/Shanghai"

    asyncio.run(scenario())


def test_timedated_external_updates_and_restarts_schedule_refresh():
    backend = SystemBackend()
    refreshes = []
    backend.schedule_refresh = refreshes.append
    for path, member, body in [("/org/freedesktop/timedate1", "PropertiesChanged", []),
                               ("/org/freedesktop/DBus", "NameOwnerChanged", ["org.freedesktop.timedate1", ":1.2", ""] )]:
        backend._message(SimpleNamespace(message_type=MessageType.SIGNAL, path=path, member=member, body=body, interface="org.freedesktop.DBus.Properties"))
    assert refreshes == ["timezone", "timezone"]
    backend.loop.close()
