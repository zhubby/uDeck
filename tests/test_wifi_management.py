import asyncio
from copy import deepcopy

import pytest
from dbus_next import DBusError
from test_wifi import ACTIVE, AP0, AP1, BUILTIN, NM, NM_ROOT, PROFILE, USB, NetworkManager

from udeck.backend import SystemBackend, unwrap


class ProfileManager(NetworkManager):
    def __init__(self):
        super().__init__()
        self.profiles[PROFILE]["connection"].update({"autoconnect": True, "interface-name": "wlan7"})
        self.profiles[PROFILE]["ipv4"] = {"method": "manual", "address-data": [{"address": "10.8.0.2", "prefix": 24}]}
        self.profiles[PROFILE]["proxy"] = {"method": 0}
        self.fail_delete = False
        self.fail_disconnect = False
        self.scan_done = False
        self.versions = {PROFILE: 1}

    async def properties(self, destination, path, interface):
        if interface == NM + ".Settings.Connection":
            return {"Unsaved": False, "VersionId": self.versions.get(path, 1)}
        return await super().properties(destination, path, interface)

    async def call(self, destination, path, interface, member, signature="", body=None, **options):
        if member in ("Update2", "Delete", "Disconnect", "RequestScan", "DeactivateConnection"):
            self.calls.append((path, member, unwrap(body or [])))
            if member == "Update2":
                self.profiles[path] = deepcopy(unwrap(body[0]))
                self.versions[path] = self.versions.get(path, 1) + 1
                return [{}]
            if member == "Delete":
                if self.fail_delete:
                    raise RuntimeError("delete denied")
                del self.profiles[path]
            if member in ("Disconnect", "DeactivateConnection"):
                if self.fail_disconnect:
                    raise RuntimeError("disconnect denied")
                device_id = path if member == "Disconnect" else self.active[body[0]]["Devices"][0]
                if member == "Disconnect" or self.devices[device_id]["ActiveConnection"] == body[0]:
                    self.devices[device_id].update(State=30, ActiveConnection="/")
                    self.wireless[device_id]["ActiveAccessPoint"] = "/"
                self.active = {key: value for key, value in self.active.items()
                               if (device_id not in value["Devices"] if member == "Disconnect" else key != body[0])}
            if member == "RequestScan" and self.scan_done:
                self.wireless[path]["LastScan"] = 12
            return []
        return await super().call(destination, path, interface, member, signature, body, **options)


@pytest.fixture
def managed_wifi():
    backend, manager = SystemBackend(), ProfileManager()
    backend.call, backend.get, backend.properties = manager.call, manager.get, manager.properties
    yield backend, manager
    backend.loop.close()


def run(backend, callback):
    async def scenario():
        await backend.refresh_wifi()
        return await callback()
    return asyncio.run(scenario())


def profile(backend, device=BUILTIN):
    return next(item for item in backend.state["wifi"]["devices"] if item["id"] == device)["saved"][0]


def payload(backend, **extra):
    p = profile(backend)
    return {"deviceId": BUILTIN, "profileUuid": p["uuid"], "revision": p["revision"], **extra}


def test_saved_network_management_survives_wifi_off_and_out_of_range(managed_wifi):
    backend, manager = managed_wifi
    manager.enabled = False
    manager.devices[BUILTIN]["AvailableConnections"] = []
    manager.wireless[BUILTIN]["AccessPoints"] = []
    async def check():
        entry = profile(backend)
        assert entry["uuid"] == "known"
        assert entry["autoconnect"] is True
        assert entry["revision"]
        assert not next(d for d in backend.state["wifi"]["devices"] if d["id"] == USB)["saved"]
        await backend._execute("wifi_set_autoconnect", payload(backend, enabled=False))
    run(backend, check)
    assert manager.profiles[PROFILE]["connection"]["autoconnect"] is False


def test_configuration_update_preserves_unrelated_properties_and_does_not_read_secrets(managed_wifi):
    backend, manager = managed_wifi
    original = deepcopy(manager.profiles[PROFILE])
    async def check():
        await backend._execute("wifi_set_autoconnect", payload(backend, enabled=False))
    run(backend, check)
    expected = deepcopy(original)
    expected["connection"]["autoconnect"] = False
    assert manager.profiles[PROFILE] == expected
    assert not any(member in ("GetSecrets", "ClearSecrets", "ActivateConnection", "Disconnect") for _, member, _ in manager.calls)


def test_password_save_is_targeted_and_never_reconnects(managed_wifi):
    backend, manager = managed_wifi
    async def check():
        await backend._execute("wifi_update_password", payload(backend, password="new-test-pass"))
    run(backend, check)
    assert manager.profiles[PROFILE]["802-11-wireless-security"]["psk"] == "new-test-pass"
    assert manager.profiles[PROFILE]["ipv4"]["method"] == "manual"
    assert manager.devices[BUILTIN]["State"] == 100
    assert not any(member in ("ActivateConnection", "Disconnect", "GetSecrets") for _, member, _ in manager.calls)
    assert "new-test-pass" not in str(backend.state)


@pytest.mark.parametrize("action", ["wifi_forget", "wifi_set_autoconnect", "wifi_update_password"])
def test_mutation_rejects_profiles_in_use_by_another_adapter(managed_wifi, action):
    backend, manager = managed_wifi
    manager.active[ACTIVE]["Devices"].append(USB)
    async def check():
        with pytest.raises(RuntimeError):
            await backend._execute(action, payload(backend, password="new-test-pass", enabled=False))
    run(backend, check)
    assert not any(member in ("Delete", "Update2", "Disconnect") for _, member, _ in manager.calls)


def test_password_entry_rejects_a_profile_changed_after_the_menu_was_opened(managed_wifi):
    backend, manager = managed_wifi
    async def check():
        target = payload(backend, password="new-test-pass")
        manager.profiles[PROFILE]["ipv4"]["method"] = "auto"
        with pytest.raises(RuntimeError):
            await backend._execute("wifi_update_password", target)
    run(backend, check)
    assert not any(member == "Update2" for _, member, _ in manager.calls)


def test_forget_disconnects_only_its_device_before_deleting_exact_profile(managed_wifi):
    backend, manager = managed_wifi
    other = NM_ROOT + "/Settings/other"
    manager.profiles[other] = deepcopy(manager.profiles[PROFILE])
    manager.profiles[other]["connection"]["uuid"] = "same-ssid-other"
    async def check():
        await backend._execute("wifi_forget", payload(backend))
    run(backend, check)
    assert PROFILE not in manager.profiles and other in manager.profiles
    commands = [(path, member, body) for path, member, body in manager.calls if member in ("Delete", "Disconnect", "DeactivateConnection")]
    assert commands == [(NM_ROOT, "DeactivateConnection", [ACTIVE]), (PROFILE, "Delete", [])]


@pytest.mark.parametrize("failure", ["disconnect", "delete"])
def test_forget_reports_partial_failure_and_never_claims_success(managed_wifi, failure):
    backend, manager = managed_wifi
    setattr(manager, "fail_" + failure, True)
    async def check():
        with pytest.raises(RuntimeError) as error:
            await backend._execute("wifi_forget", payload(backend))
        if failure == "delete":
            assert "disconnected" in str(error.value).lower() or "已断开" in str(error.value)
    run(backend, check)
    assert PROFILE in manager.profiles
    if failure == "disconnect":
        assert not any(member == "Delete" for _, member, _ in manager.calls)


def test_network_identity_survives_access_point_replacement_and_locale(managed_wifi):
    backend, manager = managed_wifi
    async def check():
        first = backend.state["wifi"]["devices"][0]["networks"][0]["key"]
        manager.aps[AP1] = manager.aps.pop(AP0)
        manager.wireless[BUILTIN].update(AccessPoints=[AP1], ActiveAccessPoint=AP1)
        await backend.refresh_wifi()
        assert backend.state["wifi"]["devices"][0]["networks"][0]["key"] == first
    run(backend, check)


def test_scan_reports_completion_from_last_scan_and_timeout_retains_networks(managed_wifi):
    backend, manager = managed_wifi
    manager.wireless[BUILTIN]["LastScan"] = 10
    manager.scan_done = True
    async def check():
        await backend._execute("wifi_scan", {"deviceId": BUILTIN})
        device = next(d for d in backend.state["wifi"]["devices"] if d["id"] == BUILTIN)
        assert device["scan"]["status"] == "complete"
        manager.scan_done = False
        await backend._execute("wifi_scan", {"deviceId": BUILTIN})
        backend.wifi_scans[BUILTIN]["started"] -= 21
        await backend.refresh_wifi()
        device = next(d for d in backend.state["wifi"]["devices"] if d["id"] == BUILTIN)
        assert device["scan"]["status"] == "timeout"
        assert device["networks"]
    run(backend, check)


def test_cancel_cannot_disconnect_an_operation_replaced_by_another_connection(managed_wifi):
    backend, manager = managed_wifi
    async def check():
        backend.wifi_operations[BUILTIN] = {"id": "stale", "activePath": "/old", "status": "connecting", "started": 0}
        with pytest.raises(RuntimeError):
            await backend._execute("wifi_cancel_connect", {"deviceId": BUILTIN, "operationId": "stale"})
    run(backend, check)
    assert not any(member in ("Disconnect", "DeactivateConnection") for _, member, _ in manager.calls)


def test_connection_deadline_does_not_disconnect_the_device(managed_wifi):
    backend, manager = managed_wifi
    async def check():
        import time
        manager.devices[BUILTIN].update(State=70)
        manager.active[ACTIVE]["State"] = 1
        backend.wifi_operations[BUILTIN] = {"id": "waiting", "activePath": ACTIVE, "profileUuid": "known", "status": "connecting", "started": time.monotonic() - 91}
        await backend.refresh_wifi()
        device = next(d for d in backend.state["wifi"]["devices"] if d["id"] == BUILTIN)
        assert device["operation"]["timedOut"] is True
        assert device["operation"]["status"] == "connecting"
    run(backend, check)
    assert not any(member == "Disconnect" for _, member, _ in manager.calls)


def test_secret_only_external_edit_invalidates_the_password_prompt(managed_wifi):
    backend, manager = managed_wifi
    async def check():
        target = payload(backend, password="new-test-pass")
        manager.versions[PROFILE] += 1
        with pytest.raises(RuntimeError):
            await backend._execute("wifi_update_password", target)
    run(backend, check)
    assert not any(member == "Update2" for _, member, _ in manager.calls)


def test_profile_updates_use_networkmanager_version_compare_and_swap(managed_wifi):
    backend, manager = managed_wifi
    async def check():
        await backend._execute("wifi_set_autoconnect", payload(backend, enabled=False))
    run(backend, check)
    update = next(body for _, member, body in manager.calls if member == "Update2")
    assert update[2] == {"version-id": 1}


def test_forget_waits_for_actual_disconnect_before_deleting(managed_wifi):
    backend, manager = managed_wifi
    original = manager.call
    backend.wifi_disconnect_timeout = 0.02
    async def delayed(destination, path, interface, member, *args, **kwargs):
        if member in ("Disconnect", "DeactivateConnection"):
            manager.calls.append((path, member, []))
            return []  # Request accepted, but the connection is still active.
        return await original(destination, path, interface, member, *args, **kwargs)
    backend.call = delayed
    async def check():
        with pytest.raises(RuntimeError):
            await backend._execute("wifi_forget", payload(backend))
    run(backend, check)
    assert PROFILE in manager.profiles
    assert not any(member == "Delete" for _, member, _ in manager.calls)


def test_forget_does_not_disconnect_a_replacement_connection(managed_wifi):
    backend, manager = managed_wifi
    replacement = NM_ROOT + "/ActiveConnection/replacement"
    other_profile = NM_ROOT + "/Settings/replacement"
    original = manager.call
    async def changed(destination, path, interface, member, *args, **kwargs):
        if member in ("Disconnect", "DeactivateConnection"):
            manager.active[replacement] = {"Connection": other_profile, "Devices": [BUILTIN], "State": 2}
            manager.devices[BUILTIN]["ActiveConnection"] = replacement
        return await original(destination, path, interface, member, *args, **kwargs)
    backend.call = changed
    async def check():
        await backend._execute("wifi_forget", payload(backend))
    run(backend, check)
    assert manager.devices[BUILTIN]["ActiveConnection"] == replacement
    assert replacement in manager.active


@pytest.mark.parametrize("cancel_failure", [False, True])
def test_cancel_during_activation_deactivates_only_the_returned_request(managed_wifi, cancel_failure):
    backend, manager = managed_wifi
    manager.fail_disconnect = cancel_failure
    entered, released = asyncio.Event(), asyncio.Event()
    active = NM_ROOT + "/ActiveConnection/new"
    original = manager.call
    async def delayed(destination, path, interface, member, signature="", body=None, **kwargs):
        if member == "AddAndActivateConnection":
            entered.set()
            await released.wait()
            manager.devices[USB].update(State=70, ActiveConnection=active)
            manager.active[active] = {"Connection": NM_ROOT + "/Settings/new", "Devices": [USB], "State": 1}
            return [NM_ROOT + "/Settings/new", active]
        return await original(destination, path, interface, member, signature, body, **kwargs)
    backend.call = delayed
    async def password(*args, **kwargs):
        return "test-password"
    backend.ask = password
    async def check():
        joining = asyncio.create_task(backend._execute("wifi_connect", {"deviceId": USB, "id": AP1}))
        await asyncio.wait_for(entered.wait(), 1)
        operation = backend.wifi_operations[USB]
        await backend._execute("wifi_cancel_connect", {"deviceId": USB, "operationId": operation["id"]})
        released.set()
        if cancel_failure:
            with pytest.raises(RuntimeError):
                await joining
            assert backend.wifi_operations[USB]["status"] == "connecting"
        else:
            await joining
            assert backend.wifi_operations[USB]["status"] == "cancelled"
    run(backend, check)
    assert (active in manager.active) is cancel_failure
    assert manager.devices[BUILTIN]["ActiveConnection"] == ACTIVE


def test_networkmanager_restart_during_password_entry_prevents_activation(managed_wifi):
    backend, manager = managed_wifi
    async def password(*args, **kwargs):
        backend._reset_wifi()
        return "test-password"
    backend.ask = password
    async def check():
        with pytest.raises(DBusError, match="cancelled|取消"):
            await backend._execute("wifi_connect", {"deviceId": USB, "id": AP1})
    run(backend, check)
    assert not any(member == "AddAndActivateConnection" for _, member, _ in manager.calls)


def test_unknown_advanced_profile_compatibility_is_visible_but_disabled(managed_wifi):
    backend, manager = managed_wifi
    manager.profiles[PROFILE]["match"] = {"driver": ["brcmfmac"]}
    manager.devices[BUILTIN]["AvailableConnections"] = []
    manager.enabled = False
    async def check():
        saved = profile(backend)
        assert saved["blocked"] and saved["mutationBlocked"]
        with pytest.raises(RuntimeError):
            await backend._execute("wifi_forget", payload(backend))
    run(backend, check)


def test_scan_keeps_previous_networks_until_last_scan_changes(managed_wifi):
    backend, manager = managed_wifi
    async def check():
        await backend._execute("wifi_scan", {"deviceId": USB})
        manager.wireless[USB]["AccessPoints"] = []
        await backend.refresh_wifi()
        device = next(d for d in backend.state["wifi"]["devices"] if d["id"] == USB)
        assert device["networks"] and device["scan"]["status"] == "scanning"
        backend.wifi_scans[USB]["started"] -= 21
        await backend.refresh_wifi()
        device = next(d for d in backend.state["wifi"]["devices"] if d["id"] == USB)
        assert device["networks"] and device["scan"]["status"] == "timeout"
    run(backend, check)


@pytest.mark.parametrize("unavailable", ["occupied", "unknown", "deleted"])
def test_confirmation_revalidates_configuration_ownership_and_existence(managed_wifi, unavailable):
    backend, manager = managed_wifi
    async def check():
        target = payload(backend)
        if unavailable == "occupied":
            manager.active[ACTIVE]["Devices"].append(USB)
        elif unavailable == "unknown":
            manager.broken.add(ACTIVE)
        else:
            del manager.profiles[PROFILE]
        with pytest.raises(RuntimeError):
            await backend._execute("wifi_forget", target)
    run(backend, check)
    assert not any(member in ("Delete", "Disconnect", "DeactivateConnection") for _, member, _ in manager.calls)


def test_autoconnect_save_failure_restores_actual_preference(managed_wifi):
    backend, manager = managed_wifi
    original = manager.call
    async def denied(destination, path, interface, member, *args, **kwargs):
        if member == "Update2":
            raise RuntimeError("permission denied")
        return await original(destination, path, interface, member, *args, **kwargs)
    backend.call = denied
    async def check():
        with pytest.raises(RuntimeError, match="permission denied"):
            await backend._execute("wifi_set_autoconnect", payload(backend, enabled=False))
        assert profile(backend)["autoconnect"] is True
    run(backend, check)


def test_retry_reuses_its_saved_configuration_and_waits_for_actual_state(managed_wifi):
    backend, manager = managed_wifi
    original = manager.call
    added_profile, added_active = NM_ROOT + "/Settings/new", NM_ROOT + "/ActiveConnection/new"
    async def activate(destination, path, interface, member, signature="", body=None, **kwargs):
        if member in ("AddAndActivateConnection", "ActivateConnection"):
            manager.calls.append((path, member, unwrap(body)))
            if member == "AddAndActivateConnection":
                manager.profiles[added_profile] = unwrap(body[0])
            manager.devices[USB].update(State=70, ActiveConnection=added_active)
            manager.active[added_active] = {"Connection": added_profile, "Devices": [USB], "State": 1}
            manager.wireless[USB]["ActiveAccessPoint"] = AP1
            return [added_profile, added_active] if member == "AddAndActivateConnection" else [added_active]
        return await original(destination, path, interface, member, signature, body, **kwargs)
    backend.call = activate
    async def password(*args, **kwargs):
        return "test-password"
    backend.ask = password
    async def check():
        target = {"deviceId": USB, "id": AP1}
        await backend._execute("wifi_connect", target)
        device = next(d for d in backend.state["wifi"]["devices"] if d["id"] == USB)
        assert device["operation"]["status"] == "connecting" and not device["connected"]
        with pytest.raises(RuntimeError):
            await backend._execute("wifi_connect", target)
        manager.devices[USB].update(State=120, StateReason=[120, 7])
        await backend.refresh_wifi()
        assert backend.wifi_operations[USB]["status"] == "failed"
        await backend._execute("wifi_connect", target)
        assert backend.wifi_operations[USB]["status"] == "connecting"
        manager.devices[USB].update(State=100)
        manager.active[added_active]["State"] = 2
        await backend.refresh_wifi()
        assert backend.wifi_operations[USB]["status"] == "connected"
    run(backend, check)
    assert sum(member == "AddAndActivateConnection" for _, member, _ in manager.calls) == 1
    assert sum(member == "ActivateConnection" for _, member, _ in manager.calls) == 1
    assert manager.devices[BUILTIN]["ActiveConnection"] == ACTIVE


def test_secret_agent_rejects_external_edits_during_credential_entry(managed_wifi):
    backend, manager = managed_wifi
    async def password(*args, **kwargs):
        manager.versions[PROFILE] += 1
        return "test-password"
    backend.ask = password
    async def check():
        with pytest.raises(DBusError):
            await type(backend.network_agent).GetSecrets.__wrapped__(backend.network_agent, {}, PROFILE, "802-11-wireless-security", [], 0)
    run(backend, check)


def test_cancel_while_entering_password_does_not_activate_or_drop_existing_connection(managed_wifi):
    backend, manager = managed_wifi
    async def password(*args, **kwargs):
        operation = backend.wifi_operations[USB]
        await backend._execute("wifi_cancel_connect", {"deviceId": USB, "operationId": operation["id"]})
        return "test-password"
    backend.ask = password
    async def check():
        with pytest.raises(DBusError):
            await backend._execute("wifi_connect", {"deviceId": USB, "id": AP1})
        assert backend.wifi_operations[USB]["status"] == "cancelled"
    run(backend, check)
    assert not any(member in ("ActivateConnection", "AddAndActivateConnection", "Disconnect", "DeactivateConnection") for _, member, _ in manager.calls)
    assert manager.devices[BUILTIN]["ActiveConnection"] == ACTIVE


def test_restart_during_activation_does_not_bind_a_stale_profile(managed_wifi):
    backend, manager = managed_wifi
    original = manager.call
    async def restarted(destination, path, interface, member, *args, **kwargs):
        if member == "AddAndActivateConnection":
            backend._reset_wifi()
            return [NM_ROOT + "/Settings/stale", NM_ROOT + "/ActiveConnection/stale"]
        return await original(destination, path, interface, member, *args, **kwargs)
    backend.call = restarted
    async def password(*args, **kwargs):
        return "test-password"
    backend.ask = password
    async def check():
        await backend._execute("wifi_connect", {"deviceId": USB, "id": AP1})
        assert backend.wifi_profile_devices == {} and backend.wifi_operations == {}
    run(backend, check)


def test_unreadable_adapter_still_ends_its_scan_at_the_deadline(managed_wifi):
    backend, manager = managed_wifi
    async def check():
        await backend._execute("wifi_scan", {"deviceId": USB})
        backend.wifi_scans[USB]["started"] -= 21
        manager.broken.add(USB)
        await backend.refresh_wifi()
        device = next(d for d in backend.state["wifi"]["devices"] if d["id"] == USB)
        assert device["scan"]["status"] == "timeout" and device["error"]
        assert next(d for d in backend.state["wifi"]["devices"] if d["id"] == BUILTIN)["connected"] == "Workshop"
    run(backend, check)


def test_queued_mutation_from_a_previous_networkmanager_instance_is_rejected(managed_wifi):
    backend, manager = managed_wifi
    async def check():
        target = {**payload(backend, enabled=False), "wifiEpoch": backend.wifi_epoch}
        backend._reset_wifi()
        with pytest.raises(RuntimeError):
            await backend._execute("wifi_set_autoconnect", target)
    run(backend, check)
    assert not any(member == "Update2" for _, member, _ in manager.calls)


def test_restart_during_profile_validation_cancels_the_mutation(managed_wifi):
    backend, manager = managed_wifi
    original = manager.call
    reset = False
    async def restarted(destination, path, interface, member, *args, **kwargs):
        nonlocal reset
        if member == "GetSettings" and not reset:
            reset = True
            backend._reset_wifi()
        return await original(destination, path, interface, member, *args, **kwargs)
    async def check():
        target = payload(backend, enabled=False)
        backend.call = restarted
        with pytest.raises(RuntimeError):
            await backend._execute("wifi_set_autoconnect", target)
    run(backend, check)
    assert not any(member == "Update2" for _, member, _ in manager.calls)
