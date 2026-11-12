"""Exercise real hotspot operations across the external NetworkManager boundary."""

import asyncio
import json
import time
from copy import deepcopy

import pytest
from test_wifi import ACTIVE, BUILTIN, NM, NM_ROOT, PROFILE, USB
from test_wifi_management import ProfileManager

from udeck.backend import SystemBackend, unwrap
from udeck.hotspot import hotspot_summary
from udeck.i18n import render
from udeck.wifi import wifi_indicators, wifi_summary


class HotspotManager(ProfileManager):
    def __init__(self):
        super().__init__()
        self.auto_activate = True
        self.hotspot_activation_states = {}
        self.deny = ""
        self.next_id = 10
        for index, path in enumerate((BUILTIN, USB), 1):
            self.wireless[path].update(Mode=2, WirelessCapabilities=0x68,
                                       PermHwAddress=f"00:11:22:33:44:{index:02x}")

    async def call(self, destination, path, interface, member, signature="", body=None, **options):
        if member == self.deny:
            raise RuntimeError("permission denied")
        if member == "AddConnection":
            self.next_id += 1
            target = NM_ROOT + f"/Settings/{self.next_id}"
            self.profiles[target] = unwrap(deepcopy(body[0]))
            self.calls.append((path, member, unwrap(body)))
            return [target]
        if member == "ActivateConnection":
            self.calls.append((path, member, unwrap(body)))
            profile, device, _ = body
            self.next_id += 1
            active = NM_ROOT + f"/ActiveConnection/{self.next_id}"
            old = self.devices[device]["ActiveConnection"]
            self.active.pop(old, None)
            ap = self.profiles[profile]["802-11-wireless"].get("mode") == "ap"
            state = 100 if self.auto_activate else 50
            if ap:
                state = self.hotspot_activation_states.get(device, state)
            self.active[active] = {"Connection": profile, "Devices": [device], "State": 2 if state == 100 else 1}
            self.devices[device].update(ActiveConnection=active, State=state)
            self.wireless[device].update(Mode=3 if ap else 2, ActiveAccessPoint="/")
            return [active]
        if member == "DeactivateConnection":
            devices = self.active[body[0]]["Devices"]
            result = await super().call(destination, path, interface, member, signature, body, **options)
            for device in devices:
                self.wireless[device]["Mode"] = 2
            return result
        return await super().call(destination, path, interface, member, signature, body, **options)


@pytest.fixture
def hotspot_backend():
    backend, manager = SystemBackend(), HotspotManager()
    backend.call, backend.get, backend.properties = manager.call, manager.get, manager.properties
    yield backend, manager
    backend.loop.close()


def device(backend, identifier=USB):
    return next(item for item in backend.state["wifi"]["devices"] if item["id"] == identifier)


async def configure(backend, identifier=USB, **values):
    await backend.refresh_wifi()
    hotspot = device(backend, identifier).get("hotspot", {})
    await backend._execute("wifi_hotspot_configure", {
        "deviceId": identifier, "ssid": "Pocket network", "password": "test-only-password",
        "revision": hotspot.get("revision", ""), **values})


async def settle(backend):
    for _ in range(100):
        await asyncio.sleep(0.005)
        if not any(not task.done() for task in getattr(backend, "hotspot_tasks", {}).values()):
            await backend.refresh_wifi()
            return
    raise AssertionError("Hotspot task did not settle")


async def start(backend, identifier=USB):
    hotspot = device(backend, identifier)["hotspot"]
    await backend._execute("wifi_hotspot_start", {"deviceId": identifier,
                          "revision": hotspot["revision"],
                          "expectedActive": device(backend, identifier).get("activeConnection", "/")})
    await settle(backend)


async def stop(backend, identifier=USB):
    hotspot = device(backend, identifier)["hotspot"]
    await backend._execute("wifi_hotspot_stop", {"deviceId": identifier,
                          "operationId": hotspot["operationId"], "activePath": hotspot["activePath"]})
    await settle(backend)


def test_ap_profile_is_bound_shared_manual_and_reused_without_client_profile_changes(hotspot_backend):
    backend, manager = hotspot_backend
    original = deepcopy(manager.profiles[PROFILE])

    async def scenario():
        await configure(backend)
        item = device(backend)
        assert item["apSupported"] is True
        assert item["hotspot"]["configured"]
        assert device(backend, BUILTIN)["saved"][0]["uuid"] == "known"
        assert item["saved"] == []
        path = next(path for path in manager.profiles if path != PROFILE)
        profile = manager.profiles[path]
        assert profile["connection"]["autoconnect"] is False
        assert "interface-name" not in profile["connection"]  # Bind permanent hardware, not transient numbering.
        assert profile["802-11-wireless"]["mode"] == "ap"
        assert bytes(profile["802-11-wireless"]["mac-address"]) == bytes.fromhex("001122334402")
        assert profile["ipv4"]["method"] == "shared"
        assert profile["ipv6"]["method"] == "disabled"
        assert profile["802-11-wireless-security"]["proto"] == ["rsn"]
        assert profile["802-11-wireless-security"]["pairwise"] == ["ccmp"]
        assert "test-only-password" not in json.dumps(backend.state)
        await configure(backend, ssid="Renamed", password="another-test-password")
        assert len(manager.profiles) == 2
        assert manager.profiles[PROFILE] == original
        assert not any(call[1] == "GetSecrets" for call in manager.calls)
    asyncio.run(scenario())


def test_client_and_hotspot_have_distinct_indicators_and_connection_counts(hotspot_backend):
    backend, manager = hotspot_backend

    async def scenario():
        await configure(backend)
        await start(backend)
        assert device(backend)["hotspot"]["status"] == "active"
        assert manager.devices[BUILTIN]["ActiveConnection"] == ACTIVE
        indicators = wifi_indicators(backend.state["wifi"])
        assert [item["kind"] for item in indicators] == ["wifi", "hotspot"]
        assert indicators[1]["strength"] is None
        assert render(wifi_summary(backend.state["wifi"]), "en") == "2 adapters · 1 connected"
        await stop(backend)
        assert device(backend)["hotspot"]["status"] == "off"
    asyncio.run(scenario())


def test_multiple_hotspots_and_restoration_touch_only_the_selected_adapter(hotspot_backend):
    backend, manager = hotspot_backend

    async def scenario():
        await configure(backend, BUILTIN)
        await configure(backend)
        await start(backend, BUILTIN)
        await start(backend)
        usb_active = manager.devices[USB]["ActiveConnection"]
        await stop(backend, BUILTIN)
        assert manager.devices[USB]["ActiveConnection"] == usb_active
        restored = manager.devices[BUILTIN]["ActiveConnection"]
        assert manager.active[restored]["Connection"] == PROFILE
        assert device(backend, BUILTIN)["hotspot"]["status"] == "off"
    asyncio.run(scenario())


@pytest.mark.parametrize("metadata", ["timestamp", "seen-bssids", "both"])
def test_automatic_profile_metadata_updates_do_not_block_original_wifi_restoration(hotspot_backend, metadata):
    backend, manager = hotspot_backend
    manager.profiles[PROFILE]["connection"].update(autoconnect=False, timestamp=1000)
    manager.profiles[PROFILE]["802-11-wireless"]["seen-bssids"] = ["00:11:22:33:44:55"]
    original_call = manager.call

    async def service(destination, path, interface, member, signature="", body=None, **options):
        if (member == "ActivateConnection" and body[1] == BUILTIN
                and manager.profiles[body[0]]["802-11-wireless"].get("mode") == "ap"):
            # NM returns updated runtime metadata without changing VersionId.
            if metadata in ("timestamp", "both"):
                manager.profiles[PROFILE]["connection"]["timestamp"] = 1001
            if metadata in ("seen-bssids", "both"):
                manager.profiles[PROFILE]["802-11-wireless"]["seen-bssids"].append("00:11:22:33:44:66")
        return await original_call(destination, path, interface, member, signature, body, **options)

    backend.call = service

    async def scenario():
        await configure(backend)
        await start(backend)
        other_active = manager.devices[USB]["ActiveConnection"]
        await configure(backend, BUILTIN)
        await start(backend, BUILTIN)
        await stop(backend, BUILTIN)
        restored = manager.devices[BUILTIN]["ActiveConnection"]
        assert restored != "/"
        assert manager.active[restored]["Connection"] == PROFILE
        assert device(backend, BUILTIN)["hotspot"]["status"] == "off"
        assert manager.profiles[PROFILE]["connection"]["autoconnect"] is False
        assert manager.versions[PROFILE] == 1
        assert manager.devices[USB]["ActiveConnection"] == other_active

    asyncio.run(scenario())


@pytest.mark.parametrize("change", ["settings", "secret-version"])
def test_original_wifi_configuration_changes_still_block_restoration(hotspot_backend, change):
    backend, manager = hotspot_backend

    async def scenario():
        await configure(backend)
        await start(backend)
        other_active = manager.devices[USB]["ActiveConnection"]
        await configure(backend, BUILTIN)
        await start(backend, BUILTIN)
        if change == "settings":
            manager.profiles[PROFILE]["ipv4"]["address-data"][0]["address"] = "10.8.0.3"
        else:
            # Secret edits need not change GetSettings, but must change VersionId.
            manager.versions[PROFILE] += 1
        await stop(backend, BUILTIN)
        item = device(backend, BUILTIN)
        assert item["activeConnection"] == "/"
        assert item["hotspot"]["status"] == "failed"
        assert "configuration changed" in render(item["hotspot"]["message"], "en")
        assert manager.devices[USB]["ActiveConnection"] == other_active

    asyncio.run(scenario())


def test_activation_request_does_not_report_success_before_device_activation(hotspot_backend):
    backend, manager = hotspot_backend

    async def scenario():
        await configure(backend)
        manager.auto_activate = False
        hotspot = device(backend)["hotspot"]
        await backend._execute("wifi_hotspot_start", {"deviceId": USB, "revision": hotspot["revision"], "expectedActive": "/"})
        await asyncio.sleep(0.02)
        await backend.refresh_wifi()
        assert device(backend)["hotspot"]["status"] == "starting"
        manager.devices[USB]["State"] = 100
        manager.active[manager.devices[USB]["ActiveConnection"]]["State"] = 2
        await settle(backend)
        assert device(backend)["hotspot"]["status"] == "active"
    asyncio.run(scenario())


@pytest.mark.parametrize("cause", ["unsupported", "unknown-hardware", "stale", "permission"])
def test_unavailable_or_stale_configuration_cannot_activate_or_change_another_adapter(hotspot_backend, cause):
    backend, manager = hotspot_backend

    async def scenario():
        await configure(backend)
        if cause == "unsupported":
            manager.wireless[USB]["WirelessCapabilities"] = 0x28
        elif cause == "unknown-hardware":
            manager.wireless[USB]["PermHwAddress"] = ""
        elif cause == "permission":
            manager.deny = "ActivateConnection"
        target = {"deviceId": USB, "revision": "stale" if cause == "stale" else device(backend)["hotspot"]["revision"], "expectedActive": "/"}
        try:
            await backend._execute("wifi_hotspot_start", target)
        except RuntimeError:
            pass
        await settle(backend)
        assert not any(active["Devices"] == [USB] for active in manager.active.values())
        assert manager.devices[BUILTIN]["ActiveConnection"] == ACTIVE
        assert device(backend)["hotspot"]["status"] != "active"
    asyncio.run(scenario())


def test_external_replacement_is_never_stopped_by_a_stale_hotspot_request(hotspot_backend):
    backend, manager = hotspot_backend

    async def scenario():
        await configure(backend)
        await start(backend)
        old = deepcopy(device(backend)["hotspot"])
        replacement = NM_ROOT + "/ActiveConnection/999"
        manager.devices[USB].update(ActiveConnection=replacement, State=100)
        manager.wireless[USB]["Mode"] = 2
        manager.active[replacement] = {"Connection": PROFILE, "Devices": [USB], "State": 2}
        before = len(manager.calls)
        with pytest.raises(RuntimeError):
            await backend._execute("wifi_hotspot_stop", {"deviceId": USB, "operationId": old["operationId"], "activePath": old["activePath"]})
        assert manager.devices[USB]["ActiveConnection"] == replacement
        assert not any(call[1] in ("DeactivateConnection", "ActivateConnection") for call in manager.calls[before:])
    asyncio.run(scenario())


@pytest.mark.parametrize(("activation_state", "poll_delay"), [(50, 0), (50, 0.06), (120, 0)])
def test_start_failure_restores_the_original_wifi_and_preserves_the_other_hotspot(hotspot_backend, monkeypatch, activation_state, poll_delay):
    backend, manager = hotspot_backend
    original_sleep = asyncio.sleep
    delayed = False

    async def delayed_poll(delay, result=None):
        nonlocal delayed
        await original_sleep(delay)
        if (poll_delay and not delayed and delay == backend.hotspot_poll_interval
                and manager.devices[BUILTIN]["State"] == 50 and manager.wireless[BUILTIN]["Mode"] == 3):
            delayed = True
            time.sleep(poll_delay)
        return result

    monkeypatch.setattr(asyncio, "sleep", delayed_poll)

    async def scenario():
        backend.hotspot_poll_interval = 0.005
        backend.hotspot_timeout = 0.03
        await configure(backend)
        await start(backend)
        usb = manager.devices[USB]["ActiveConnection"]
        await configure(backend, BUILTIN)
        manager.hotspot_activation_states[BUILTIN] = activation_state
        await backend._execute("wifi_hotspot_start", {"deviceId": BUILTIN,
                              "revision": device(backend, BUILTIN)["hotspot"]["revision"], "expectedActive": ACTIVE})
        await settle(backend)
        assert device(backend, BUILTIN)["hotspot"]["status"] == "failed"
        assert manager.active[manager.devices[BUILTIN]["ActiveConnection"]]["Connection"] == PROFILE
        assert device(backend, BUILTIN)["deviceState"] == 100
        assert device(backend, BUILTIN)["mode"] == "infrastructure"
        assert device(backend, BUILTIN)["activeProfileUuid"] == "known"
        assert device(backend, BUILTIN)["connected"] == "Workshop"
        assert wifi_indicators(backend.state["wifi"])[0]["kind"] == "wifi"
        assert manager.devices[USB]["ActiveConnection"] == usb
        assert device(backend, USB)["hotspot"]["status"] == "active"
        assert not poll_delay or delayed
    asyncio.run(scenario())


@pytest.mark.parametrize("cause", ["deleted", "occupied", "stop-denied"])
def test_stop_reports_restore_failure_without_changing_other_connections(hotspot_backend, cause):
    backend, manager = hotspot_backend

    async def scenario():
        await configure(backend, BUILTIN)
        await start(backend, BUILTIN)
        if cause == "deleted":
            del manager.profiles[PROFILE]
        elif cause == "occupied":
            other = NM_ROOT + "/ActiveConnection/900"
            manager.active[other] = {"Connection": PROFILE, "Devices": [USB], "State": 2}
            manager.devices[USB].update(ActiveConnection=other, State=100)
        else:
            manager.deny = "DeactivateConnection"
        before = manager.devices[USB]["ActiveConnection"]
        await stop(backend, BUILTIN)
        assert device(backend, BUILTIN)["hotspot"]["status"] == "failed"
        message = render(device(backend, BUILTIN)["hotspot"]["message"], "en")
        if cause == "deleted":
            assert "removed" in message
        elif cause == "occupied":
            assert "another adapter" in message
        else:
            assert "Could not stop hotspot" in message
        assert manager.devices[USB]["ActiveConnection"] == before
        if cause == "stop-denied":
            assert manager.wireless[BUILTIN]["Mode"] == 3
    asyncio.run(scenario())


@pytest.mark.parametrize("takeover", ["client", "hotspot", "client-then-hotspot"])
def test_external_takeover_clears_failed_operation_and_stale_restoration(hotspot_backend, takeover):
    backend, manager = hotspot_backend

    async def scenario():
        await configure(backend)
        await start(backend)
        other_active = manager.devices[USB]["ActiveConnection"]
        await configure(backend, BUILTIN)
        await start(backend, BUILTIN)
        hotspot_profile = manager.active[manager.devices[BUILTIN]["ActiveConnection"]]["Connection"]
        manager.deny = "DeactivateConnection"
        await stop(backend, BUILTIN)
        failed = device(backend, BUILTIN)["hotspot"]
        stale_request = {"deviceId": BUILTIN, "operationId": failed["operationId"], "activePath": failed["activePath"]}
        manager.deny = ""
        if takeover != "hotspot":
            guest = NM_ROOT + "/Settings/999"
            manager.profiles[guest] = deepcopy(manager.profiles[PROFILE])
            manager.profiles[guest]["connection"].update(uuid="guest-wifi", id="Guest network")
            manager.profiles[guest]["802-11-wireless"]["ssid"] = list(b"Guest network")
            await manager.call(NM, NM_ROOT, NM, "ActivateConnection", "ooo", [guest, BUILTIN, "/"])
            await backend.refresh_wifi()
        if takeover != "client":
            await manager.call(NM, NM_ROOT, NM, "ActivateConnection", "ooo", [hotspot_profile, BUILTIN, "/"])
            await backend.refresh_wifi()
        replacement = manager.devices[BUILTIN]["ActiveConnection"]
        assert BUILTIN not in backend.hotspot_operations
        assert device(backend, BUILTIN)["hotspot"]["status"] == ("off" if takeover == "client" else "active")
        with pytest.raises(RuntimeError):
            await backend._execute("wifi_hotspot_stop", stale_request)
        assert manager.devices[BUILTIN]["ActiveConnection"] == replacement
        if takeover != "client":
            await stop(backend, BUILTIN)
            assert manager.devices[BUILTIN]["ActiveConnection"] == "/"
        assert manager.devices[USB]["ActiveConnection"] == other_active

    asyncio.run(scenario())


def test_failed_stop_retry_preserves_restoration_while_the_same_hotspot_is_active(hotspot_backend):
    backend, manager = hotspot_backend

    async def scenario():
        await configure(backend, BUILTIN)
        await start(backend, BUILTIN)
        manager.deny = "DeactivateConnection"
        await stop(backend, BUILTIN)
        await backend.refresh_wifi()
        assert device(backend, BUILTIN)["hotspot"]["status"] == "failed"
        manager.deny = ""
        await stop(backend, BUILTIN)
        assert manager.active[manager.devices[BUILTIN]["ActiveConnection"]]["Connection"] == PROFILE
        assert device(backend, BUILTIN)["hotspot"]["status"] == "off"

    asyncio.run(scenario())


@pytest.mark.parametrize("running_count", [1, 2])
def test_failed_stop_summary_counts_actual_running_hotspots(hotspot_backend, running_count):
    backend, manager = hotspot_backend

    async def scenario():
        await configure(backend, BUILTIN)
        await start(backend, BUILTIN)
        if running_count == 2:
            await configure(backend)
            await start(backend)
        manager.deny = "DeactivateConnection"
        await stop(backend, BUILTIN)
        assert device(backend, BUILTIN)["hotspot"]["status"] == "failed"
        assert render(hotspot_summary(backend.state["wifi"]), "en") == f"{running_count} hotspots on"
        manager.deny = ""
        await stop(backend, BUILTIN)
        expected = "Hotspots off" if running_count == 1 else "1 hotspots on"
        assert render(hotspot_summary(backend.state["wifi"]), "en") == expected

    asyncio.run(scenario())


def test_takeover_during_start_failure_cannot_reuse_the_original_restore_record(hotspot_backend):
    backend, manager = hotspot_backend

    async def scenario():
        backend.hotspot_poll_interval = 0.005
        await configure(backend, BUILTIN)
        manager.auto_activate = False
        await backend._execute("wifi_hotspot_start", {"deviceId": BUILTIN,
                              "revision": device(backend, BUILTIN)["hotspot"]["revision"], "expectedActive": ACTIVE})
        await asyncio.sleep(0.01)
        hotspot_profile = manager.active[manager.devices[BUILTIN]["ActiveConnection"]]["Connection"]
        manager.auto_activate = True
        result = await manager.call(NM, NM_ROOT, NM, "ActivateConnection", "ooo", [hotspot_profile, BUILTIN, "/"])
        await settle(backend)
        assert manager.devices[BUILTIN]["ActiveConnection"] == result[0]
        assert device(backend, BUILTIN)["hotspot"]["status"] == "failed"
        await stop(backend, BUILTIN)
        assert manager.devices[BUILTIN]["ActiveConnection"] == "/"

    asyncio.run(scenario())


def test_takeover_during_stop_is_reported_without_disconnecting_the_replacement(hotspot_backend):
    backend, manager = hotspot_backend
    previous = manager.call
    replacement = NM_ROOT + "/ActiveConnection/999"

    async def service(*args, **kwargs):
        result = await previous(*args, **kwargs)
        if args[3] == "DeactivateConnection":
            manager.devices[BUILTIN].update(ActiveConnection=replacement, State=100)
            manager.active[replacement] = {"Connection": "/external", "Devices": [BUILTIN], "State": 2}
        return result

    async def scenario():
        await configure(backend, BUILTIN)
        await start(backend, BUILTIN)
        backend.call = service
        await stop(backend, BUILTIN)
        hotspot = device(backend, BUILTIN)["hotspot"]
        assert hotspot["status"] == "failed"
        assert "Another connection took over" in render(hotspot["message"], "en")
        assert manager.devices[BUILTIN]["ActiveConnection"] == replacement

    asyncio.run(scenario())


def test_failed_hotspot_tooltip_keeps_name_and_failure_status(hotspot_backend):
    backend, manager = hotspot_backend

    async def scenario():
        await configure(backend)
        manager.deny = "ActivateConnection"
        await start(backend)
        indicator = wifi_indicators(backend.state["wifi"])[1]
        assert indicator["kind"] == "hotspot"
        assert indicator["status"] == "failed"
        label = render(indicator["label"], "en")
        assert "Pocket network" in label and "Hotspot failed" in label

    asyncio.run(scenario())


def test_removed_adapter_cancels_background_activation_without_restoring_on_another_device(hotspot_backend):
    backend, manager = hotspot_backend

    async def scenario():
        await configure(backend)
        manager.auto_activate = False
        await backend._execute("wifi_hotspot_start", {"deviceId": USB, "revision": device(backend)["hotspot"]["revision"], "expectedActive": "/"})
        await asyncio.sleep(0.01)
        del manager.devices[USB]
        await backend.refresh_wifi()
        await asyncio.sleep(0.01)
        assert USB not in backend.hotspot_operations
        assert manager.devices[BUILTIN]["ActiveConnection"] == ACTIVE
    asyncio.run(scenario())


def test_service_epoch_cancels_old_operations_and_rejects_queued_requests(hotspot_backend):
    backend, manager = hotspot_backend

    async def scenario():
        await configure(backend)
        stale = {"deviceId": USB, "wifiEpoch": backend.wifi_epoch, "revision": device(backend)["hotspot"]["revision"], "expectedActive": "/"}
        manager.auto_activate = False
        await backend._execute("wifi_hotspot_start", stale)
        await asyncio.sleep(0.01)
        before = len(manager.calls)
        backend._reset_wifi()
        await asyncio.sleep(0.01)
        with pytest.raises(RuntimeError):
            await backend._execute("wifi_hotspot_start", stale)
        assert not any(call[1] in ("ActivateConnection", "DeactivateConnection") for call in manager.calls[before:])
    asyncio.run(scenario())


def test_active_hotspot_config_is_readonly_and_client_actions_are_rejected(hotspot_backend):
    backend, manager = hotspot_backend

    async def scenario():
        await configure(backend)
        await start(backend)
        original = deepcopy(manager.profiles)
        with pytest.raises(RuntimeError):
            await configure(backend, ssid="must-not-save")
        with pytest.raises(RuntimeError):
            await backend._execute("wifi_scan", {"deviceId": USB})
        with pytest.raises(RuntimeError):
            await backend._execute("wifi_connect", {"deviceId": USB, "id": "stale-scan"})
        with pytest.raises(RuntimeError):
            await backend._execute("wifi_disconnect", {"deviceId": USB})
        assert manager.profiles == original
    asyncio.run(scenario())


def test_external_ap_configuration_is_visible_and_never_adopted_or_modified(hotspot_backend):
    backend, manager = hotspot_backend

    async def scenario():
        external = NM_ROOT + "/Settings/800"
        manager.profiles[external] = {"connection": {"id": "External", "uuid": "external"},
                                      "802-11-wireless": {"mode": "ap", "ssid": list(b"External")}}
        active = NM_ROOT + "/ActiveConnection/800"
        manager.active[active] = {"Connection": external, "Devices": [USB], "State": 2}
        manager.devices[USB].update(State=100, ActiveConnection=active)
        manager.wireless[USB]["Mode"] = 3
        await backend.refresh_wifi()
        hotspot = device(backend)["hotspot"]
        assert hotspot["activeSsid"] == "External"
        assert not hotspot["owned"]
        before = deepcopy(manager.profiles)
        with pytest.raises(RuntimeError):
            await configure(backend)
        with pytest.raises(RuntimeError):
            await stop(backend)
        assert manager.profiles == before
        assert manager.devices[USB]["ActiveConnection"] == active
    asyncio.run(scenario())


def test_profile_save_errors_cannot_echo_passwords_to_public_state(hotspot_backend):
    backend, manager = hotspot_backend
    previous = manager.call

    async def service(*args, **kwargs):
        if args[3] == "AddConnection":
            raise RuntimeError("rejected test-only-password")
        return await previous(*args, **kwargs)
    backend.call = service

    async def scenario():
        with pytest.raises(RuntimeError) as caught:
            await configure(backend)
        assert "test-only-password" not in str(caught.value)
        assert "test-only-password" not in json.dumps(backend.state)
        assert manager.devices[BUILTIN]["ActiveConnection"] == ACTIVE
    asyncio.run(scenario())


def test_profile_edited_after_start_request_is_not_activated(hotspot_backend):
    backend, manager = hotspot_backend

    async def scenario():
        await configure(backend)
        await backend._execute("wifi_hotspot_start", {"deviceId": USB, "revision": device(backend)["hotspot"]["revision"], "expectedActive": "/"})
        path = next(p for p in manager.profiles if p != PROFILE)
        manager.profiles[path]["802-11-wireless"]["ssid"] = list(b"Externally changed")
        manager.versions[path] = 99
        await settle(backend)
        assert manager.devices[USB]["ActiveConnection"] == "/"
        assert device(backend)["hotspot"]["status"] == "failed"
    asyncio.run(scenario())


@pytest.mark.parametrize("group,key,value", [("connection", "autoconnect", True),
                                              ("ipv4", "method", "auto"),
                                              ("802-11-wireless-security", "key-mgmt", "none")])
def test_externally_weakened_hotspot_is_not_started(hotspot_backend, group, key, value):
    backend, manager = hotspot_backend

    async def scenario():
        await configure(backend)
        path = next(p for p in manager.profiles if p != PROFILE)
        manager.profiles[path][group][key] = value
        await backend.refresh_wifi()
        with pytest.raises(RuntimeError):
            await backend._execute("wifi_hotspot_start", {"deviceId": USB, "revision": device(backend)["hotspot"]["revision"], "expectedActive": "/"})
        assert manager.devices[USB]["ActiveConnection"] == "/"
    asyncio.run(scenario())


def test_saved_hotspot_follows_the_same_hardware_when_its_interface_is_renamed(hotspot_backend):
    backend, manager = hotspot_backend

    async def scenario():
        await configure(backend)
        previous = device(backend)["hotspot"]["profileUuid"]
        manager.devices[USB]["Interface"] = "wlan99"
        await backend.refresh_wifi()
        assert device(backend)["hotspot"]["profileUuid"] == previous
        await start(backend)
        assert device(backend)["hotspot"]["status"] == "active"
        assert len(manager.profiles) == 2
    asyncio.run(scenario())
