"""NetworkManager Wi-Fi reads and device-bound profile operations."""

import asyncio
import getpass
import hashlib
import json
import time
import uuid
from copy import deepcopy

from dbus_next import DBusError, Variant

from .hotspot_backend import HotspotBackend
from .i18n import Msg, error_text, tr
from .wifi import (
    network_key,
    security_code,
    wifi_failure,
    wifi_identity,
    wifi_label,
    wifi_phase,
    wifi_security,
)

NM = "org.freedesktop.NetworkManager"
NM_ROOT = "/org/freedesktop/NetworkManager"
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
        raise ValueError(tr(Msg.THE_WI_FI_PASSWORD_CANNOT_BE_EMPTY_OR_CONTAIN_NUL_CHARACTERS))
    if security == "WPA3":
        return value
    if not 8 <= len(value.encode()) <= 63 and not (len(value) == 64 and all(character in "0123456789abcdefABCDEF" for character in value)):
        raise ValueError(tr(Msg.WPA2_REQUIRES_8_63_BYTES_OR_A_64_DIGIT_HEXADECIMAL_PSK))
    return value



class WifiBackend(HotspotBackend):
    def _init_wifi(self):
        self._init_hotspots()
        self.wifi_profile_devices = {}
        self.wifi_settings = {}
        self.wifi_operations = {}
        self.wifi_scans = {}
        self.wifi_epoch = uuid.uuid4().hex
        self.wifi_monitor = None
        self.wifi_disconnect_timeout = 10

    def _reset_wifi(self):
        self._clear_hotspots()
        self.cancel_prompts("network")
        if self.wifi_monitor and not self.wifi_monitor.done():
            self.wifi_monitor.cancel()
        self._init_wifi()

    def _monitor_wifi(self):
        if self.wifi_monitor and not self.wifi_monitor.done():
            return
        async def monitor():
            while not self.closing and (any(item["status"] == "scanning" for item in self.wifi_scans.values())
                                       or any(item["status"] in ("preparing", "connecting") for item in self.wifi_operations.values())):
                await asyncio.sleep(1)
                await self.refresh_wifi()
        self.wifi_monitor = asyncio.create_task(monitor())

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
                    agent_error = error_text(error)
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
            for removed_id in previous.keys() - present:
                task = self.hotspot_tasks.pop(removed_id, None)
                if task:
                    task.cancel()
                self.hotspot_operations.pop(removed_id, None)
                self.wifi_operations.pop(removed_id, None)
                self.wifi_scans.pop(removed_id, None)
            if not enabled:
                self.cancel_prompts("network")
                for entry in devices:
                    operation = self.wifi_operations.get(entry["id"], {})
                    if operation.get("status") in ("preparing", "connecting"):
                        operation.update(status="cancelled", message=tr(Msg.WI_FI_WAS_TURNED_OFF))
                        entry["operation"] = self._public_wifi_operation(operation)
                    scan = self.wifi_scans.get(entry["id"], {})
                    if scan.get("status") == "scanning":
                        scan["status"] = "cancelled"
                        entry["scan"] = {"status": "cancelled"}
            self.publish("wifi", {"epoch": self.wifi_epoch, "available": bool(devices), "enabled": enabled, "devices": devices,
                                  "error": "" if devices else tr(Msg.NO_WI_FI_ADAPTERS_FOUND), "agentError": agent_error})
        except Exception as error:
            self.cancel_prompts("network")
            for operation in self.wifi_operations.values():
                if operation.get("status") in ("preparing", "connecting"):
                    operation.update(status="failed", message=error_text(error))
            for scan in self.wifi_scans.values():
                if scan.get("status") == "scanning":
                    scan["status"] = "failed"
            self.publish("wifi", {"epoch": self.wifi_epoch, "available": False, "enabled": False, "devices": [], "error": error_text(error)})

    async def _read_wifi_device(self, path, saved, usage, previous):
        result = {"id": path, **wifi_identity(previous.get("interface", "")), "available": False,
                  "managed": True, "deviceState": 0, "connected": "", "connecting": "",
                  "strength": None, "networks": [], "saved": [], "error": ""}
        try:
            device = await self.properties(NM, path, NM + ".Device")
            result.update(wifi_identity(device.get("Interface", "")))
            device_state = device.get("State", 0)
            result.update({"managed": device.get("Managed", True), "deviceState": device_state,
                           "activeConnection": device.get("ActiveConnection", "/"),
                           "stateReason": device.get("StateReason", [device_state, 0])[1]})
            profiles = self._wifi_device_profiles(path, device, saved, usage)
            result["activeProfileUuid"] = next((profile["uuid"] for profile in profiles if profile.get("active")), "")
            result["addresses"] = await self._wifi_addresses(device)
            result["saved"] = profiles
            wireless = await self.properties(NM, path, NM + ".Device.Wireless")
            result.update(mode="ap" if wireless.get("Mode") == 3 else "infrastructure",
                          apSupported=wireless.get("WirelessCapabilities", 0) & 0x68 == 0x68,
                          hotspot=await self._read_hotspot(path, device, wireless))
            networks = {}
            active_ap = wireless.get("ActiveAccessPoint", "/")
            access_points = list(wireless.get("AccessPoints", []))
            if active_ap != "/" and active_ap not in access_points:
                access_points.append(active_ap)
            for access_point in access_points:
                try:
                    information = await self.properties(NM, access_point, NM + ".AccessPoint")
                except Exception:
                    continue
                if access_point == active_ap and device_state == 100:
                    result["strength"] = information.get("Strength")
                ssid_bytes = bytes(information.get("Ssid", []))
                if not ssid_bytes:
                    continue
                name = ssid_bytes.decode("utf-8", errors="replace")
                security, keys = wifi_security(information)
                entry = {"id": access_point, "key": network_key(ssid_bytes, security_code(information)),
                         "securityId": security_code(information), "name": name, "ssid": list(ssid_bytes),
                         "strength": information.get("Strength", 0), "security": security,
                         "saved": any(profile["ssid"] == list(ssid_bytes) and profile["keyManagement"] in (keys or [""]) for profile in profiles),
                         "keyManagement": keys,
                         "secured": security != tr(Msg.OPEN_NETWORK), "unsupported": security in (tr(Msg.ENTERPRISE_NETWORK), tr(Msg.UNSUPPORTED_ENCRYPTION)),
                         "connected": access_point == wireless.get("ActiveAccessPoint") and device_state == 100,
                         "connecting": access_point == wireless.get("ActiveAccessPoint") and 40 <= device_state < 100}
                deduplication_key = entry["key"]
                existing = networks.get(deduplication_key)
                if not existing or (entry["connected"], entry["connecting"], entry["strength"]) > (existing["connected"], existing["connecting"], existing["strength"]):
                    networks[deduplication_key] = entry
            entries = sorted(networks.values(), key=lambda entry: (not entry["connected"], -entry["strength"]))
            reason = device.get("StateReason", [device_state, 0])[1]
            failure = wifi_failure(reason) if device_state == 120 else ""
            result.update({"available": True, "networks": entries,
                           "connected": next((entry["name"] for entry in entries if entry["connected"]), ""),
                           "connecting": next((entry["name"] for entry in entries if entry["connecting"]), ""), "error": failure})
            if result["mode"] == "ap":
                result.update(connected="", connecting="", strength=None, networks=[])
            if result["mode"] != "ap" and device_state == 100 and not result["connected"] and usage is not None:
                profile = next((profile for profile in saved if path in usage.get(profile["id"], set())), None)
                if profile:
                    result["connected"] = bytes(profile["ssid"]).decode("utf-8", errors="replace")
            result.update(self._wifi_progress(path, result, wireless, previous))
        except Exception as error:
            result["error"] = tr(Msg.COULD_NOT_READ_ADAPTER_PREFIX) + error_text(error)
            result.update(self._wifi_progress(path, result, {}, previous))
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
        result = []
        for profile in profiles:
            if not self._wifi_compatible(device, profile):
                continue
            others = usage.get(profile["id"], set()) - {device_id} if usage is not None else set()
            mutation_blocked = tr(Msg.ANOTHER_ADAPTER_IS_USING_THIS_SAVED_CONFIGURATION) if others else (
                tr(Msg.CANNOT_DETERMINE_WHETHER_THIS_PROFILE_IS_IN_USE) if usage is None else "")
            blocked = mutation_blocked if profile["multiConnect"] not in (2, 3) else ""
            settings = unwrap(self.wifi_settings.get(profile["id"], {}))
            connection = settings.get("connection", {})
            if (settings.get("match") or connection.get("controller") or connection.get("master")) and profile["id"] not in device.get("AvailableConnections", []):
                blocked = mutation_blocked = tr(Msg.THE_SYSTEM_CANNOT_CONFIRM_THIS_CONFIGURATION_IS_COMPATIBLE_WITH_THIS_ADAPTER)
            result.append({**profile, "blocked": blocked, "mutationBlocked": mutation_blocked,
                           "active": usage is not None and device_id in usage.get(profile["id"], set())})
        return result

    def _wifi_compatible(self, device, profile):
        settings = unwrap(self.wifi_settings.get(profile["id"], {}))
        connection, wireless = settings.get("connection", {}), settings.get("802-11-wireless", {})
        if connection.get("interface-name") and connection["interface-name"] != device.get("Interface"):
            return False
        mac = wireless.get("mac-address")
        if mac:
            expected = bytes(mac).hex() if not isinstance(mac, str) else mac.replace(":", "").lower()
            actual = device.get("PermHwAddress") or device.get("HwAddress", "")
            if expected != actual.replace(":", "").lower():
                return False
        return True

    @staticmethod
    def _wifi_revision(settings, version=None):
        configuration = unwrap(settings)
        # GetSettings includes NM's runtime history even when VersionId is unchanged.
        # It must not invalidate restoration or edits to the saved configuration.
        configuration.get("connection", {}).pop("timestamp", None)
        configuration.get("802-11-wireless", {}).pop("seen-bssids", None)
        return hashlib.sha256(json.dumps([configuration, version], sort_keys=True,
                                         default=lambda value: list(value)).encode()).hexdigest()

    async def _wifi_profile_version(self, path):
        try:
            return (await self.properties(NM, path, NM + ".Settings.Connection")).get("VersionId")
        except DBusError as error:
            if error.type not in ("org.freedesktop.DBus.Error.UnknownProperty", "org.freedesktop.DBus.Error.UnknownInterface"):
                raise
        except RuntimeError:
            # Older NetworkManager/test services may have no property interface.
            return None

    async def _saved_wifi(self):
        profiles, snapshots = [], {}
        hotspots = {}
        connections = (await self.call(NM, NM_ROOT + "/Settings", NM + ".Settings", "ListConnections"))[0]
        for path in connections:
            try:
                version = await self._wifi_profile_version(path)
                raw = (await self.call(NM, path, NM + ".Settings.Connection", "GetSettings"))[0]
                if version != await self._wifi_profile_version(path):
                    continue  # A refresh will read a consistent snapshot after Updated.
                settings = unwrap(raw)
                wireless = settings.get("802-11-wireless")
                if wireless and wireless.get("mode") == "ap":
                    self._remember_hotspot_profile(path, raw, version)
                    hotspots[path] = self.hotspot_profiles[path]
                if not wireless or wireless.get("mode", "infrastructure") != "infrastructure":
                    continue
                connection = settings.get("connection", {})
                key = settings.get("802-11-wireless-security", {}).get("key-mgmt", "")
                ssid = list(wireless.get("ssid", []))
                snapshots[path] = deepcopy(raw)
                profiles.append({"id": path, "uuid": connection.get("uuid", ""),
                                 "revision": self._wifi_revision(raw, version), "versionId": version,
                                 "autoconnect": connection.get("autoconnect", True),
                                 "name": connection.get("id", bytes(ssid).decode("utf-8", errors="replace")),
                                 "ssid": ssid, "keyManagement": key,
                                 "readOnly": connection.get("read-only", False),
                                 "multiConnect": connection.get("multi-connect", 0),
                                 "unsupported": key not in ("", "wpa-psk", "sae")})
            except Exception:
                continue
        self.wifi_settings = snapshots
        self.hotspot_profiles = hotspots
        return profiles

    async def _wifi_addresses(self, device):
        result = {"ip": [], "gateway": [], "dns": []}
        for family in (4, 6):
            path = device.get(f"Ip{family}Config", "/")
            if path == "/":
                continue
            try:
                value = await self.properties(NM, path, NM + f".IP{family}Config")
                result["ip"] += [f"{entry['address']}/{entry['prefix']}" for entry in value.get("AddressData", [])]
                if value.get("Gateway"):
                    result["gateway"].append(value["Gateway"])
                result["dns"] += [entry["address"] for entry in value.get("NameserverData", []) if entry.get("address")]
            except Exception:
                continue
        return result

    def _wifi_progress(self, device_id, device, wireless, previous):
        scan = self.wifi_scans.get(device_id, {})
        if scan.get("status") == "scanning":
            if wireless.get("LastScan", -1) > scan.get("baseline", -1):
                scan["status"] = "complete"
            else:
                keys = {network["key"] for network in device["networks"]}
                device["networks"] += [{**deepcopy(network), "connected": False, "connecting": False}
                                       for network in previous.get("networks", []) if network["key"] not in keys]
                if time.monotonic() - scan["started"] >= 20:
                    scan["status"] = "timeout"
        elif scan.get("status") == "timeout" and not device["networks"]:
            device["networks"] = deepcopy(previous.get("networks", []))
        operation = self.wifi_operations.get(device_id, {})
        state = device.get("deviceState", 0)
        if operation.get("status") == "connecting":
            active = device.get("activeConnection", "/")
            if state == 100 and active == operation.get("activePath"):
                operation.update(status="connected", message=tr(Msg.JOINED_NETWORK))
            elif state == 120:
                operation.update(status="failed", message=wifi_failure(device.get("stateReason", 0)))
            elif state in (0, 10, 20):
                operation.update(status="failed", message=tr(Msg.THIS_ADAPTER_CANNOT_JOIN_THIS_NETWORK_RIGHT_NOW))
            elif active not in ("/", operation.get("activePath")) and time.monotonic() - operation["started"] > 3:
                operation.update(status="superseded", message=tr(Msg.THE_SYSTEM_SELECTED_ANOTHER_CONNECTION))
            elif state == 30 and (operation.get("sawActivating") or time.monotonic() - operation["started"] > 5):
                operation.update(status="failed", message=wifi_failure(device.get("stateReason", 0)))
            else:
                operation.update(message=wifi_phase(state), timedOut=time.monotonic() - operation["started"] >= 90)
                if 40 <= state < 100:
                    operation["sawActivating"] = True
        return {"scan": {key: value for key, value in scan.items() if key not in ("started", "baseline")},
                "operation": self._public_wifi_operation(operation)}

    @staticmethod
    def _public_wifi_operation(operation):
        return {key: value for key, value in operation.items() if key in (
            "id", "status", "message", "networkKey", "profileUuid", "name", "timedOut")}

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
            raise DBusError(NM + ".SecretAgent.Error.NoSecrets", tr(Msg.COULD_NOT_IDENTIFY_THE_ADAPTER_REQUESTING_A_PASSWORD_SELECT_AN_ADAPTER_AND_RECONNECT)) from error
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
            raise DBusError(NM + ".SecretAgent.Error.NoSecrets", tr(Msg.COULD_NOT_IDENTIFY_THE_ADAPTER_REQUESTING_A_PASSWORD_SELECT_AN_ADAPTER_AND_RECONNECT))
        await self._require_wifi_device(device_id)
        return device_id

    async def _require_wifi_device(self, device_id, inactive=False):
        known = next((entry for entry in self.state["wifi"].get("devices", []) if entry["id"] == device_id), None)
        if known is None or device_id not in (await self.call(NM, NM_ROOT, NM, "GetDevices"))[0]:
            raise RuntimeError(tr(Msg.TARGET_ADAPTER_REMOVED_SELECT_ADAPTER))
        device = await self.properties(NM, device_id, NM + ".Device")
        if device.get("DeviceType") != 2 or device.get("Interface") != known["interface"]:
            raise RuntimeError(tr(Msg.THE_TARGET_WI_FI_ADAPTER_CHANGED_SELECT_AN_ADAPTER_AGAIN))
        if not inactive and not device.get("Managed", True):
            raise RuntimeError(tr(Msg.THIS_ADAPTER_IS_UNMANAGED_BY_THE_SYSTEM))
        if not inactive and not await self.get(NM, NM_ROOT, NM, "WirelessEnabled"):
            raise RuntimeError(tr(Msg.TURN_ON_ALL_WI_FI_FIRST))
        return device

    async def _require_wifi_access_point(self, device_id, network):
        device = await self._require_wifi_device(device_id)
        wireless = await self.properties(NM, device_id, NM + ".Device.Wireless")
        paths = wireless.get("AccessPoints", [])
        candidates = [network["id"]] if network["id"] in paths else paths
        expected_security = network.get("securityId") or ("open" if not network.get("secured") else "wpa3" if network["security"] == "WPA3" else "wpa2")
        for path in candidates:
            try:
                information = await self.properties(NM, path, NM + ".AccessPoint")
            except Exception:
                continue
            if (list(information.get("Ssid", [])) == network["ssid"]
                    and security_code(information) == expected_security):
                network["id"] = path
                break
        else:
            raise RuntimeError(tr(Msg.THIS_ADAPTER_CAN_NO_LONGER_SEE_THE_NETWORK_SCAN_AGAIN))
        return device

    async def _checked_wifi_profile(self, payload, mutate=False):
        device_id = payload.get("deviceId")
        device = await self._require_wifi_device(device_id, inactive=mutate)
        profiles = await self._saved_wifi()
        usage = await self._wifi_profile_usage()
        profiles = self._wifi_device_profiles(device_id, device, profiles, usage)
        target = next((entry for entry in profiles if (entry["uuid"] == payload.get("profileUuid")
                       if payload.get("profileUuid") else entry["id"] == payload.get("id"))), None)
        if target is None:
            raise RuntimeError(tr(Msg.THIS_SAVED_CONFIGURATION_WAS_REMOVED_OR_IS_INCOMPATIBLE_WITH_THE_ADAPTER))
        if mutate:
            if not target["uuid"] or not payload.get("revision") or payload["revision"] != target["revision"]:
                raise RuntimeError(tr(Msg.THE_SAVED_CONFIGURATION_CHANGED_REOPEN_IT_AND_TRY_AGAIN))
            if target["readOnly"]:
                raise RuntimeError(tr(Msg.THIS_SAVED_CONFIGURATION_IS_READ_ONLY))
        reason = target["mutationBlocked"] if mutate else target["blocked"]
        if reason:
            raise RuntimeError(reason)
        return {**target, "_settings": deepcopy(self.wifi_settings[target["id"]])}

    def _begin_wifi_join(self, device_id, **target):
        current = self.wifi_operations.get(device_id, {})
        if current.get("status") in ("preparing", "connecting"):
            raise RuntimeError(tr(Msg.THIS_ADAPTER_IS_ALREADY_JOINING_A_NETWORK))
        operation = {"id": uuid.uuid4().hex, "started": time.monotonic(), "status": "preparing",
                     "message": tr(Msg.PREPARING_TO_JOIN), **target}
        self.wifi_operations[device_id] = operation
        self._monitor_wifi()
        return operation

    def _check_wifi_join(self, device_id, operation):
        if self.wifi_operations.get(device_id) is not operation or operation["status"] != "preparing":
            raise DBusError(NETWORK_CANCEL, tr(Msg.JOINING_CANCELLED))

    def _check_wifi_epoch(self, epoch):
        if epoch != self.wifi_epoch:
            raise RuntimeError(tr(Msg.THE_WI_FI_SERVICE_RESTARTED_REOPEN_THE_ADAPTER_AND_TRY_AGAIN))

    async def _finish_wifi_activation(self, device_id, operation, active_path, profile_uuid):
        if self.wifi_operations.get(device_id) is not operation:
            return  # The adapter or NetworkManager instance was replaced.
        operation.update(activePath=active_path, profileUuid=profile_uuid)
        if operation["status"] == "cancelled":
            device = await self._require_wifi_device(device_id, inactive=True)
            if self.wifi_operations.get(device_id) is not operation:
                return
            if device.get("ActiveConnection") == active_path:
                try:
                    await self.call(NM, NM_ROOT, NM, "DeactivateConnection", "o", [active_path])
                except Exception:
                    operation["status"] = "connecting"
                    self._monitor_wifi()
                    raise
            return
        operation["status"] = "connecting"
        self._monitor_wifi()

    async def _activate_wifi_profile(self, device_id, profile, access_point="/"):
        operation = self.wifi_operations[device_id]
        current = await self._checked_wifi_profile({"deviceId": device_id, "profileUuid": profile["uuid"]})
        if current["ssid"] != profile["ssid"] or current["keyManagement"] != profile["keyManagement"]:
            raise RuntimeError(tr(Msg.THE_SAVED_CONFIGURATION_CHANGED_REOPEN_IT_AND_TRY_AGAIN))
        self._check_wifi_join(device_id, operation)
        self.wifi_profile_devices[profile["id"]] = device_id
        operation["started"] = time.monotonic()
        result = await self.call(NM, NM_ROOT, NM, "ActivateConnection", "ooo", [profile["id"], device_id, access_point])
        await self._finish_wifi_activation(device_id, operation, result[0], profile["uuid"])

    async def _disconnect_wifi_profile(self, device_id, profile):
        epoch = self.wifi_epoch
        device = await self._require_wifi_device(device_id, inactive=True)
        active_path = device.get("ActiveConnection", "/")
        if active_path == "/":
            raise RuntimeError(tr(Msg.THE_CONNECTION_CHANGED_NO_CONNECTION_WAS_CANCELLED))
        active = await self.properties(NM, active_path, NM + ".Connection.Active")
        if active.get("Connection") != profile["id"] or set(active.get("Devices", [])) != {device_id}:
            raise RuntimeError(tr(Msg.THE_CONNECTION_CHANGED_NO_CONNECTION_WAS_CANCELLED))
        self._check_wifi_epoch(epoch)
        await self.call(NM, NM_ROOT, NM, "DeactivateConnection", "o", [active_path])
        deadline = time.monotonic() + self.wifi_disconnect_timeout
        while True:
            await self._require_wifi_device(device_id, inactive=True)
            paths = await self.get(NM, NM_ROOT, NM, "ActiveConnections")
            if active_path not in paths:
                return
            try:
                active = await self.properties(NM, active_path, NM + ".Connection.Active")
            except Exception:
                if active_path not in await self.get(NM, NM_ROOT, NM, "ActiveConnections"):
                    return
                raise
            if active.get("State") == 4:
                return
            if time.monotonic() >= deadline:
                raise RuntimeError(tr(Msg.DISCONNECTING_TIMED_OUT_THE_SAVED_CONFIGURATION_WAS_NOT_REMOVED))
            await asyncio.sleep(0.1)

    async def _execute_wifi(self, action, payload):
        device_id = payload.get("deviceId")
        epoch = payload.get("wifiEpoch", self.wifi_epoch)
        previous_operation = self.wifi_operations.get(device_id)
        try:
            self._check_wifi_epoch(epoch)
            if action.startswith("wifi_hotspot_"):
                await self._execute_hotspot(action, payload)
            elif action == "wifi_power":
                await self.set_property(NM, NM_ROOT, NM, "WirelessEnabled", "b", bool(payload["enabled"]))
                if not payload["enabled"]:
                    self._clear_hotspots()
                    self.hotspot_operations.clear()
                    self.cancel_prompts("network")
                    for operation in self.wifi_operations.values():
                        if operation["status"] in ("preparing", "connecting"):
                            operation.update(status="cancelled", message=tr(Msg.WI_FI_WAS_TURNED_OFF))
            elif action == "wifi_scan":
                await self._require_wifi_device(device_id)
                wireless = await self.properties(NM, device_id, NM + ".Device.Wireless")
                if wireless.get("Mode") == 3 or self.hotspot_operations.get(device_id, {}).get("status") in ("starting", "stopping", "restoring"):
                    raise RuntimeError(tr(Msg.TURN_OFF_THE_HOTSPOT_BEFORE_USING_WI_FI_ON_THIS_ADAPTER))
                self._check_wifi_epoch(epoch)
                if self.wifi_scans.get(device_id, {}).get("status") == "scanning":
                    raise RuntimeError(tr(Msg.THIS_ADAPTER_IS_ALREADY_SCANNING))
                scan = {"status": "scanning", "baseline": wireless.get("LastScan", -1), "started": time.monotonic()}
                self.wifi_scans[device_id] = scan
                try:
                    await self.call(NM, device_id, NM + ".Device.Wireless", "RequestScan", "a{sv}", [{}])
                except Exception:
                    scan["status"] = "failed"
                    raise
                self._monitor_wifi()
            elif action == "wifi_disconnect":
                await self._require_wifi_device(device_id)
                wireless = await self.properties(NM, device_id, NM + ".Device.Wireless")
                if wireless.get("Mode") == 3 or self.hotspot_operations.get(device_id, {}).get("status") in ("starting", "stopping", "restoring"):
                    raise RuntimeError(tr(Msg.TURN_OFF_THE_HOTSPOT_BEFORE_USING_WI_FI_ON_THIS_ADAPTER))
                self._check_wifi_epoch(epoch)
                await self.call(NM, device_id, NM + ".Device", "Disconnect")
                self.cancel_prompts("network", device_id=device_id)
                if device_id in self.wifi_operations:
                    self.wifi_operations[device_id].update(status="cancelled", message=tr(Msg.DISCONNECTED))
            elif action == "wifi_cancel_connect":
                await self._require_wifi_device(device_id)
                operation = self.wifi_operations.get(device_id, {})
                if operation.get("id") != payload.get("operationId") or operation.get("status") not in ("preparing", "connecting"):
                    raise RuntimeError(tr(Msg.THIS_JOIN_REQUEST_IS_NO_LONGER_ACTIVE))
                active_path = operation.get("activePath")
                if active_path:
                    device = await self.properties(NM, device_id, NM + ".Device")
                    if device.get("ActiveConnection") != active_path:
                        raise RuntimeError(tr(Msg.THE_CONNECTION_CHANGED_NO_CONNECTION_WAS_CANCELLED))
                    self._check_wifi_epoch(epoch)
                    await self.call(NM, NM_ROOT, NM, "DeactivateConnection", "o", [active_path])
                operation.update(status="cancelled", message=tr(Msg.JOINING_CANCELLED))
                self.cancel_prompts("network", device_id=device_id)
            elif action in ("wifi_connect", "wifi_connect_saved", "wifi_reconnect"):
                await self.refresh_wifi()
                self._check_wifi_epoch(epoch)
                selected = next((d for d in self.state["wifi"]["devices"] if d["id"] == device_id), {})
                if selected.get("mode") == "ap" or selected.get("hotspot", {}).get("status") in ("starting", "stopping", "restoring"):
                    raise RuntimeError(tr(Msg.TURN_OFF_THE_HOTSPOT_BEFORE_USING_WI_FI_ON_THIS_ADAPTER))
                if action == "wifi_connect":
                    await self._wifi_connect(device_id, payload.get("networkKey") or payload.get("id"))
                else:
                    profile = await self._checked_wifi_profile(payload)
                    if profile["unsupported"]:
                        raise RuntimeError(tr(Msg.THIS_SAVED_NETWORK_CANNOT_BE_USED_BY_THIS_ADAPTER_SELECT_ANOTHER))
                    self._check_wifi_epoch(epoch)
                    self._begin_wifi_join(device_id, profileUuid=profile["uuid"])
                    await self.refresh_wifi()
                    if action == "wifi_reconnect" and profile["active"]:
                        await self._disconnect_wifi_profile(device_id, profile)
                        profile = await self._checked_wifi_profile(payload)
                    await self._activate_wifi_profile(device_id, profile)
            elif action in ("wifi_forget", "wifi_set_autoconnect", "wifi_update_password"):
                profile = await self._checked_wifi_profile(payload, mutate=True)
                self._check_wifi_epoch(epoch)
                if action == "wifi_forget":
                    disconnected = False
                    if profile["active"]:
                        await self._disconnect_wifi_profile(device_id, profile)
                        disconnected = True
                    try:
                        profile = await self._checked_wifi_profile(payload, mutate=True)
                        if profile["active"]:
                            raise RuntimeError(tr(Msg.THE_CONNECTION_CHANGED_REOPEN_THIS_NETWORK_AND_TRY_AGAIN))
                        self._check_wifi_epoch(epoch)
                        await self.call(NM, profile["id"], NM + ".Settings.Connection", "Delete")
                    except Exception as error:
                        if disconnected:
                            raise RuntimeError(tr(Msg.DISCONNECTED_BUT_FORGETTING_THE_NETWORK_FAILED_ERROR, error=error_text(error))) from error
                        raise
                else:
                    settings = deepcopy(profile["_settings"])
                    if action == "wifi_set_autoconnect":
                        settings["connection"]["autoconnect"] = Variant("b", bool(payload["enabled"]))
                    else:
                        if profile["keyManagement"] not in ("wpa-psk", "sae"):
                            raise RuntimeError(tr(Msg.ONLY_PERSONAL_WI_FI_NETWORKS_ARE_SUPPORTED))
                        password = validate_wifi_password(payload["password"], "WPA3" if profile["keyManagement"] == "sae" else "WPA2")
                        security = settings["802-11-wireless-security"]
                        security["psk"] = Variant("s", password)
                        security["psk-flags"] = Variant("u", 0)
                    await self._checked_wifi_profile(payload, mutate=True)
                    self._check_wifi_epoch(epoch)
                    arguments = {"version-id": Variant("t", profile["versionId"])} if profile["versionId"] is not None else {}
                    await self.call(NM, profile["id"], NM + ".Settings.Connection", "Update2", "a{sa{sv}}ua{sv}", [settings, 1, arguments])
            else:
                raise ValueError(tr(Msg.UNKNOWN_WI_FI_ACTION))
        except Exception as error:
            if action in ("wifi_connect", "wifi_connect_saved", "wifi_reconnect"):
                operation = self.wifi_operations.get(device_id, {})
                if operation is not previous_operation and operation.get("status") == "preparing":
                    cancelled = isinstance(error, DBusError) and error.type == NETWORK_CANCEL
                    operation.update(status="cancelled" if cancelled else "failed", message=tr(Msg.JOINING_CANCELLED) if cancelled else error_text(error))
            raise
        finally:
            await self.refresh_wifi()

    async def _wifi_connect(self, device_id, identifier):
        device = next((entry for entry in self.state["wifi"].get("devices", []) if entry["id"] == device_id), {})
        network = next((entry for entry in device.get("networks", []) if entry.get("key") == identifier or entry["id"] == identifier), None)
        if network is None or network.get("unsupported"):
            raise RuntimeError(tr(Msg.THE_NETWORK_IS_NO_LONGER_VISIBLE_ON_THIS_ADAPTER_OR_ITS_AUTHENTICATION_IS_UNSUPPORTED))
        network = deepcopy(network)
        await self._require_wifi_access_point(device_id, network)
        operation = self._begin_wifi_join(device_id, networkKey=network.get("key", ""), name=network["name"])
        await self.refresh_wifi()
        properties = await self._require_wifi_device(device_id)
        profiles = await self._saved_wifi()
        usage = await self._wifi_profile_usage()
        for profile in self._wifi_device_profiles(device_id, properties, profiles, usage):
            if profile["ssid"] == network["ssid"] and not profile["blocked"] and not profile["unsupported"]:
                if profile["keyManagement"] in (network["keyManagement"] or [""]):
                    await self._activate_wifi_profile(device_id, profile, network["id"])
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
            password = await self.ask("text", tr(Msg.CONNECT_PREFIX) + network["name"], wifi_label(device) + tr(Msg.ENTER_THE_WI_FI_PASSWORD_CREDENTIALS_ARE_MANAGED_BY_THE_SYSTEM_NOTICE),
                                      secret=True, wifiSecurity=network["security"], cancel_error=NETWORK_CANCEL,
                                      group="network:" + device_id, deviceId=device_id)
            password = validate_wifi_password(password, network["security"])
            settings["802-11-wireless-security"] = {"key-mgmt": Variant("s", "sae" if network["security"] == "WPA3" else "wpa-psk"), "psk": Variant("s", str(password))}
        await self._require_wifi_access_point(device_id, network)
        self._check_wifi_join(device_id, operation)
        operation["started"] = time.monotonic()
        result = await self.call(NM, NM_ROOT, NM, "AddAndActivateConnection", "a{sa{sv}}oo", [settings, device_id, network["id"]])
        if self.wifi_operations.get(device_id) is operation:
            self.wifi_profile_devices[result[0]] = device_id
        await self._finish_wifi_activation(device_id, operation, result[1], settings["connection"]["uuid"].value)
