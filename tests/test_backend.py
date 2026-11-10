import asyncio
from types import SimpleNamespace

import pytest
from dbus_next import DBusError
from dbus_next.constants import MessageType

import udeck.backend as backend_module
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


def test_logind_lock_request_stays_suspended_until_unlock_is_confirmed(monkeypatch):
    async def scenario():
        backend = SystemBackend()
        backend.login_session = '/org/freedesktop/login1/session/test'
        backend.schedule_refresh = lambda component: None
        properties = {'Active': True, 'LockedHint': False}

        async def read_properties(*arguments):
            return properties

        backend.properties = read_properties
        message = SimpleNamespace(message_type=MessageType.SIGNAL, path=backend.login_session,
                                  member='Lock', body=[], interface='org.freedesktop.login1.Session')
        backend._message(message)
        await backend.refresh_session()
        assert backend.state['sessionInput']['locked'] is True
        properties['LockedHint'] = True
        await backend.refresh_session()
        properties['LockedHint'] = False
        await backend.refresh_session()
        assert backend.state['sessionInput']['locked'] is False
        backend._message(message)
        message.member = 'Unlock'
        backend._message(message)
        await backend.refresh_session()
        assert backend.state['sessionInput']['locked'] is False
        backend.loop.close()

    monkeypatch.setenv('UDECK_SESSION', '1')
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
            return {"WirelessEnabled": True, "DeviceType": 2, "State": 100, "ActiveConnections": []}[name]

        async def properties(destination, path, interface):
            if path == "/ap0":
                return {"Ssid": list(b"Known"), "RsnFlags": 0x100, "Strength": 90}
            if interface.endswith("Device.Wireless"):
                return {"AccessPoints": ["/ap0"], "ActiveAccessPoint": "/ap0"}
            return {"State": 100, "StateReason": [100, 0], "Interface": "wlan0", "DeviceType": 2, "AvailableConnections": ["/profile0"]}

        backend.call = call
        backend.get = get
        backend.properties = properties
        await backend.refresh_wifi()
        assert backend.state["wifi"]["available"]
        assert backend.state["wifi"]["devices"][0]["saved"][0]["id"] == "/profile0"
        assert backend.state["wifi"]["devices"][0]["networks"][0]["saved"]
        backend.loop.close()

    asyncio.run(scenario())


def test_original_desktop_receives_logind_session_changes(monkeypatch):
    monkeypatch.delenv('UDECK_SESSION', raising=False)
    backend = SystemBackend()
    refreshed = []
    backend.schedule_refresh = refreshed.append
    try:
        backend._message(SimpleNamespace(message_type=MessageType.SIGNAL,
                                        path='/org/freedesktop/login1/session/_1',
                                        member='PropertiesChanged', body=[],
                                        interface='org.freedesktop.DBus.Properties'))
        assert refreshed == ['session']
    finally:
        backend.loop.close()


def test_original_desktop_monitors_session_even_when_network_startup_fails(monkeypatch):
    monkeypatch.delenv('UDECK_SESSION', raising=False)
    monkeypatch.setenv('XDG_SESSION_ID', 'graphical-session')

    class Bus:
        async def connect(self):
            return self

        def add_message_handler(self, handler):
            pass

        def export(self, path, agent):
            pass

    monkeypatch.setattr(backend_module, 'MessageBus', lambda **kwargs: Bus())

    async def scenario():
        backend = SystemBackend()
        backend.loop.close()
        backend.loop = asyncio.get_running_loop()
        monitored = []

        async def call(destination, path, interface, member, *arguments):
            if member == 'GetSession':
                assert arguments == ('s', ['graphical-session'])
                return ['/org/freedesktop/login1/session/_1']
            assert member == 'AddMatch'
            return []

        async def properties(*arguments):
            return {'Active': True, 'LockedHint': False}

        async def unavailable():
            raise RuntimeError('Network service unavailable')

        async def idle():
            pass

        async def monitor():
            monitored.append(True)

        backend.call, backend.properties = call, properties
        backend.refresh_wifi = unavailable
        backend.refresh_bluetooth = backend.refresh_timezone = backend.refresh_audio = idle
        backend._watch_audio = backend._hardware_timer = idle
        backend._session_timer = monitor
        backend.refresh_hardware = lambda: None
        await backend._start()
        await asyncio.sleep(0)
        assert backend.state['sessionInput'] == {'available': True, 'active': True, 'locked': False}
        assert monitored == [True]

    asyncio.run(scenario())
