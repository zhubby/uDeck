import asyncio
from copy import deepcopy

import pytest
from dbus_next import DBusError, Message

from udeck.backend import NM, NM_ROOT, SystemBackend, unwrap

BUILTIN = NM_ROOT + "/Devices/1"
USB = NM_ROOT + "/Devices/2"
AP0 = NM_ROOT + "/AccessPoint/1"
AP1 = NM_ROOT + "/AccessPoint/2"
PROFILE = NM_ROOT + "/Settings/1"
ACTIVE = NM_ROOT + "/ActiveConnection/1"


class NetworkManager:
    """Replace the external D-Bus boundary; keep uDeck enumeration and actions real."""

    def __init__(self):
        self.enabled = True
        self.devices = {
            BUILTIN: {"DeviceType": 2, "Interface": "wlan7", "Managed": True,
                      "State": 100, "StateReason": [100, 0], "ActiveConnection": ACTIVE,
                      "AvailableConnections": [PROFILE]},
            USB: {"DeviceType": 2, "Interface": "wlx0123456789ab", "Managed": True,
                  "State": 30, "StateReason": [30, 0], "ActiveConnection": "/",
                  "AvailableConnections": [PROFILE]},
        }
        self.wireless = {
            BUILTIN: {"AccessPoints": [AP0], "ActiveAccessPoint": AP0},
            USB: {"AccessPoints": [AP1], "ActiveAccessPoint": "/"},
        }
        self.aps = {
            AP0: {"Ssid": list(b"Workshop"), "RsnFlags": 0x100, "Strength": 70},
            AP1: {"Ssid": list(b"Workshop"), "RsnFlags": 0x100, "Strength": 95},
        }
        self.profiles = {PROFILE: {"connection": {"id": "Workshop", "uuid": "known", "multi-connect": 0},
                                   "802-11-wireless": {"ssid": list(b"Workshop")},
                                   "802-11-wireless-security": {"key-mgmt": "wpa-psk"}}}
        self.active = {ACTIVE: {"Connection": PROFILE, "Devices": [BUILTIN], "State": 2}}
        self.broken = set()
        self.calls = []

    async def properties(self, destination, path, interface):
        if path in self.broken:
            raise RuntimeError("device read failed")
        if interface == NM + ".Device.Wireless":
            return deepcopy(self.wireless[path])
        for collection in (self.devices, self.aps, self.active):
            if path in collection:
                return deepcopy(collection[path])
        raise RuntimeError("object disappeared")

    async def get(self, destination, path, interface, name):
        if path == NM_ROOT:
            return {"WirelessEnabled": self.enabled, "ActiveConnections": list(self.active)}[name]
        if name == "DeviceType":
            return self.devices[path][name]
        return (await self.properties(destination, path, interface))[name]

    async def call(self, destination, path, interface, member, signature="", body=None, **options):
        self.calls.append((path, member, unwrap(body or [])))
        if member == "GetDevices":
            return [list(self.devices)]
        if member == "ListConnections":
            return [list(self.profiles)]
        if member == "GetSettings":
            return [deepcopy(self.profiles[path])]
        if member == "AddAndActivateConnection":
            return [NM_ROOT + "/Settings/2", NM_ROOT + "/ActiveConnection/2"]
        if member in ("RegisterWithCapabilities", "RequestScan", "Disconnect", "ActivateConnection"):
            return ["/"] if member == "ActivateConnection" else []
        raise AssertionError((path, interface, member))


@pytest.fixture
def network_backend():
    backend = SystemBackend()
    manager = NetworkManager()
    backend.call, backend.get, backend.properties = manager.call, manager.get, manager.properties
    yield backend, manager
    backend.loop.close()


def test_enumerates_both_adapters_without_combining_the_same_ssid(network_backend):
    backend, _ = network_backend
    asyncio.run(backend.refresh_wifi())
    devices = {device["id"]: device for device in backend.state["wifi"]["devices"]}
    assert set(devices) == {BUILTIN, USB}
    assert devices[BUILTIN]["connected"] == "Workshop"
    assert devices[USB]["connected"] == ""
    assert devices[BUILTIN]["networks"][0]["id"] == AP0
    assert devices[USB]["networks"][0]["id"] == AP1


def test_one_broken_adapter_does_not_hide_the_other(network_backend):
    backend, manager = network_backend
    manager.broken.add(USB)
    asyncio.run(backend.refresh_wifi())
    assert backend.state["wifi"]["available"]
    devices = {device["id"]: device for device in backend.state["wifi"]["devices"]}
    assert devices[BUILTIN]["connected"] == "Workshop"
    assert devices[USB]["error"]


def test_networkmanager_hotplug_signals_refresh_adapters(network_backend):
    backend, manager = network_backend
    usb = manager.devices.pop(USB)
    backend.loop.close()

    async def scenario():
        backend.loop = asyncio.get_running_loop()
        await backend.refresh_wifi()
        assert {device["id"] for device in backend.state["wifi"]["devices"]} == {BUILTIN}
        manager.devices[USB] = usb
        backend._message(Message.new_signal(NM_ROOT, NM, "DeviceAdded", "o", [USB]))
        await asyncio.wait_for(asyncio.gather(*backend.refresh_tasks.values()), timeout=3)
        assert {device["id"] for device in backend.state["wifi"]["devices"]} == {BUILTIN, USB}
        manager.devices.pop(USB)
        backend._message(Message.new_signal(NM_ROOT, NM, "DeviceRemoved", "o", [USB]))
        await asyncio.wait_for(asyncio.gather(*backend.refresh_tasks.values()), timeout=3)
        assert [device["id"] for device in backend.state["wifi"]["devices"]] == [BUILTIN]
        assert backend.state["wifi"]["devices"][0]["connected"] == "Workshop"

    asyncio.run(scenario())


def test_disappearing_ap_does_not_hide_the_adapter(network_backend):
    backend, manager = network_backend
    manager.broken.add(AP1)
    asyncio.run(backend.refresh_wifi())
    devices = {device["id"]: device for device in backend.state["wifi"]["devices"]}
    assert devices[USB]["available"]
    assert devices[USB]["networks"] == []
    assert devices[BUILTIN]["connected"] == "Workshop"


@pytest.mark.parametrize(("action", "member"), [("wifi_scan", "RequestScan"), ("wifi_disconnect", "Disconnect")])
def test_operations_use_only_the_explicit_adapter(network_backend, action, member):
    backend, manager = network_backend

    async def scenario():
        await backend.refresh_wifi()
        await backend._execute(action, {"deviceId": USB})

    asyncio.run(scenario())
    assert [(path, call) for path, call, _ in manager.calls if call == member] == [(USB, member)]


@pytest.mark.parametrize("payload", [{}, {"deviceId": NM_ROOT + "/Devices/99"}])
def test_scanning_without_a_present_target_never_falls_back(network_backend, payload):
    backend, manager = network_backend

    async def scenario():
        await backend.refresh_wifi()
        with pytest.raises(RuntimeError):
            await backend._execute("wifi_scan", payload)

    asyncio.run(scenario())
    assert not any(member == "RequestScan" for _, member, _ in manager.calls)


def test_saved_profiles_are_filtered_by_device_compatibility(network_backend):
    backend, manager = network_backend
    manager.devices[USB]["AvailableConnections"] = []
    asyncio.run(backend.refresh_wifi())
    devices = {device["id"]: device for device in backend.state["wifi"]["devices"]}
    assert len(devices[BUILTIN]["saved"]) == 1
    assert devices[USB]["saved"] == []


def test_saved_single_instance_profile_cannot_be_stolen(network_backend):
    backend, manager = network_backend

    async def scenario():
        await backend.refresh_wifi()
        usb = next(device for device in backend.state["wifi"]["devices"] if device["id"] == USB)
        assert usb["saved"][0]["blocked"]
        with pytest.raises(RuntimeError):
            await backend._execute("wifi_connect_saved", {"deviceId": USB, "id": PROFILE})

    asyncio.run(scenario())
    assert not any(member == "ActivateConnection" for _, member, _ in manager.calls)


def test_scanned_network_creates_an_independent_profile_when_original_is_busy(network_backend):
    backend, manager = network_backend

    async def password(*args, **options):
        assert options["deviceId"] == USB
        return "test-password"

    backend.ask = password

    async def scenario():
        await backend.refresh_wifi()
        await backend._execute("wifi_connect", {"deviceId": USB, "id": AP1})

    asyncio.run(scenario())
    activations = [(member, body) for _, member, body in manager.calls if member in ("ActivateConnection", "AddAndActivateConnection")]
    assert len(activations) == 1
    assert activations[0][0] == "AddAndActivateConnection"
    assert activations[0][1][1:] == [USB, AP1]
    assert activations[0][1][0]["connection"]["uuid"] != "known"


@pytest.mark.parametrize("mode", ["ap", "adhoc", "mesh"])
def test_client_connection_never_activates_a_non_infrastructure_profile(network_backend, mode):
    backend, manager = network_backend
    manager.profiles[PROFILE]["802-11-wireless"]["mode"] = mode
    manager.active.clear()
    manager.devices[BUILTIN]["State"] = 30
    manager.wireless[BUILTIN]["ActiveAccessPoint"] = "/"

    async def password(*args, **options):
        return "test-password"

    backend.ask = password

    async def scenario():
        await backend.refresh_wifi()
        await backend._execute("wifi_connect", {"deviceId": USB, "id": AP1})

    asyncio.run(scenario())
    activations = [(member, body) for _, member, body in manager.calls if member in ("ActivateConnection", "AddAndActivateConnection")]
    assert len(activations) == 1
    assert activations[0][0] == "AddAndActivateConnection"
    assert activations[0][1][0]["802-11-wireless"]["mode"] == "infrastructure"
    assert all(device["saved"] == [] for device in backend.state["wifi"]["devices"])


def test_unplug_during_password_prompt_prevents_activation(network_backend):
    backend, manager = network_backend
    prompted = []

    async def password(*args, **options):
        prompted.append(options["deviceId"])
        manager.devices.pop(USB)
        return "test-password"

    backend.ask = password

    async def scenario():
        await backend.refresh_wifi()
        with pytest.raises(RuntimeError):
            await backend._execute("wifi_connect", {"deviceId": USB, "id": AP1})

    asyncio.run(scenario())
    assert prompted == [USB]
    assert not any(member in ("ActivateConnection", "AddAndActivateConnection") for _, member, _ in manager.calls)


def test_wrong_adapters_access_point_cannot_be_activated(network_backend):
    backend, manager = network_backend

    async def scenario():
        await backend.refresh_wifi()
        with pytest.raises(RuntimeError):
            await backend._execute("wifi_connect", {"deviceId": USB, "id": AP0})

    asyncio.run(scenario())
    assert not any(member in ("ActivateConnection", "AddAndActivateConnection") for _, member, _ in manager.calls)


def test_adapter_names_follow_the_bus_not_wlan_number(tmp_path):
    from udeck.wifi import wifi_identity

    for interface, bus in (("wlan0", "usb"), ("wlan9", "mmc")):
        device = tmp_path / "devices" / interface
        device.mkdir(parents=True)
        bus_path = tmp_path / "bus" / bus
        bus_path.mkdir(parents=True)
        (device / "subsystem").symlink_to(bus_path, target_is_directory=True)
        net = tmp_path / "net" / interface
        net.mkdir(parents=True)
        (net / "device").symlink_to(device, target_is_directory=True)
    assert wifi_identity("wlan0", tmp_path / "net")["kind"] == "usb"
    assert wifi_identity("wlan9", tmp_path / "net")["kind"] == "builtin"
    assert wifi_identity("wlan1", tmp_path / "net")["kind"] == "unknown"


def test_secret_agent_rejects_an_ambiguous_shared_profile_without_prompting(network_backend):
    backend, _ = network_backend
    prompts = []

    async def password(*args, **options):
        prompts.append(options)
        return "test-password"

    backend.ask = password

    async def scenario():
        await backend.refresh_wifi()
        backend.wifi_profile_devices[PROFILE] = USB
        with pytest.raises(DBusError, match="无法确认"):
            await type(backend.network_agent).GetSecrets.__wrapped__(backend.network_agent, {}, PROFILE, "802-11-wireless-security", [], 0)

    asyncio.run(scenario())
    assert prompts == []


@pytest.mark.parametrize("usage_unreadable", [False, True])
def test_secret_agent_rejects_requests_without_a_confirmed_adapter(network_backend, usage_unreadable):
    backend, manager = network_backend
    prompts = []

    async def password(*args, **options):
        prompts.append(options)
        return "test-password"

    backend.ask = password

    async def scenario():
        await backend.refresh_wifi()
        if usage_unreadable:
            manager.broken.add(ACTIVE)
        else:
            manager.active.clear()
        with pytest.raises(DBusError, match="无法确认"):
            await type(backend.network_agent).GetSecrets.__wrapped__(backend.network_agent, {}, PROFILE, "802-11-wireless-security", [], 0)

    asyncio.run(scenario())
    assert prompts == []


def test_secret_agent_binds_an_unmapped_request_to_its_only_active_adapter(network_backend):
    backend, _ = network_backend
    prompts = []

    async def password(*args, **options):
        prompts.append(options)
        return "test-password"

    backend.ask = password

    async def scenario():
        await backend.refresh_wifi()
        result = await type(backend.network_agent).GetSecrets.__wrapped__(backend.network_agent, {}, PROFILE, "802-11-wireless-security", [], 0)
        assert unwrap(result) == {"802-11-wireless-security": {"psk": "test-password"}}

    asyncio.run(scenario())
    assert prompts[0]["deviceId"] == BUILTIN


def test_secret_agent_rechecks_profile_ownership_after_password_input(network_backend):
    backend, manager = network_backend

    async def password(*args, **options):
        manager.active[ACTIVE]["Devices"] = [USB]
        return "test-password"

    backend.ask = password

    async def scenario():
        await backend.refresh_wifi()
        backend.wifi_profile_devices[PROFILE] = BUILTIN
        with pytest.raises(DBusError, match="无法确认"):
            await type(backend.network_agent).GetSecrets.__wrapped__(backend.network_agent, {}, PROFILE, "802-11-wireless-security", [], 0)

    asyncio.run(scenario())


def test_secret_agent_targets_the_only_activating_adapter_of_a_shared_profile(network_backend):
    backend, manager = network_backend
    prompts = []

    async def password(*args, **options):
        prompts.append(options)
        return "test-password"

    backend.ask = password

    async def scenario():
        await backend.refresh_wifi()
        backend.wifi_profile_devices[PROFILE] = USB
        manager.active[NM_ROOT + "/ActiveConnection/2"] = {"Connection": PROFILE, "Devices": [USB], "State": 1}
        result = await type(backend.network_agent).GetSecrets.__wrapped__(backend.network_agent, {}, PROFILE, "802-11-wireless-security", [], 0)
        assert unwrap(result) == {"802-11-wireless-security": {"psk": "test-password"}}

    asyncio.run(scenario())
    assert prompts[0]["deviceId"] == USB


def test_cancel_get_secrets_leaves_another_password_on_the_same_adapter_open(network_backend):
    backend, _ = network_backend
    backend.loop.close()

    async def scenario():
        backend.loop = asyncio.get_running_loop()
        await backend.refresh_wifi()
        backend.wifi_profile_devices[PROFILE] = BUILTIN
        secret = asyncio.create_task(type(backend.network_agent).GetSecrets.__wrapped__(backend.network_agent, {}, PROFILE, "802-11-wireless-security", [], 0))
        manual = asyncio.create_task(backend.ask("text", "新网络密码", "", group="network:" + BUILTIN, deviceId=BUILTIN))
        try:
            await asyncio.sleep(0)
            type(backend.network_agent).CancelGetSecrets.__wrapped__(backend.network_agent, PROFILE, "802-11-wireless-security")
            result = await asyncio.wait_for(asyncio.gather(secret, return_exceptions=True), timeout=1)
            assert isinstance(result[0], DBusError)
            assert not manual.done()
        finally:
            backend.cancel_prompts("network")
            await asyncio.gather(secret, manual, return_exceptions=True)

    asyncio.run(scenario())
    assert backend.pending_prompts == {}


def test_unplug_cancels_a_saved_profile_password_but_keeps_another_adapter_prompt(network_backend):
    backend, manager = network_backend
    backend.loop.close()

    async def scenario():
        backend.loop = asyncio.get_running_loop()
        await backend.refresh_wifi()
        backend.wifi_profile_devices[PROFILE] = BUILTIN
        secret = asyncio.create_task(type(backend.network_agent).GetSecrets.__wrapped__(backend.network_agent, {}, PROFILE, "802-11-wireless-security", [], 0))
        other = asyncio.create_task(backend.ask("text", "USB 密码", "", group="network:" + USB, deviceId=USB))
        try:
            await asyncio.sleep(0)
            manager.devices.pop(BUILTIN)
            backend._message(Message.new_signal(NM_ROOT, NM, "DeviceRemoved", "o", [BUILTIN]))
            result = await asyncio.wait_for(asyncio.gather(secret, return_exceptions=True), timeout=1)
            assert isinstance(result[0], DBusError)
            assert not other.done()
            await asyncio.wait_for(asyncio.gather(*backend.refresh_tasks.values()), timeout=3)
        finally:
            backend.cancel_prompts("network")
            await asyncio.gather(secret, other, return_exceptions=True)

    asyncio.run(scenario())
    assert backend.pending_prompts == {}
