import asyncio

import pytest
from dbus_next import DBusError

from udeck.backend import NM, SystemBackend


def test_network_prompt_cancellation_uses_networkmanager_error():
    async def scenario():
        backend = SystemBackend()
        backend.loop.close()
        backend.loop = asyncio.get_running_loop()
        backend.prompt.connect(lambda prompt: backend.reply(prompt["token"], None) if "token" in prompt else None)
        with pytest.raises(DBusError) as caught:
            await backend.ask("text", "Password", "Enter password", cancel_error=NM + ".SecretAgent.Error.UserCanceled", group="network")
        assert caught.value.type == NM + ".SecretAgent.Error.UserCanceled"
        assert backend.pending_prompts == {}

    asyncio.run(scenario())


def test_wifi_enumeration_survives_secret_agent_registration_failure():
    async def scenario():
        backend = SystemBackend()

        async def call(destination, path, interface, member, *arguments, **options):
            if member == "RegisterWithCapabilities":
                raise RuntimeError("agent permission denied")
            if member == "GetDevices":
                return [["/wifi0"]]
            if member == "ListConnections":
                return [["/profile0"]]
            if member == "GetSettings":
                return [{"connection": {"id": "Known network"}, "802-11-wireless": {"ssid": list(b"Known")}, "802-11-wireless-security": {"key-mgmt": "wpa-psk"}}]
            raise AssertionError(member)

        async def get(destination, path, interface, name):
            return {"WirelessEnabled": True, "DeviceType": 2, "State": 100}[name]

        async def properties(destination, path, interface):
            if path == "/ap0":
                return {"Ssid": list(b"Known"), "RsnFlags": 0x100, "Strength": 90}
            if interface.endswith("Device.Wireless"):
                return {"AccessPoints": ["/ap0"], "ActiveAccessPoint": "/ap0"}
            return {"State": 100, "StateReason": [100, 0]}

        backend.call = call
        backend.get = get
        backend.properties = properties
        await backend.refresh_wifi()
        assert backend.state["wifi"]["available"]
        assert backend.state["wifi"]["saved"][0]["id"] == "/profile0"
        assert backend.state["wifi"]["networks"][0]["saved"]
        backend.loop.close()

    asyncio.run(scenario())
