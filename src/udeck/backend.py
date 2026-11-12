import asyncio
import json
import math
import os
import threading
import uuid
from copy import deepcopy
from pathlib import Path

from dbus_next import BusType, DBusError, Message, MessageType, Variant
from dbus_next.aio import MessageBus
from dbus_next.service import ServiceInterface, method
from PySide6.QtCore import QObject, Signal

from .audio import AUDIO_ACTIONS, audio_state
from .battery import read_battery
from .i18n import Msg, error_text, tr
from .mock import initial_state
from .timezone import TIMEDATE, TIMEDATE_PATH
from .wifi import wifi_label
from .wifi_backend import NETWORK_CANCEL, NM, NM_ROOT, WifiBackend, unwrap, validate_wifi_password

BLUEZ = "org.bluez"
PROPERTIES = "org.freedesktop.DBus.Properties"




class BluezAgent(ServiceInterface):
    def __init__(self, backend):
        super().__init__("org.bluez.Agent1")
        self.backend = backend

    @method()
    def Release(self):
        self.backend.cancel_prompts()

    @method()
    async def RequestPinCode(self, device: "o") -> "s":
        response = await self.backend.ask("text", tr(Msg.BLUETOOTH_PIN), tr(Msg.ENTER_THE_PIN_REQUESTED_BY_THE_DEVICE), secret=True)
        return str(response)

    @method()
    def DisplayPinCode(self, device: "o", pincode: "s"):
        self.backend.information(tr(Msg.BLUETOOTH_PAIRING), tr(Msg.ENTER_THIS_PIN_ON_THE_OTHER_DEVICE_VALUE0, value0=pincode))

    @method()
    async def RequestPasskey(self, device: "o") -> "u":
        response = await self.backend.ask("text", tr(Msg.BLUETOOTH_PASSKEY), tr(Msg.ENTER_A_NUMERIC_PASSKEY_FROM_0_TO_999999), numeric=True)
        if not str(response).isdigit() or not 0 <= int(response) <= 999999:
            raise DBusError("org.bluez.Error.Rejected", tr(Msg.INVALID_PASSKEY))
        return int(response)

    @method()
    def DisplayPasskey(self, device: "o", passkey: "u", entered: "q"):
        self.backend.information(tr(Msg.BLUETOOTH_PAIRING), tr(Msg.ENTER_ON_THE_OTHER_DEVICE_VALUE0_06D_VALUE1_DIGITS_ENTERED, value0=passkey, value1=entered))

    @method()
    async def RequestConfirmation(self, device: "o", passkey: "u"):
        await self.backend.ask("confirm", tr(Msg.CONFIRM_BLUETOOTH_PAIRING), tr(Msg.DO_BOTH_DEVICES_SHOW_VALUE0_06D_PROMPT, value0=passkey))

    @method()
    async def RequestAuthorization(self, device: "o"):
        await self.backend.ask("confirm", tr(Msg.BLUETOOTH_PAIRING_REQUEST), tr(Msg.ALLOW_THIS_DEVICE_TO_PAIR_WITH_UCONSOLE_PROMPT))

    @method()
    async def AuthorizeService(self, device: "o", service_uuid: "s"):
        await self.backend.ask("confirm", tr(Msg.BLUETOOTH_SERVICE_AUTHORIZATION), tr(Msg.ALLOW_THE_PAIRED_DEVICE_TO_USE_SERVICE_VALUE0_PROMPT, value0=service_uuid))

    @method()
    def Cancel(self):
        self.backend.cancel_prompts()


class NetworkAgent(ServiceInterface):
    def __init__(self, backend):
        super().__init__(NM + ".SecretAgent")
        self.backend = backend

    @method()
    async def GetSecrets(self, connection: "a{sa{sv}}", connection_path: "o", setting_name: "s", hints: "as", flags: "u") -> "a{sa{sv}}":
        if setting_name != "802-11-wireless-security":
            raise DBusError(NM + ".SecretAgent.Error.NoSecrets", tr(Msg.ONLY_PERSONAL_WI_FI_NETWORKS_ARE_SUPPORTED))
        device_id = await self.backend._wifi_secret_device(connection_path)
        device = next(entry for entry in self.backend.state["wifi"]["devices"] if entry["id"] == device_id)
        epoch = self.backend.wifi_epoch
        profile = next((entry for entry in await self.backend._saved_wifi() if entry["id"] == connection_path), None)
        if not profile:
            raise DBusError(NM + ".SecretAgent.Error.NoSecrets", tr(Msg.THIS_SAVED_CONFIGURATION_WAS_REMOVED_OR_IS_INCOMPATIBLE_WITH_THE_ADAPTER))
        settings = unwrap(connection)
        security = "WPA3" if settings.get(setting_name, {}).get("key-mgmt") == "sae" else "WPA2"
        password = await self.backend.ask("text", tr(Msg.WI_FI_PASSWORD), wifi_label(device),
                                          secret=True, wifiSecurity=security, cancel_error=NETWORK_CANCEL,
                                          group="network:" + connection_path, deviceId=device_id, profileUuid=profile["uuid"])
        current = next((entry for entry in await self.backend._saved_wifi() if entry["id"] == connection_path), None)
        if self.backend.wifi_epoch != epoch or not current or current["revision"] != profile["revision"]:
            raise DBusError(NM + ".SecretAgent.Error.NoSecrets", tr(Msg.THE_SAVED_CONFIGURATION_CHANGED_REOPEN_IT_AND_TRY_AGAIN))
        if await self.backend._wifi_secret_device(connection_path) != device_id:
            raise DBusError(NM + ".SecretAgent.Error.NoSecrets", tr(Msg.COULD_NOT_IDENTIFY_THE_ADAPTER_REQUESTING_A_PASSWORD_RECONNECT))
        return {setting_name: {"psk": Variant("s", validate_wifi_password(password, security))}}

    @method()
    def CancelGetSecrets(self, connection_path: "o", setting_name: "s"):
        self.backend.cancel_prompts("network:" + connection_path)

    @method()
    def SaveSecrets(self, connection: "a{sa{sv}}", connection_path: "o"):
        pass

    @method()
    def DeleteSecrets(self, connection: "a{sa{sv}}", connection_path: "o"):
        pass


class SystemBackend(WifiBackend, QObject):
    updated = Signal(object)
    failed = Signal(object)
    operationFailed = Signal(str, object)
    prompt = Signal(object)
    completed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.state = initial_state()
        self.loop = asyncio.new_event_loop()
        self.thread = None
        self.bus = None
        self.pending_prompts = {}
        self.prompt_groups = {}
        self.prompt_devices = {}
        self.refresh_tasks = {}
        self.refresh_again = set()
        self.wifi_refresh_lock = asyncio.Lock()
        self.wifi_operation_lock = asyncio.Lock()
        self.audio_refresh_lock = asyncio.Lock()
        self.audio_operation_lock = asyncio.Lock()
        self.timezone_operation_lock = asyncio.Lock()
        self.timezone_refresh_lock = asyncio.Lock()
        self.timezones = []
        self._init_wifi()
        self.processes = set()
        self.closing = False
        self.agent_registered = False
        self.network_agent_registered = False
        self.discovery_active = False
        self.login_session = None
        self.session_lock_requested = False
        self.session_lock_hint_seen = False
        self.bluetooth_agent = BluezAgent(self)
        self.network_agent = NetworkAgent(self)

    def start(self):
        self.thread = threading.Thread(target=self._run, name="udeck-services", daemon=True)
        self.thread.start()

    def _run(self):
        asyncio.set_event_loop(self.loop)
        self.loop.create_task(self._start())
        self.loop.run_forever()
        self.loop.close()

    async def call(self, destination, path, interface, member, signature="", body=None, timeout=30):
        if self.bus is None:
            raise RuntimeError(tr(Msg.SYSTEM_D_BUS_IS_NOT_CONNECTED_YET))
        response = await asyncio.wait_for(self.bus.call(Message(
            destination=destination, path=path, interface=interface,
            member=member, signature=signature, body=body or [],
        )), timeout)
        if response.message_type == MessageType.ERROR:
            detail = str(response.body[0])[:300] if response.body else ""
            raise RuntimeError(f"{member}: {response.error_name}" + (f" · {detail}" if detail else ""))
        return response.body

    async def get(self, destination, path, interface, property_name):
        return unwrap((await self.call(destination, path, PROPERTIES, "Get", "ss", [interface, property_name]))[0])

    async def properties(self, destination, path, interface):
        return unwrap((await self.call(destination, path, PROPERTIES, "GetAll", "s", [interface]))[0])

    async def set_property(self, destination, path, interface, name, signature, value):
        await self.call(destination, path, PROPERTIES, "Set", "ssv", [interface, name, Variant(signature, value)])

    async def _start(self):
        try:
            self.bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
            self.bus.add_message_handler(self._message)
            for rule in (
                "type='signal',sender='org.freedesktop.NetworkManager'",
                "type='signal',sender='org.bluez'",
                "type='signal',interface='org.freedesktop.DBus',member='NameOwnerChanged',arg0='org.bluez'",
                "type='signal',interface='org.freedesktop.DBus',member='NameOwnerChanged',arg0='org.freedesktop.NetworkManager'",
                "type='signal',sender='org.freedesktop.login1'",
                "type='signal',sender='org.freedesktop.timedate1'",
                "type='signal',interface='org.freedesktop.DBus',member='NameOwnerChanged',arg0='org.freedesktop.timedate1'",
            ):
                await self.call("org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus", "AddMatch", "s", [rule])
            self.bus.export("/io/github/zhubby/uDeck/BluezAgent", self.bluetooth_agent)
            self.bus.export("/org/freedesktop/NetworkManager/SecretAgent", self.network_agent)
            await self.refresh_session()
            self.loop.create_task(self._session_timer())
            await asyncio.gather(self.refresh_wifi(), self.refresh_bluetooth(), self.refresh_timezone())
        except Exception as error:
            self.failed.emit(tr(Msg.SYSTEM_SERVICE_INITIALIZATION_FAILED_VALUE0, value0=error))
        await self.refresh_audio()
        self.refresh_hardware()
        self.loop.create_task(self._watch_audio())
        self.loop.create_task(self._hardware_timer())

    def _message(self, message):
        if message.message_type != MessageType.SIGNAL:
            return
        if message.path == self.login_session and message.member == 'Lock':
            self.session_lock_requested = True
            self.publish('sessionInput', {'available': True, 'active': True, 'locked': True})
        elif message.path == self.login_session and message.member == 'Unlock':
            self.session_lock_requested = False
            self.schedule_refresh('session')
        elif message.member == 'PrepareForSleep' and message.body and message.body[0]:
            self.publish('sessionInput', {'available': True, 'active': False, 'locked': True})
        elif (message.path or '').startswith('/org/freedesktop/login1'):
            self.schedule_refresh('session')
        elif message.member == "NameOwnerChanged":
            if message.body[0] == TIMEDATE:
                self.timezones = []
                self.schedule_refresh("timezone")
            elif message.body[0] == BLUEZ:
                self.agent_registered = False
                self.schedule_refresh("bluetooth")
            elif message.body[0] == NM:
                self.network_agent_registered = False
                self._reset_wifi()
                self.schedule_refresh("wifi")
        elif message.path == TIMEDATE_PATH:
            self.schedule_refresh("timezone")
        elif (message.path or "").startswith(NM_ROOT):
            if message.member == "DeviceRemoved" and message.body:
                self.cancel_prompts("network", device_id=message.body[0])
            self.schedule_refresh("wifi")
        elif (message.path or "").startswith("/org/bluez") or message.interface == "org.freedesktop.DBus.ObjectManager":
            self.schedule_refresh("bluetooth")

    def schedule_refresh(self, component):
        if self.closing:
            return
        if component in self.refresh_tasks:
            self.refresh_again.add(component)
            return

        async def refresh():
            try:
                while not self.closing:
                    await asyncio.sleep(0.35)
                    self.refresh_again.discard(component)
                    await getattr(self, "refresh_" + component)()
                    if component not in self.refresh_again:
                        break
            finally:
                self.refresh_tasks.pop(component, None)

        self.refresh_tasks[component] = self.loop.create_task(refresh())

    async def refresh_session(self):
        try:
            if not self.login_session:
                session = os.environ.get('XDG_SESSION_ID')
                member, signature, arguments = ('GetSession', 's', [session]) if session else ('GetSessionByPID', 'u', [os.getpid()])
                self.login_session = (await self.call('org.freedesktop.login1', '/org/freedesktop/login1', 'org.freedesktop.login1.Manager', member, signature, arguments))[0]
            properties = await self.properties('org.freedesktop.login1', self.login_session, 'org.freedesktop.login1.Session')
            locked = bool(properties.get('LockedHint'))
            if locked:
                self.session_lock_hint_seen = True
            elif self.session_lock_hint_seen:
                self.session_lock_requested = False
                self.session_lock_hint_seen = False
            value = {'available': True, 'active': bool(properties.get('Active')), 'locked': locked or self.session_lock_requested}
        except Exception as error:
            value = {'available': False, 'active': False, 'locked': True, 'error': error_text(error)}
        if self.state.get('sessionInput') != value:
            self.publish('sessionInput', value)

    async def _session_timer(self):
        while True:
            await asyncio.sleep(5)
            await self.refresh_session()

    def publish(self, component, value):
        self.state[component] = value
        # Python object signals preserve deferred messages. Detach the payload
        # so queued UI deliveries cannot share mutable service state.
        self.updated.emit(deepcopy({component: value}))

    async def refresh_timezone(self):
        async with self.timezone_refresh_lock:
            previous = self.state["timezone"]
            try:
                current = await self.get(TIMEDATE, TIMEDATE_PATH, TIMEDATE, "Timezone")
                if not self.timezones:
                    self.timezones = sorted(set((await self.call(TIMEDATE, TIMEDATE_PATH, TIMEDATE, "ListTimezones"))[0]))
                value = {"available": True, "current": current, "zones": self.timezones}
            except Exception as error:
                value = {**previous, "available": False, "error": tr(Msg.TIME_ZONE_SERVICE_UNAVAILABLE_ERROR, error=error_text(error))}
            if value != previous:
                self.publish("timezone", value)
            return value["available"]

    async def _set_timezone(self, payload):
        zone = payload.get("timezone")
        if not isinstance(zone, str) or not zone:
            raise ValueError(tr(Msg.INVALID_TIME_ZONE))
        if not await self.refresh_timezone():
            raise RuntimeError(self.state["timezone"]["error"])
        if zone not in self.timezones:
            raise ValueError(tr(Msg.INVALID_TIME_ZONE))
        if zone == self.state["timezone"]["current"]:
            return
        try:
            await self.call(TIMEDATE, TIMEDATE_PATH, TIMEDATE, "SetTimezone", "sb", [zone, True], timeout=120)
        except Exception as error:
            await self.refresh_timezone()
            raise RuntimeError(tr(Msg.COULD_NOT_CHANGE_TIME_ZONE_ERROR, error=error_text(error))) from error
        if not await self.refresh_timezone() or self.state["timezone"]["current"] != zone:
            raise RuntimeError(tr(Msg.COULD_NOT_VERIFY_THE_NEW_TIME_ZONE_CHECK_THE_CURRENT_SYSTEM_SETTING))

    async def refresh_bluetooth(self):
        try:
            objects = unwrap((await self.call(BLUEZ, "/", "org.freedesktop.DBus.ObjectManager", "GetManagedObjects"))[0])
            self.adapter = next((path for path, interfaces in objects.items() if BLUEZ + ".Adapter1" in interfaces), None)
            if not self.adapter:
                self.publish("bluetooth", {"available": False, "powered": False, "devices": [], "discovering": False, "error": tr(Msg.NO_BLUETOOTH_ADAPTER)})
                return
            if not self.agent_registered:
                await self.call(BLUEZ, "/org/bluez", BLUEZ + ".AgentManager1", "RegisterAgent", "os", ["/io/github/zhubby/uDeck/BluezAgent", "KeyboardDisplay"])
                if os.environ.get("XDG_SESSION_DESKTOP") == "udeck":
                    await self.call(BLUEZ, "/org/bluez", BLUEZ + ".AgentManager1", "RequestDefaultAgent", "o", ["/io/github/zhubby/uDeck/BluezAgent"])
                self.agent_registered = True
            adapter = objects[self.adapter][BLUEZ + ".Adapter1"]
            devices = []
            for path, interfaces in objects.items():
                information = interfaces.get(BLUEZ + ".Device1")
                if information is not None and information.get("Adapter") == self.adapter:
                    devices.append({"id": path, "name": information.get("Alias") or information.get("Name") or information.get("Address", tr(Msg.BLUETOOTH_DEVICE)),
                                    "paired": information.get("Paired", False), "connected": information.get("Connected", False),
                                    "trusted": information.get("Trusted", False), "resolved": information.get("ServicesResolved", False)})
            self.publish("bluetooth", {"available": True, "powered": adapter.get("Powered", False),
                                       "discovering": adapter.get("Discovering", False),
                                       "devices": sorted(devices, key=lambda device: (not device["connected"], not device["paired"], device["name"]))})
        except Exception as error:
            self.publish("bluetooth", {"available": False, "powered": False, "devices": [], "discovering": False, "error": error_text(error)})

    async def command(self, *arguments, timeout=10):
        process = await asyncio.create_subprocess_exec(*arguments, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        self.processes.add(process)
        try:
            output, errors = await asyncio.wait_for(process.communicate(), timeout)
            if process.returncode:
                raise RuntimeError(tr(Msg.VALUE0_FAILED, value0=arguments[0]))
            return output.decode(errors="replace")
        finally:
            if process.returncode is None:
                process.kill()
                await process.wait()
            self.processes.discard(process)

    async def refresh_audio(self):
        async with self.audio_refresh_lock:
            kinds = ("sinks", "sources", "cards")
            results = await asyncio.gather(*(self.command("pactl", "--format=json", "list", kind) for kind in kinds),
                                           self.command("pactl", "get-default-sink"),
                                           self.command("pactl", "get-default-source"), return_exceptions=True)
            values, errors = {}, {}
            for kind, result in zip(kinds, results[:3], strict=True):
                try:
                    if isinstance(result, BaseException):
                        raise result
                    values[kind] = json.loads(result)
                    if not isinstance(values[kind], list):
                        raise ValueError(tr(Msg.INVALID_AUDIO_DEVICE_RESPONSE))
                except Exception as error:
                    values[kind] = []
                    errors[kind] = error_text(error)
            default_sink, default_source = (value.strip() if isinstance(value, str) else "" for value in results[3:])
            value = audio_state(values["sinks"], values["sources"], values["cards"], default_sink, default_source)
            value.update(available="sinks" not in errors or "sources" not in errors,
                         outputError=errors.get("sinks", ""), inputError=errors.get("sources", ""),
                         cardError=errors.get("cards", ""))
            self.publish("audio", value)

    async def _execute_audio(self, action, payload):
        await self.refresh_audio()
        audio = self.state["audio"]
        if action == "audio_profile":
            card = next((card for card in audio.get("cards", []) if card["id"] == payload["id"]), None)
            if card is None:
                raise ValueError(tr(Msg.THE_AUDIO_DEVICE_WAS_REMOVED))
            profile = next((profile for profile in card["profiles"] if profile["id"] == payload["profile"]), None)
            if profile is None or not profile["available"]:
                raise ValueError(tr(Msg.BLUETOOTH_AUDIO_MODE_IS_UNAVAILABLE))
            await self.command("pactl", "set-card-profile", card["id"], profile["id"])
        else:
            inputs = action in ("audio_input", "audio_input_volume", "audio_input_mute")
            entries = audio.get("inputs" if inputs else "outputs", [])
            identifier = payload.get("id")
            target = next((entry for entry in entries if entry["id"] == identifier), None) if identifier else next((entry for entry in entries if entry["active"]), None)
            if target is None:
                raise ValueError(tr(Msg.THE_AUDIO_DEVICE_WAS_REMOVED))
            kind = "source" if inputs else "sink"
            if action in ("audio_input", "audio_output"):
                await self.command("pactl", "set-default-" + kind, target["id"])
            elif action in ("audio_input_volume", "volume"):
                level = float(payload["value"])
                if not math.isfinite(level):
                    raise ValueError(tr(Msg.INVALID_AUDIO_VOLUME))
                await self.command("pactl", "set-" + kind + "-volume", target["id"], f"{max(0, min(1, level)) * 100:.0f}%")
            else:
                await self.command("pactl", "set-" + kind + "-mute", target["id"], "toggle")
        await self.refresh_audio()
        if action == "audio_profile":
            for attempt in range(6):
                card = next((card for card in self.state["audio"].get("cards", []) if card["id"] == payload["id"]), {})
                if any(profile["id"] == payload["profile"] and profile["active"] for profile in card.get("profiles", [])):
                    return
                if attempt < 5:
                    await asyncio.sleep(0.2)
                    await self.refresh_audio()
            raise RuntimeError(tr(Msg.THE_BLUETOOTH_AUDIO_MODE_CHANGE_WAS_NOT_CONFIRMED))
        if action in ("audio_input", "audio_output"):
            entries = self.state["audio"].get("inputs" if action == "audio_input" else "outputs", [])
            if not any(entry["id"] == payload["id"] and entry["active"] for entry in entries):
                raise RuntimeError(tr(Msg.THE_AUDIO_DEVICE_CHANGE_WAS_NOT_CONFIRMED))

    async def _watch_audio(self):
        try:
            process = await asyncio.create_subprocess_exec("pactl", "subscribe", stdout=asyncio.subprocess.PIPE,
                                                           stderr=asyncio.subprocess.DEVNULL,
                                                           env={**os.environ, "LC_ALL": "C"})
            self.processes.add(process)
            try:
                while line := await process.stdout.readline():
                    # Each read-only pactl query creates a client. Refreshing on
                    # those events would make our own queries trigger forever.
                    facility = line.rsplit(b" on ", 1)[-1].split(b" #", 1)[0]
                    if facility in (b"sink", b"source", b"card", b"server"):
                        self.schedule_refresh("audio")
            finally:
                if process.returncode is None:
                    process.kill()
                await process.wait()
                self.processes.discard(process)
        except OSError:
            pass

    def refresh_hardware(self):
        backlights = sorted(Path("/sys/class/backlight").glob("*"))
        try:
            self.backlight = backlights[0]
            maximum = int((self.backlight / "max_brightness").read_text())
            value = int((self.backlight / "brightness").read_text()) / maximum
            self.publish("brightness", {"available": os.access(self.backlight / "brightness", os.W_OK), "value": value})
        except (OSError, ValueError, IndexError, ZeroDivisionError):
            self.publish("brightness", {"available": False, "value": 0})
        self.publish("battery", read_battery(Path("/sys/class/power_supply")))

    async def _hardware_timer(self):
        while True:
            await asyncio.sleep(5)
            self.refresh_hardware()

    def request(self, action, payload=None):
        if not self.thread or self.closing:
            return
        if action.startswith("wifi_"):
            payload = {"wifiEpoch": self.wifi_epoch, **(payload or {})}
        future = asyncio.run_coroutine_threadsafe(self._execute(action, payload or {}), self.loop)

        def complete(result):
            try:
                result.result()
                self.completed.emit(action)
            except asyncio.CancelledError:
                pass
            except Exception as error:
                if not self.closing:
                    self.operationFailed.emit(action, error_text(error))

        future.add_done_callback(complete)

    async def _execute(self, action, payload):
        if action == "timezone_set":
            async with self.timezone_operation_lock:
                await self._set_timezone(payload)
        elif action == "wifi_cancel_connect":
            await self._execute_wifi(action, payload)
        elif action.startswith("wifi_"):
            async with self.wifi_operation_lock:
                await self._execute_wifi(action, payload)
        elif action in AUDIO_ACTIONS:
            async with self.audio_operation_lock:
                await self._execute_audio(action, payload)
        elif action == "bluetooth_power":
            await self.set_property(BLUEZ, self.adapter, BLUEZ + ".Adapter1", "Powered", "b", bool(payload["enabled"]))
            await self.refresh_bluetooth()
        elif action == "bluetooth_scan":
            await self.call(BLUEZ, self.adapter, BLUEZ + ".Adapter1", "StartDiscovery")
            self.discovery_active = True
            self.loop.create_task(self._stop_discovery_later())
            await self.refresh_bluetooth()
        elif action == "bluetooth_stop":
            if self.discovery_active:
                await self.call(BLUEZ, self.adapter, BLUEZ + ".Adapter1", "StopDiscovery")
                self.discovery_active = False
        elif action in ("bluetooth_connect", "bluetooth_disconnect", "bluetooth_pair"):
            device = payload["id"]
            operation = {"bluetooth_connect": "Connect", "bluetooth_disconnect": "Disconnect", "bluetooth_pair": "Pair"}[action]
            try:
                await self.call(BLUEZ, device, BLUEZ + ".Device1", operation, timeout=120)
            finally:
                self.prompt.emit({"dismiss": "bluez-display"})
            if action == "bluetooth_pair":
                await self.set_property(BLUEZ, device, BLUEZ + ".Device1", "Trusted", "b", True)
                await self.refresh_bluetooth()
                await self.call(BLUEZ, device, BLUEZ + ".Device1", "Connect", timeout=30)
            await self.refresh_bluetooth()
        elif action == "bluetooth_remove":
            await self.call(BLUEZ, self.adapter, BLUEZ + ".Adapter1", "RemoveDevice", "o", [payload["id"]])
            await self.refresh_bluetooth()
        elif action == "brightness":
            maximum = int((self.backlight / "max_brightness").read_text())
            (self.backlight / "brightness").write_text(str(max(1, min(maximum, round(maximum * payload["value"])))))
            self.refresh_hardware()
        elif action in ("reboot", "poweroff"):
            await self.call("org.freedesktop.login1", "/org/freedesktop/login1", "org.freedesktop.login1.Manager", "Reboot" if action == "reboot" else "PowerOff", "b", [True])
        elif action == "logout":
            if os.environ.get("XDG_SESSION_DESKTOP") != "udeck":
                raise RuntimeError(tr(Msg.LOGOUT_REQUIRES_STANDALONE_SESSION))
            session = os.environ.get("XDG_SESSION_ID")
            if not session:
                raise RuntimeError(tr(Msg.COULD_NOT_IDENTIFY_THE_CURRENT_LOGIN_SESSION))
            await self.call("org.freedesktop.login1", "/org/freedesktop/login1", "org.freedesktop.login1.Manager", "TerminateSession", "s", [session])
        elif action == "lock":
            await self.command("swaylock", timeout=None)
        elif action == "blank":
            process = await asyncio.create_subprocess_exec("swayidle", "-w", "timeout", "1", "wlopm --off '*'", "resume", "wlopm --on '*'; kill -TERM \"$PPID\"", stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
            self.processes.add(process)
        elif action == "refresh":
            await asyncio.gather(self.refresh_wifi(), self.refresh_bluetooth(), self.refresh_audio(), self.refresh_timezone())
            self.refresh_hardware()
        else:
            raise ValueError(tr(Msg.UNKNOWN_SYSTEM_OPERATION))

    async def _stop_discovery_later(self):
        await asyncio.sleep(30)
        try:
            await self._execute("bluetooth_stop", {})
            await self.refresh_bluetooth()
        except Exception:
            pass

    async def ask(self, kind, title, body, cancel_error="org.bluez.Error.Rejected", group="bluez", **options):
        token = uuid.uuid4().hex
        future = self.loop.create_future()
        self.pending_prompts[token] = future
        self.prompt_groups[token] = group
        self.prompt_devices[token] = options.get("deviceId")
        self.prompt.emit({"kind": kind, "title": title, "body": body, "token": token, **options})
        try:
            answer = await asyncio.wait_for(future, 120)
            if answer is None or (kind == "confirm" and answer is not True):
                raise DBusError(cancel_error, tr(Msg.CANCELLED_BY_USER))
            return answer
        except TimeoutError as error:
            raise DBusError(cancel_error, tr(Msg.CONFIRMATION_TIMED_OUT)) from error
        finally:
            self.pending_prompts.pop(token, None)
            self.prompt_groups.pop(token, None)
            self.prompt_devices.pop(token, None)
            self.prompt.emit({"dismiss": token})

    def information(self, title, body):
        self.prompt.emit({"kind": "information", "title": title, "body": body, "token": "bluez-display"})

    def reply(self, token, value):
        def deliver():
            future = self.pending_prompts.get(token)
            if future is not None and not future.done():
                future.set_result(value)

        self.loop.call_soon_threadsafe(deliver)

    def cancel_prompts(self, group="bluez", *, device_id=None):
        for token in list(self.pending_prompts):
            if device_id is not None and self.prompt_devices.get(token) != device_id:
                continue
            prompt_group = self.prompt_groups.get(token, "")
            if group is None or prompt_group == group or (group == "network" and prompt_group.startswith("network:")):
                self.reply(token, None)
        if group in (None, "bluez"):
            self.prompt.emit({"dismiss": "bluez-display"})

    def close(self):
        if not self.thread or not self.thread.is_alive():
            return
        self.closing = True

        async def shutdown():
            self.cancel_prompts(None)
            try:
                if self.state["bluetooth"].get("discovering"):
                    await self._execute("bluetooth_stop", {})
            except Exception:
                pass
            for task in asyncio.all_tasks(self.loop):
                if task is not asyncio.current_task():
                    task.cancel()
            for process in list(self.processes):
                if process.returncode is None:
                    process.terminate()
                    await process.wait()
            if self.bus:
                self.bus.disconnect()
            await asyncio.sleep(0)

        future = asyncio.run_coroutine_threadsafe(shutdown(), self.loop)
        try:
            future.result(timeout=4)
        except Exception:
            pass
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join(timeout=1)
