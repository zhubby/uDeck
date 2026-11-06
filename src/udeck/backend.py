import asyncio
import getpass
import json
import os
import threading
import uuid
from pathlib import Path

from dbus_next import BusType, DBusError, Message, MessageType, Variant
from dbus_next.aio import MessageBus
from dbus_next.service import ServiceInterface, method
from PySide6.QtCore import QObject, Signal

from .mock import initial_state
from .wifi import wifi_identity, wifi_label, wifi_security

NM = "org.freedesktop.NetworkManager"
NM_ROOT = "/org/freedesktop/NetworkManager"
BLUEZ = "org.bluez"
PROPERTIES = "org.freedesktop.DBus.Properties"
NETWORK_CANCEL = NM + ".SecretAgent.Error.UserCanceled"


def unwrap(value):
    if isinstance(value, Variant):
        return unwrap(value.value)
    if isinstance(value, dict):
        return {key: unwrap(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [unwrap(item) for item in value]
    return value


def validate_wifi_password(password, security):
    value = str(password)
    if not value or "\x00" in value:
        raise ValueError("Wi-Fi 密码不能为空或包含空字符")
    if security == "WPA3":
        return value
    if not 8 <= len(value.encode()) <= 63 and not (len(value) == 64 and all(character in "0123456789abcdefABCDEF" for character in value)):
        raise ValueError("WPA2 密码需为 8–63 字节，或 64 位十六进制 PSK")
    return value


class BluezAgent(ServiceInterface):
    def __init__(self, backend):
        super().__init__("org.bluez.Agent1")
        self.backend = backend

    @method()
    def Release(self):
        self.backend.cancel_prompts()

    @method()
    async def RequestPinCode(self, device: "o") -> "s":
        response = await self.backend.ask("text", "蓝牙 PIN", "请输入设备要求的 PIN", secret=True)
        return str(response)

    @method()
    def DisplayPinCode(self, device: "o", pincode: "s"):
        self.backend.information("蓝牙配对", f"请在另一台设备输入 PIN：{pincode}")

    @method()
    async def RequestPasskey(self, device: "o") -> "u":
        response = await self.backend.ask("text", "蓝牙配对码", "输入 0–999999 的数字配对码", numeric=True)
        if not str(response).isdigit() or not 0 <= int(response) <= 999999:
            raise DBusError("org.bluez.Error.Rejected", "配对码无效")
        return int(response)

    @method()
    def DisplayPasskey(self, device: "o", passkey: "u", entered: "q"):
        self.backend.information("蓝牙配对", f"请在另一台设备输入：{passkey:06d} · 已输入 {entered} 位")

    @method()
    async def RequestConfirmation(self, device: "o", passkey: "u"):
        await self.backend.ask("confirm", "确认蓝牙配对", f"两台设备是否都显示 {passkey:06d}？")

    @method()
    async def RequestAuthorization(self, device: "o"):
        await self.backend.ask("confirm", "蓝牙配对请求", "允许这台设备与 uConsole 配对？")

    @method()
    async def AuthorizeService(self, device: "o", service_uuid: "s"):
        await self.backend.ask("confirm", "蓝牙服务授权", f"允许已配对设备使用服务 {service_uuid}？")

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
            raise DBusError(NM + ".SecretAgent.Error.NoSecrets", "仅支持个人 Wi-Fi 网络")
        device_id = await self.backend._wifi_secret_device(connection_path)
        device = next(entry for entry in self.backend.state["wifi"]["devices"] if entry["id"] == device_id)
        password = await self.backend.ask("text", "Wi-Fi 密码", wifi_label(device),
                                          secret=True, cancel_error=NETWORK_CANCEL,
                                          group="network:" + connection_path, deviceId=device_id)
        if await self.backend._wifi_secret_device(connection_path) != device_id:
            raise DBusError(NM + ".SecretAgent.Error.NoSecrets", "无法确认请求密码的无线网卡，请重新连接")
        return {setting_name: {"psk": Variant("s", str(password))}}

    @method()
    def CancelGetSecrets(self, connection_path: "o", setting_name: "s"):
        self.backend.cancel_prompts("network:" + connection_path)

    @method()
    def SaveSecrets(self, connection: "a{sa{sv}}", connection_path: "o"):
        pass

    @method()
    def DeleteSecrets(self, connection: "a{sa{sv}}", connection_path: "o"):
        pass


class SystemBackend(QObject):
    updated = Signal(dict)
    failed = Signal(str)
    operationFailed = Signal(str, str)
    prompt = Signal(dict)
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
        self.wifi_profile_devices = {}
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
            raise RuntimeError("系统 D-Bus 尚未连接")
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
            ):
                await self.call("org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus", "AddMatch", "s", [rule])
            self.bus.export("/io/github/zhubby/uDeck/BluezAgent", self.bluetooth_agent)
            self.bus.export("/org/freedesktop/NetworkManager/SecretAgent", self.network_agent)
            await asyncio.gather(self.refresh_wifi(), self.refresh_bluetooth())
            if os.environ.get('UDECK_SESSION') == '1':
                await self.refresh_session()
                self.loop.create_task(self._session_timer())
        except Exception as error:
            self.failed.emit(f"系统服务初始化失败：{error}")
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
        elif (message.path or '').startswith('/org/freedesktop/login1') and os.environ.get('UDECK_SESSION') == '1':
            self.schedule_refresh('session')
        elif message.member == "NameOwnerChanged":
            if message.body[0] == BLUEZ:
                self.agent_registered = False
                self.schedule_refresh("bluetooth")
            elif message.body[0] == NM:
                self.network_agent_registered = False
                self.wifi_profile_devices.clear()
                self.cancel_prompts("network")
                self.schedule_refresh("wifi")
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
            value = {'available': False, 'active': False, 'locked': True, 'error': str(error)}
        if self.state.get('sessionInput') != value:
            self.publish('sessionInput', value)

    async def _session_timer(self):
        while True:
            await asyncio.sleep(5)
            await self.refresh_session()

    def publish(self, component, value):
        self.state[component] = value
        self.updated.emit({component: value})

    async def refresh_wifi(self):
        async with self.wifi_refresh_lock:
            await self._refresh_wifi()

    async def _refresh_wifi(self):
        try:
            agent_error = ""
            if not self.network_agent_registered:
                try:
                    await self.call(NM, NM_ROOT + "/AgentManager", NM + ".AgentManager", "RegisterWithCapabilities", "su", ["io.github.zhubby.uDeck", 0])
                    self.network_agent_registered = True
                except Exception as error:
                    agent_error = str(error)
            enabled = await self.get(NM, NM_ROOT, NM, "WirelessEnabled")
            paths = (await self.call(NM, NM_ROOT, NM, "GetDevices"))[0]
            saved = await self._saved_wifi()
            usage = await self._wifi_profile_usage()
            previous = {entry["id"]: entry for entry in self.state["wifi"].get("devices", [])}
            devices = []
            for device_path in paths:
                try:
                    if await self.get(NM, device_path, NM + ".Device", "DeviceType") != 2:
                        continue
                except Exception:
                    if device_path not in previous:
                        continue
                devices.append(await self._read_wifi_device(device_path, saved, usage, previous.get(device_path, {})))
            devices.sort(key=lambda entry: ({"builtin": 0, "usb": 1}.get(entry["kind"], 2), entry["interface"], entry["id"]))
            present = {entry["id"] for entry in devices}
            for device_id in previous.keys() - present:
                self.cancel_prompts("network", device_id=device_id)
            self.wifi_profile_devices = {profile: device for profile, device in self.wifi_profile_devices.items() if device in present}
            self.publish("wifi", {"available": bool(devices), "enabled": enabled, "devices": devices,
                                  "error": "" if devices else "未检测到无线网卡", "agentError": agent_error})
        except Exception as error:
            self.publish("wifi", {"available": False, "enabled": False, "devices": [], "error": str(error)})

    async def _read_wifi_device(self, path, saved, usage, previous):
        result = {"id": path, **wifi_identity(previous.get("interface", "")), "available": False,
                  "managed": True, "deviceState": 0, "connected": "", "connecting": "",
                  "networks": [], "saved": [], "error": ""}
        try:
            device = await self.properties(NM, path, NM + ".Device")
            result.update(wifi_identity(device.get("Interface", "")))
            device_state = device.get("State", 0)
            result.update({"managed": device.get("Managed", True), "deviceState": device_state,
                           "activeConnection": device.get("ActiveConnection", "/")})
            profiles = self._wifi_device_profiles(path, device, saved, usage)
            result["saved"] = profiles
            wireless = await self.properties(NM, path, NM + ".Device.Wireless")
            networks = {}
            for access_point in wireless.get("AccessPoints", []):
                try:
                    information = await self.properties(NM, access_point, NM + ".AccessPoint")
                except Exception:
                    continue
                ssid_bytes = bytes(information.get("Ssid", []))
                if not ssid_bytes:
                    continue
                name = ssid_bytes.decode("utf-8", errors="replace")
                security, keys = wifi_security(information)
                entry = {"id": access_point, "name": name, "ssid": list(ssid_bytes),
                         "strength": information.get("Strength", 0), "security": security,
                         "saved": any(profile["ssid"] == list(ssid_bytes) and profile["keyManagement"] in (keys or [""]) for profile in profiles),
                         "keyManagement": keys,
                         "secured": security != "开放网络", "unsupported": security in ("企业网络", "不支持的加密"),
                         "connected": access_point == wireless.get("ActiveAccessPoint") and device_state == 100,
                         "connecting": access_point == wireless.get("ActiveAccessPoint") and 40 <= device_state < 100}
                deduplication_key = (ssid_bytes, security)
                existing = networks.get(deduplication_key)
                if not existing or (entry["connected"], entry["connecting"], entry["strength"]) > (existing["connected"], existing["connecting"], existing["strength"]):
                    networks[deduplication_key] = entry
            entries = sorted(networks.values(), key=lambda entry: (not entry["connected"], -entry["strength"]))
            reason = device.get("StateReason", [device_state, 0])[1]
            failure = f"连接失败 · NetworkManager 原因代码 {reason}" if device_state == 120 else ""
            result.update({"available": True, "networks": entries,
                           "connected": next((entry["name"] for entry in entries if entry["connected"]), ""),
                           "connecting": next((entry["name"] for entry in entries if entry["connecting"]), ""), "error": failure})
            if device_state == 100 and not result["connected"] and usage is not None:
                profile = next((profile for profile in saved if path in usage.get(profile["id"], set())), None)
                if profile:
                    result["connected"] = bytes(profile["ssid"]).decode("utf-8", errors="replace")
        except Exception as error:
            result["error"] = "无法读取网卡 · " + str(error)
        return result

    async def _wifi_profile_usage(self):
        try:
            usage = {}
            for path in await self.get(NM, NM_ROOT, NM, "ActiveConnections"):
                properties = await self.properties(NM, path, NM + ".Connection.Active")
                if properties.get("State") != 4:
                    usage.setdefault(properties["Connection"], set()).update(properties.get("Devices", []))
            return usage
        except Exception:
            # Unknown usage must never permit moving a single-instance profile.
            return None

    def _wifi_device_profiles(self, device_id, device, profiles, usage):
        compatible = set(device.get("AvailableConnections", []))
        result = []
        for profile in profiles:
            if profile["id"] not in compatible:
                continue
            blocked = ""
            if profile["multiConnect"] not in (2, 3):
                if usage is None:
                    blocked = "暂时无法确认此配置是否正在使用"
                elif usage.get(profile["id"], set()) - {device_id}:
                    blocked = "另一张网卡正在使用 · 可从网络列表另建连接"
            result.append({**profile, "blocked": blocked})
        return result

    async def _saved_wifi(self):
        profiles = []
        connections = (await self.call(NM, NM_ROOT + "/Settings", NM + ".Settings", "ListConnections"))[0]
        for path in connections:
            try:
                settings = unwrap((await self.call(NM, path, NM + ".Settings.Connection", "GetSettings"))[0])
                wireless = settings.get("802-11-wireless")
                if not wireless or wireless.get("mode", "infrastructure") != "infrastructure":
                    continue
                key = settings.get("802-11-wireless-security", {}).get("key-mgmt", "")
                ssid = list(wireless.get("ssid", []))
                profiles.append({"id": path, "name": settings.get("connection", {}).get("id", bytes(ssid).decode("utf-8", errors="replace")),
                                 "ssid": ssid, "keyManagement": key, "multiConnect": settings.get("connection", {}).get("multi-connect", 0),
                                 "unsupported": key not in ("", "wpa-psk", "sae")})
            except Exception:
                continue
        return profiles

    async def refresh_bluetooth(self):
        try:
            objects = unwrap((await self.call(BLUEZ, "/", "org.freedesktop.DBus.ObjectManager", "GetManagedObjects"))[0])
            self.adapter = next((path for path, interfaces in objects.items() if BLUEZ + ".Adapter1" in interfaces), None)
            if not self.adapter:
                self.publish("bluetooth", {"available": False, "powered": False, "devices": [], "discovering": False, "error": "没有蓝牙适配器"})
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
                    devices.append({"id": path, "name": information.get("Alias") or information.get("Name") or information.get("Address", "蓝牙设备"),
                                    "paired": information.get("Paired", False), "connected": information.get("Connected", False),
                                    "trusted": information.get("Trusted", False), "resolved": information.get("ServicesResolved", False)})
            self.publish("bluetooth", {"available": True, "powered": adapter.get("Powered", False),
                                       "discovering": adapter.get("Discovering", False),
                                       "devices": sorted(devices, key=lambda device: (not device["connected"], not device["paired"], device["name"]))})
        except Exception as error:
            self.publish("bluetooth", {"available": False, "powered": False, "devices": [], "discovering": False, "error": str(error)})

    async def command(self, *arguments, timeout=10):
        process = await asyncio.create_subprocess_exec(*arguments, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        self.processes.add(process)
        try:
            output, errors = await asyncio.wait_for(process.communicate(), timeout)
            if process.returncode:
                raise RuntimeError(f"{arguments[0]} 执行失败")
            return output.decode(errors="replace")
        finally:
            if process.returncode is None:
                process.kill()
                await process.wait()
            self.processes.discard(process)

    async def refresh_audio(self):
        try:
            volume_information = await self.command("wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@")
            volume = float(volume_information.split()[1])
            sinks = json.loads(await self.command("pactl", "--format=json", "list", "sinks"))
            default = (await self.command("pactl", "get-default-sink")).strip()
            outputs = [{"id": sink["name"], "name": sink.get("description", sink["name"]), "active": sink["name"] == default} for sink in sinks]
            self.publish("audio", {"available": True, "volume": min(1, volume), "muted": "MUTED" in volume_information, "outputs": outputs})
        except Exception as error:
            self.publish("audio", {"available": False, "volume": 0, "muted": False, "outputs": [], "error": str(error)})

    async def _watch_audio(self):
        try:
            process = await asyncio.create_subprocess_exec("pactl", "subscribe", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
            self.processes.add(process)
            try:
                while await process.stdout.readline():
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
        for supply in Path("/sys/class/power_supply").glob("*"):
            try:
                if (supply / "type").read_text().strip() == "Battery":
                    self.publish("battery", {"available": True, "capacity": int((supply / "capacity").read_text()), "charging": (supply / "status").read_text().strip() in ("Charging", "Full")})
                    return
            except (OSError, ValueError):
                continue

    async def _hardware_timer(self):
        while True:
            await asyncio.sleep(30)
            self.refresh_hardware()

    def request(self, action, payload=None):
        if not self.thread or self.closing:
            return
        future = asyncio.run_coroutine_threadsafe(self._execute(action, payload or {}), self.loop)

        def complete(result):
            try:
                result.result()
                self.completed.emit(action)
            except asyncio.CancelledError:
                pass
            except Exception as error:
                if not self.closing:
                    self.operationFailed.emit(action, str(error))

        future.add_done_callback(complete)

    async def _execute(self, action, payload):
        if action.startswith("wifi_"):
            async with self.wifi_operation_lock:
                await self._execute_wifi(action, payload)
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
        elif action == "volume":
            await self.command("wpctl", "set-volume", "--limit", "1.0", "@DEFAULT_AUDIO_SINK@", str(max(0, min(1, payload["value"]))))
            await self.refresh_audio()
        elif action == "mute":
            await self.command("wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "toggle")
            await self.refresh_audio()
        elif action == "audio_output":
            valid_outputs = {output["id"] for output in self.state["audio"].get("outputs", [])}
            if payload["id"] not in valid_outputs:
                raise ValueError("音频设备已移除")
            await self.command("pactl", "set-default-sink", payload["id"])
            await self.refresh_audio()
        elif action == "brightness":
            maximum = int((self.backlight / "max_brightness").read_text())
            (self.backlight / "brightness").write_text(str(max(1, min(maximum, round(maximum * payload["value"])))))
            self.refresh_hardware()
        elif action in ("reboot", "poweroff"):
            await self.call("org.freedesktop.login1", "/org/freedesktop/login1", "org.freedesktop.login1.Manager", "Reboot" if action == "reboot" else "PowerOff", "b", [True])
        elif action == "logout":
            if os.environ.get("XDG_SESSION_DESKTOP") != "udeck":
                raise RuntimeError("仅能从独立 uDeck 会话注销；窗口预览不会注销原桌面")
            session = os.environ.get("XDG_SESSION_ID")
            if not session:
                raise RuntimeError("无法确定当前登录会话")
            await self.call("org.freedesktop.login1", "/org/freedesktop/login1", "org.freedesktop.login1.Manager", "TerminateSession", "s", [session])
        elif action == "lock":
            await self.command("swaylock", timeout=None)
        elif action == "blank":
            process = await asyncio.create_subprocess_exec("swayidle", "-w", "timeout", "1", "wlopm --off '*'", "resume", "wlopm --on '*'; kill -TERM \"$PPID\"", stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
            self.processes.add(process)
        elif action == "refresh":
            await asyncio.gather(self.refresh_wifi(), self.refresh_bluetooth(), self.refresh_audio())
            self.refresh_hardware()
        else:
            raise ValueError("未知系统操作")

    async def _stop_discovery_later(self):
        await asyncio.sleep(30)
        try:
            await self._execute("bluetooth_stop", {})
            await self.refresh_bluetooth()
        except Exception:
            pass

    async def _wifi_secret_device(self, connection_path):
        active_devices, activating_devices = set(), set()
        try:
            for path in await self.get(NM, NM_ROOT, NM, "ActiveConnections"):
                properties = await self.properties(NM, path, NM + ".Connection.Active")
                if properties.get("Connection") == connection_path and properties.get("State") != 4:
                    active_devices.update(properties.get("Devices", []))
                    if properties.get("State") == 1:
                        activating_devices.update(properties.get("Devices", []))
        except Exception as error:
            raise DBusError(NM + ".SecretAgent.Error.NoSecrets", "无法确认请求密码的无线网卡，请重新选择网卡连接") from error
        # SecretAgent names a profile, so prefer its one activating device.
        if len(activating_devices) == 1:
            device_id = next(iter(activating_devices))
        elif not activating_devices:
            device_id = self.wifi_profile_devices.get(connection_path)
            if device_id is None and len(active_devices) == 1:
                device_id = next(iter(active_devices))
            if active_devices - {device_id}:
                device_id = None
        else:
            device_id = None
        if device_id is None:
            raise DBusError(NM + ".SecretAgent.Error.NoSecrets", "无法确认请求密码的无线网卡，请重新选择网卡连接")
        await self._require_wifi_device(device_id)
        return device_id

    async def _require_wifi_device(self, device_id):
        known = next((entry for entry in self.state["wifi"].get("devices", []) if entry["id"] == device_id), None)
        if known is None or device_id not in (await self.call(NM, NM_ROOT, NM, "GetDevices"))[0]:
            raise RuntimeError("目标无线网卡已移除，请重新选择网卡")
        device = await self.properties(NM, device_id, NM + ".Device")
        if device.get("DeviceType") != 2 or device.get("Interface") != known["interface"]:
            raise RuntimeError("目标无线网卡已改变，请重新选择网卡")
        if not device.get("Managed", True):
            raise RuntimeError("此网卡未由系统管理")
        if not await self.get(NM, NM_ROOT, NM, "WirelessEnabled"):
            raise RuntimeError("请先开启全部 Wi-Fi")
        return device

    async def _require_wifi_access_point(self, device_id, network):
        device = await self._require_wifi_device(device_id)
        wireless = await self.properties(NM, device_id, NM + ".Device.Wireless")
        if network["id"] not in wireless.get("AccessPoints", []):
            raise RuntimeError("此网卡已搜索不到该网络，请重新搜索")
        information = await self.properties(NM, network["id"], NM + ".AccessPoint")
        if list(information.get("Ssid", [])) != network["ssid"] or wifi_security(information)[0] != network["security"]:
            raise RuntimeError("网络已改变，请重新搜索")
        return device

    async def _execute_wifi(self, action, payload):
        if action == "wifi_power":
            await self.set_property(NM, NM_ROOT, NM, "WirelessEnabled", "b", bool(payload["enabled"]))
            if not payload["enabled"]:
                self.cancel_prompts("network")
        elif action in ("wifi_scan", "wifi_disconnect"):
            device_id = payload.get("deviceId")
            await self._require_wifi_device(device_id)
            if action == "wifi_scan":
                await self.call(NM, device_id, NM + ".Device.Wireless", "RequestScan", "a{sv}", [{}])
            else:
                await self.call(NM, device_id, NM + ".Device", "Disconnect")
        elif action == "wifi_connect":
            await self._wifi_connect(payload.get("deviceId"), payload["id"])
        elif action == "wifi_connect_saved":
            device_id = payload.get("deviceId")
            device = await self._require_wifi_device(device_id)
            profiles = await self._saved_wifi()
            usage = await self._wifi_profile_usage()
            profile = next((entry for entry in self._wifi_device_profiles(device_id, device, profiles, usage) if entry["id"] == payload["id"]), None)
            if profile is None or profile.get("unsupported"):
                raise RuntimeError("此网卡无法使用该已保存网络，请重新选择")
            if profile["blocked"]:
                raise RuntimeError(profile["blocked"])
            self.wifi_profile_devices[profile["id"]] = device_id
            await self.call(NM, NM_ROOT, NM, "ActivateConnection", "ooo", [profile["id"], device_id, "/"])
        else:
            raise ValueError("未知 Wi-Fi 操作")
        await self.refresh_wifi()

    async def _wifi_connect(self, device_id, identifier):
        device = next((entry for entry in self.state["wifi"].get("devices", []) if entry["id"] == device_id), {})
        network = next((entry for entry in device.get("networks", []) if entry["id"] == identifier), None)
        if network is None or network.get("unsupported"):
            raise RuntimeError("此网卡已搜索不到该网络，或不支持此认证方式")
        properties = await self._require_wifi_access_point(device_id, network)
        profiles = await self._saved_wifi()
        usage = await self._wifi_profile_usage()
        for profile in self._wifi_device_profiles(device_id, properties, profiles, usage):
            if profile["ssid"] == network["ssid"] and not profile["blocked"] and not profile["unsupported"]:
                if profile["keyManagement"] in (network["keyManagement"] or [""]):
                    self.wifi_profile_devices[profile["id"]] = device_id
                    await self.call(NM, NM_ROOT, NM, "ActivateConnection", "ooo", [profile["id"], device_id, identifier])
                    return
        name = network["name"]
        if any(profile["ssid"] == network["ssid"] for profile in profiles):
            name += " (" + device["interface"] + ")"
        settings = {
            "connection": {"id": Variant("s", name), "uuid": Variant("s", str(uuid.uuid4())),
                           "type": Variant("s", "802-11-wireless"), "autoconnect": Variant("b", True),
                           "permissions": Variant("as", [f"user:{getpass.getuser()}:"])},
            "802-11-wireless": {"ssid": Variant("ay", bytes(network["ssid"])), "mode": Variant("s", "infrastructure")},
            "ipv4": {"method": Variant("s", "auto")}, "ipv6": {"method": Variant("s", "auto")},
        }
        if network["secured"]:
            password = await self.ask("text", "连接 " + network["name"], wifi_label(device) + "\n输入 Wi-Fi 密码；凭据交由系统管理",
                                      secret=True, cancel_error=NETWORK_CANCEL, group="network:" + device_id, deviceId=device_id)
            password = validate_wifi_password(password, network["security"])
            settings["802-11-wireless-security"] = {"key-mgmt": Variant("s", "sae" if network["security"] == "WPA3" else "wpa-psk"), "psk": Variant("s", str(password))}
        await self._require_wifi_access_point(device_id, network)
        result = await self.call(NM, NM_ROOT, NM, "AddAndActivateConnection", "a{sa{sv}}oo", [settings, device_id, identifier])
        self.wifi_profile_devices[result[0]] = device_id

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
                raise DBusError(cancel_error, "用户取消")
            return answer
        except TimeoutError as error:
            raise DBusError(cancel_error, "确认超时") from error
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
