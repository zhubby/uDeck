import asyncio
import json
import os
from copy import deepcopy

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication

from udeck.backend import SystemBackend
from udeck.controller import ShellController
from udeck.core import ConfigStore
from udeck.i18n import Msg, error_text
from udeck.mock import MockBackend


def node(name, description, *, bluetooth=False, volume=32768, **values):
    return {"name": name, "description": description, "mute": False,
            "volume": {"mono": {"value": volume, "value_percent": "50%"}},
            "properties": {"device.api": "bluez5" if bluetooth else "alsa",
                           "device.name": "bluez_card.headset" if bluetooth else "alsa_card.usb"}, **values}


@pytest.fixture
def audio_server():
    backend = SystemBackend()
    state = {
        "sinks": [node("speaker", "Speaker"), node("bluez_output.headset", "Studio headset", bluetooth=True)],
        "sources": [node("speaker.monitor", "Monitor of Speaker", monitor_of_sink=57),
                    node("usb-mic", "USB microphone", monitor_of_sink="n/a"),
                    node("bluez_input.headset", "Studio headset microphone", bluetooth=True, monitor_of_sink=4294967295)],
        "cards": [{"index": 9, "name": "bluez_card.headset", "properties": {"device.api": "bluez5", "device.description": "Studio headset"},
                   "active_profile": "a2dp-sink", "profiles": {
                       "off": {"description": "Off", "sinks": 0, "sources": 0, "available": True},
                       "a2dp-sink": {"description": "A2DP SBC", "sinks": 1, "sources": 0, "available": True},
                       "headset-head-unit": {"description": "HFP mSBC", "sinks": 1, "sources": 1, "available": "yes"},
                       "headset-head-unit-cvsd": {"description": "HFP CVSD", "sinks": 1, "sources": 1, "available": "no"}}}],
        "default-sink": "speaker", "default-source": "usb-mic", "fail": set(),
    }
    commands = []

    async def command(*args, **kwargs):
        commands.append(args)
        if args == ("wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@"):
            return "Volume: 0.50"
        if args[:3] == ("pactl", "--format=json", "list"):
            if args[3] in state["fail"]:
                raise RuntimeError("Device service read failed")
            return json.dumps(state[args[3]])
        if args[:1] == ("pactl",) and args[1].startswith("get-default-"):
            return state[args[1][4:]]
        if args[:2] in (("pactl", "set-default-source"), ("pactl", "set-default-sink")):
            state["default-" + args[1].removeprefix("set-default-")] = args[2]
            return ""
        if args[:2] in (("pactl", "set-source-volume"), ("pactl", "set-sink-volume")):
            entries = state["sources" if args[1] == "set-source-volume" else "sinks"]
            target = next(entry for entry in entries if entry["name"] == args[2])
            target["volume"] = {"mono": {"value": round(float(args[3].removesuffix("%")) / 100 * 65536)}}
            return ""
        if args[:2] in (("pactl", "set-source-mute"), ("pactl", "set-sink-mute")):
            entries = state["sources" if args[1] == "set-source-mute" else "sinks"]
            target = next(entry for entry in entries if entry["name"] == args[2])
            target["mute"] = not target["mute"]
            return ""
        if args[:2] == ("pactl", "set-card-profile"):
            next(card for card in state["cards"] if card["name"] == args[2])["active_profile"] = args[3]
            return ""
        raise AssertionError(args)

    backend.command = command
    yield backend, state, commands
    backend.loop.close()


def test_microphone_enumeration_excludes_monitors_and_marks_bluetooth(audio_server):
    backend, _, _ = audio_server
    asyncio.run(backend.refresh_audio())
    audio = backend.state["audio"]
    assert [source["id"] for source in audio["inputs"]] == ["usb-mic", "bluez_input.headset"]
    assert [source["active"] for source in audio["inputs"]] == [True, False]
    assert audio["inputs"][1]["bluetooth"] is True
    assert audio["outputs"][1]["bluetooth"] is True
    assert audio["inputs"][1]["cardId"] == "bluez_card.headset"
    assert audio["inputs"][0]["volume"] == pytest.approx(0.5)


def test_audio_subscription_ignores_query_clients_but_keeps_device_changes(monkeypatch):
    backend = SystemBackend()
    refreshes, launches = [], []
    backend.schedule_refresh = refreshes.append
    monkeypatch.setenv("LC_ALL", "zh_CN.UTF-8")

    async def exercise():
        reader = asyncio.StreamReader()
        reader.feed_data(b"Event 'new' on client #10\nEvent 'change' on client #10\n"
                         b"Event 'remove' on client #10\nEvent 'change' on sink #1\n"
                         b"Event 'new' on source #2\nEvent 'remove' on card #3\n"
                         b"Event 'change' on server #4294967295\n"
                         b"Event 'change' on sink-input #4\nEvent 'change' on source-output #5\n"
                         b"Event 'new' on module #6\nEvent 'remove' on sample-cache #7\n")
        reader.feed_eof()

        class Process:
            stdout = reader
            returncode = None

            def kill(self):
                self.returncode = -9

            async def wait(self):
                return self.returncode

        process = Process()

        async def launch(*arguments, **options):
            launches.append((arguments, options))
            return process

        monkeypatch.setattr(asyncio, "create_subprocess_exec", launch)
        await backend._watch_audio()
        assert process.returncode == -9 and not backend.processes

    try:
        asyncio.run(exercise())
        assert refreshes == ["audio"] * 4, refreshes
        arguments, options = launches[0]
        assert arguments == ("pactl", "subscribe")
        assert options["env"]["LC_ALL"] == "C"
        assert os.environ["LC_ALL"] == "zh_CN.UTF-8"
    finally:
        backend.loop.close()


def test_bluetooth_profiles_preserve_availability_and_microphone_capability(audio_server):
    backend, _, _ = audio_server
    asyncio.run(backend.refresh_audio())
    cards = backend.state["audio"]["cards"]
    assert len(cards) == 1
    profiles = {profile["id"]: profile for profile in cards[0]["profiles"]}
    assert "off" not in profiles
    assert profiles["a2dp-sink"]["microphone"] is False
    assert profiles["a2dp-sink"]["active"] is True
    assert profiles["headset-head-unit"]["microphone"] is True
    assert profiles["headset-head-unit"]["available"] is True
    assert profiles["headset-head-unit-cvsd"]["available"] is False


def test_input_read_failure_keeps_output_controls_available(audio_server):
    backend, server, _ = audio_server
    server["fail"].add("sources")
    asyncio.run(backend.refresh_audio())
    assert backend.state["audio"]["available"] is True
    assert backend.state["audio"]["outputs"][0]["id"] == "speaker"
    assert backend.state["audio"]["inputs"] == []
    assert backend.state["audio"]["inputError"]


def test_card_name_matching_does_not_assign_unrelated_inputs_to_bluetooth(audio_server):
    backend, server, _ = audio_server
    server["cards"][0].pop("index")
    asyncio.run(backend.refresh_audio())
    inputs = {source["id"]: source for source in backend.state["audio"]["inputs"]}
    assert inputs["usb-mic"]["bluetooth"] is False
    assert inputs["usb-mic"]["cardId"] == ""
    assert inputs["bluez_input.headset"]["cardId"] == "bluez_card.headset"


@pytest.mark.parametrize(("action", "target", "expected"), [
    ("audio_output", "bluez_output.headset", ("pactl", "set-default-sink", "bluez_output.headset")),
    ("audio_input", "bluez_input.headset", ("pactl", "set-default-source", "bluez_input.headset")),
    ("audio_input_volume", "usb-mic", ("pactl", "set-source-volume", "usb-mic", "35%")),
    ("audio_input_mute", "usb-mic", ("pactl", "set-source-mute", "usb-mic", "toggle")),
])
def test_audio_operations_target_the_selected_endpoint_and_refresh_actual_state(audio_server, action, target, expected):
    backend, _, commands = audio_server
    asyncio.run(backend._execute(action, {"id": target, "value": 0.35}))
    assert expected in commands
    audio = backend.state["audio"]
    if action in ("audio_output", "audio_input"):
        entries = audio["outputs" if action == "audio_output" else "inputs"]
        assert next(entry for entry in entries if entry["active"])["id"] == target
    elif action == "audio_input_volume":
        assert audio["inputs"][0]["volume"] == pytest.approx(0.35, abs=0.001)
    else:
        assert audio["inputs"][0]["muted"] is True


@pytest.mark.parametrize(("action", "kind", "target"), [
    ("audio_output", "sinks", "bluez_output.headset"),
    ("audio_input", "sources", "bluez_input.headset"),
    ("audio_input_volume", "sources", "bluez_input.headset"),
    ("audio_input_mute", "sources", "bluez_input.headset"),
])
def test_removed_endpoint_is_rechecked_before_any_audio_write(audio_server, action, kind, target):
    backend, server, commands = audio_server
    asyncio.run(backend.refresh_audio())
    server[kind] = [entry for entry in server[kind] if entry["name"] != target]
    with pytest.raises((ValueError, RuntimeError)) as failure:
        asyncio.run(backend._execute(action, {"id": target, "value": 0.5}))
    assert error_text(failure.value).key == Msg.THE_AUDIO_DEVICE_WAS_REMOVED
    assert not any(args[0] == "pactl" and args[1].startswith("set-") for args in commands)


def test_bluetooth_profile_change_uses_card_identity_and_checks_observed_mode(audio_server):
    backend, _, commands = audio_server
    asyncio.run(backend._execute("audio_profile", {"id": "bluez_card.headset", "profile": "headset-head-unit"}))
    assert ("pactl", "set-card-profile", "bluez_card.headset", "headset-head-unit") in commands
    card = backend.state["audio"]["cards"][0]
    assert next(profile for profile in card["profiles"] if profile["active"])["id"] == "headset-head-unit"


@pytest.mark.parametrize("profile", ["off", "headset-head-unit-cvsd", "missing"])
def test_unavailable_bluetooth_profile_cannot_be_applied(audio_server, profile):
    backend, _, commands = audio_server
    with pytest.raises((ValueError, RuntimeError), match="Bluetooth audio mode is unavailable"):
        asyncio.run(backend._execute("audio_profile", {"id": "bluez_card.headset", "profile": profile}))
    assert not any(args[:2] == ("pactl", "set-card-profile") for args in commands)


@pytest.fixture
def controller(tmp_path, audio_server):
    application = QCoreApplication.instance() or QCoreApplication([])
    system, _, _ = audio_server
    asyncio.run(system.refresh_audio())
    backend = MockBackend()
    backend.state["audio"] = deepcopy(system.state["audio"])
    instance = ShellController(backend, config=ConfigStore(tmp_path / "settings.json"), mock=True)
    instance._test_application = application
    yield instance
    instance.close()


def test_microphone_controls_are_reachable_from_settings_and_quick_settings(controller):
    controller.setPage("settings")
    settings = json.loads(controller.snapshotJson)["items"]
    assert next(item for item in settings if item["id"] == "microphone")["subtitle"] == "USB microphone"
    controller.dispatch("quick-settings")
    controller.chooseModal(next(i for i, option in enumerate(controller.modal["options"]) if option.get("id") == "microphone"))
    assert controller.modal["source"] == "audio-input"
    assert any(option.get("systemAction") == "audio_input" for option in controller.modal["options"])


def test_output_menu_marks_bluetooth_and_stays_open_after_a_selection(controller):
    controller.activateSetting("output")
    state = json.loads(controller.snapshotJson)["modal"]
    position = next(i for i, option in enumerate(state["options"]) if option.get("id") == "bluez_output.headset")
    assert "Bluetooth" in state["options"][position]["subtitle"]
    key = controller.modal["key"]
    controller.chooseModal(position)
    assert controller.modal["key"] == key
    assert next(output for output in controller.data["audio"]["outputs"] if output["active"])["id"] == "bluez_output.headset"


def test_microphone_level_retains_its_target_when_the_system_default_changes(controller):
    controller.activateSetting("microphone")
    controller.chooseModal(next(i for i, option in enumerate(controller.modal["options"]) if option.get("id") == "input-level"))
    assert controller.modal["kind"] == "slider"
    audio = deepcopy(controller.data["audio"])
    for source in audio["inputs"]:
        source["active"] = source["id"] == "bluez_input.headset"
    controller.backend.state["audio"] = audio
    controller.backend.updated.emit({"audio": audio})
    controller.dispatch("right")
    controller.dispatch("accept")
    inputs = {source["id"]: source for source in controller.data["audio"]["inputs"]}
    assert inputs["usb-mic"]["volume"] == pytest.approx(0.55)
    assert inputs["bluez_input.headset"]["volume"] == pytest.approx(0.5)
    assert controller.modal["source"] == "audio-input"


def test_profile_switch_requires_confirmation_and_can_be_cancelled(controller):
    controller.activateSetting("audio-modes")
    controller.chooseModal(0)
    controller.chooseModal(next(i for i, option in enumerate(controller.modal["options"]) if option.get("id") == "headset-head-unit"))
    assert controller.modal["kind"] == "confirm"
    assert controller.modal["index"] == 0
    controller.dispatch("accept")
    assert "audio_profile" not in controller.backend.actions
    assert controller.modal["source"] == "audio-profiles"


def test_disconnecting_a_bluetooth_card_closes_only_its_profile_dialogs(controller):
    controller.setPage("settings")
    controller.activateSetting("audio-modes")
    owner = controller.modal["key"]
    controller.chooseModal(0)
    controller.chooseModal(next(i for i, option in enumerate(controller.modal["options"]) if option.get("id") == "headset-head-unit"))
    audio = deepcopy(controller.data["audio"])
    audio["cards"] = []
    controller.backend.updated.emit({"audio": audio})
    assert controller.modal["key"] == owner
    assert controller.modal["source"] == "audio-cards"
    assert "audio_profile" not in controller.backend.actions


def test_powering_off_mock_bluetooth_removes_audio_and_connected_state(tmp_path):
    application = QCoreApplication.instance() or QCoreApplication([])
    backend = MockBackend()
    backend.request("bluetooth_power", {"enabled": False})
    assert not any(device["connected"] for device in backend.state["bluetooth"]["devices"])
    assert backend.state["audio"]["cards"] == []
    assert not any(source.get("bluetooth") for source in backend.state["audio"]["inputs"])
    application.processEvents()


def test_input_disappearing_during_level_adjustment_does_not_change_another_microphone(controller):
    controller.activateSetting("microphone")
    owner = controller.modal["key"]
    controller.chooseModal(next(i for i, option in enumerate(controller.modal["options"]) if option.get("id") == "input-level"))
    audio = deepcopy(controller.backend.state["audio"])
    audio["inputs"] = [source for source in audio["inputs"] if source["id"] != "usb-mic"]
    audio["inputs"][0]["active"] = True
    controller.backend.state["audio"] = audio
    controller.backend.updated.emit({"audio": audio})
    assert controller.modal["key"] == owner
    assert controller.modal["source"] == "audio-input"
    assert "audio_input_volume" not in controller.backend.actions
    assert controller.data["audio"]["inputs"][0]["volume"] == pytest.approx(0.5)
