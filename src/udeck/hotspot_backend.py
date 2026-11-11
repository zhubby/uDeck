"""Device-bound NetworkManager AP profiles and guarded asynchronous transitions."""

import asyncio
import getpass
import time
import uuid
from copy import deepcopy

from dbus_next import Variant

from .hotspot import HOTSPOT_BUSY, HOTSPOT_OWNER, default_hotspot_name, validate_hotspot_name
from .i18n import Msg, tr

NM = "org.freedesktop.NetworkManager"
NM_ROOT = "/org/freedesktop/NetworkManager"


class HotspotError(RuntimeError):
    """A local, secret-free explanation safe to expose in operation state."""


def setting(settings, group, key, default=None):
    value = settings.get(group, {}).get(key, default)
    return value.value if isinstance(value, Variant) else value


def permanent_mac(device, wireless):
    value = wireless.get("PermHwAddress") or device.get("PermHwAddress", "")
    try:
        raw = bytes.fromhex(value.replace(":", ""))
        return raw if len(raw) == 6 and any(raw) and not raw[0] & 1 else None
    except (ValueError, AttributeError):
        return None


class HotspotBackend:
    def _init_hotspots(self):
        self.hotspot_profiles = {}
        self.hotspot_operations = {}
        self.hotspot_tasks = {}
        self.hotspot_timeout = 90
        self.hotspot_poll_interval = 0.2

    def _clear_hotspots(self):
        for task in self.hotspot_tasks.values():
            if not task.done():
                task.cancel()

    def _remember_hotspot_profile(self, path, raw, version):
        # GetSettings normally omits secrets; also strip them from unusual services.
        raw = deepcopy(raw)
        raw.get("802-11-wireless-security", {}).pop("psk", None)
        self.hotspot_profiles[path] = {"id": path, "uuid": setting(raw, "connection", "uuid", ""),
            "ssid": bytes(setting(raw, "802-11-wireless", "ssid", b"")).decode("utf-8", errors="replace"),
            "revision": self._wifi_revision(raw, version), "versionId": version, "settings": raw}

    def _owned_hotspot(self, device, wireless):
        mac = permanent_mac(device, wireless)
        if mac is None:
            return None
        candidates = []
        for profile in self.hotspot_profiles.values():
            raw = profile["settings"]
            binding = setting(raw, "802-11-wireless", "mac-address", b"")
            try:
                binding = bytes.fromhex(binding.replace(":", "")) if isinstance(binding, str) else bytes(binding)
            except (TypeError, ValueError):
                continue
            if (setting(raw, "user", "data", {}).get(HOTSPOT_OWNER) == mac.hex() and binding == mac
                    and setting(raw, "connection", "permissions") == [f"user:{getpass.getuser()}:"]):
                candidates.append(profile)
        if len(candidates) > 1:
            raise RuntimeError(tr(Msg.MULTIPLE_HOTSPOT_CONFIGURATIONS_MATCH_THIS_ADAPTER_RESOLVE_THEM_IN_NETWORKMANAGER))
        return candidates[0] if candidates else None

    @staticmethod
    def _require_safe_hotspot_profile(profile):
        raw = profile["settings"]
        expected = (("connection", "autoconnect", False), ("802-11-wireless", "mode", "ap"),
                    ("802-11-wireless-security", "key-mgmt", "wpa-psk"),
                    ("802-11-wireless-security", "proto", ["rsn"]),
                    ("802-11-wireless-security", "pairwise", ["ccmp"]),
                    ("802-11-wireless-security", "group", ["ccmp"]),
                    ("ipv4", "method", "shared"), ("ipv6", "method", "disabled"))
        if any(setting(raw, group, key) != value for group, key, value in expected):
            raise RuntimeError(tr(Msg.THE_HOTSPOT_CONFIGURATION_CHANGED_SAVE_ITS_SETTINGS_BEFORE_STARTING_IT))

    async def _read_hotspot(self, path, device, wireless):
        profile = self._owned_hotspot(device, wireless)
        active_path = device.get("ActiveConnection", "/")
        active_profile = None
        if active_path != "/":
            active = await self.properties(NM, active_path, NM + ".Connection.Active")
            active_profile = self.hotspot_profiles.get(active.get("Connection"))
        is_ap = wireless.get("Mode") == 3
        owned_active = bool(is_ap and profile and active_profile and active_profile["uuid"] == profile["uuid"])
        operation = self.hotspot_operations.get(path, {})
        status = "active" if is_ap and device.get("State") == 100 else "off"
        expected_active = operation.get("failedActivePath") if operation.get("status") == "failed" else operation.get("activePath")
        # Terminal failures belong to the connection observed after recovery.
        # An external replacement invalidates both their message and restore record.
        if operation and operation.get("status") not in HOTSPOT_BUSY and expected_active != active_path:
            self.hotspot_operations.pop(path, None)
            operation = {}
        if operation.get("status") in HOTSPOT_BUSY | {"failed"}:
            status = operation["status"]
        return {"configured": bool(profile), "ssid": profile["ssid"] if profile else default_hotspot_name(device.get("Interface", "")),
                "profileUuid": profile["uuid"] if profile else "", "revision": profile["revision"] if profile else "",
                "activeSsid": active_profile["ssid"] if active_profile else "", "owned": owned_active,
                "activePath": active_path if is_ap else "/", "status": status,
                "operationId": operation.get("id", active_path if owned_active else ""),
                "message": operation.get("message", "") if operation else ""}

    async def _hotspot_target(self, identifier, epoch, *, inactive=False):
        device = await self._require_wifi_device(identifier, inactive=inactive)
        wireless = await self.properties(NM, identifier, NM + ".Device.Wireless")
        self._check_wifi_epoch(epoch)
        if permanent_mac(device, wireless) is None:
            raise RuntimeError(tr(Msg.CANNOT_IDENTIFY_THIS_ADAPTER_S_PERMANENT_HARDWARE_ADDRESS))
        operation = self.hotspot_operations.get(identifier, {})
        if operation.get("status") in HOTSPOT_BUSY and operation.get("hardware") != permanent_mac(device, wireless).hex():
            raise RuntimeError(tr(Msg.THE_HOTSPOT_OPERATION_IS_NO_LONGER_CURRENT))
        return device, wireless

    async def _checked_hotspot(self, identifier, payload, epoch, *, configure=False):
        await self._saved_wifi()
        device, wireless = await self._hotspot_target(identifier, epoch, inactive=configure)
        if not device.get("Managed", True):
            raise RuntimeError(tr(Msg.THIS_ADAPTER_IS_NOT_MANAGED_BY_THE_SYSTEM))
        if wireless.get("WirelessCapabilities", 0) & 0x68 != 0x68:
            raise RuntimeError(tr(Msg.THIS_ADAPTER_DOES_NOT_SUPPORT_WPA2_CCMP_HOTSPOTS))
        profile = self._owned_hotspot(device, wireless)
        if payload.get("revision", "") != (profile["revision"] if profile else ""):
            raise RuntimeError(tr(Msg.THE_HOTSPOT_CONFIGURATION_CHANGED_REOPEN_IT_AND_TRY_AGAIN))
        if self.hotspot_operations.get(identifier, {}).get("status") in HOTSPOT_BUSY:
            raise RuntimeError(tr(Msg.THIS_ADAPTER_IS_CHANGING_HOTSPOT_STATE))
        if self.wifi_operations.get(identifier, {}).get("status") in ("preparing", "connecting"):
            raise RuntimeError(tr(Msg.THIS_ADAPTER_IS_ALREADY_JOINING_A_NETWORK))
        if configure and wireless.get("Mode") == 3:
            raise RuntimeError(tr(Msg.TURN_OFF_THIS_HOTSPOT_BEFORE_EDITING_ITS_CONFIGURATION))
        usage = await self._wifi_profile_usage()
        self._check_wifi_epoch(epoch)
        if profile and (usage is None or usage.get(profile["id"], set()) - {identifier}):
            raise RuntimeError(tr(Msg.CANNOT_CONFIRM_EXCLUSIVE_USE_OF_THIS_HOTSPOT_CONFIGURATION))
        if configure and profile and usage.get(profile["id"]):
            raise RuntimeError(tr(Msg.TURN_OFF_THIS_HOTSPOT_BEFORE_EDITING_ITS_CONFIGURATION))
        return device, wireless, profile

    async def _configure_hotspot(self, identifier, payload, epoch):
        name = validate_hotspot_name(payload["ssid"])
        from .wifi_backend import validate_wifi_password
        password = validate_wifi_password(payload["password"], "WPA2") if "password" in payload else None
        device, wireless, profile = await self._checked_hotspot(identifier, payload, epoch, configure=True)
        if profile is None and password is None:
            raise ValueError(tr(Msg.SET_A_PASSWORD_BEFORE_STARTING_THIS_HOTSPOT))
        mac = permanent_mac(device, wireless)
        raw = deepcopy(profile["settings"]) if profile else {
            "connection": {"id": Variant("s", "uDeck hotspot " + mac.hex()), "uuid": Variant("s", str(uuid.uuid4())),
                "type": Variant("s", "802-11-wireless"), "permissions": Variant("as", [f"user:{getpass.getuser()}:"])},
            "802-11-wireless": {}, "802-11-wireless-security": {},
        }
        raw["connection"]["autoconnect"] = Variant("b", False)
        raw["connection"].pop("interface-name", None)
        raw["802-11-wireless"].update({"ssid": Variant("ay", name.encode()), "mode": Variant("s", "ap"), "mac-address": Variant("ay", mac)})
        raw["802-11-wireless-security"].update({"key-mgmt": Variant("s", "wpa-psk"), "proto": Variant("as", ["rsn"]),
            "pairwise": Variant("as", ["ccmp"]), "group": Variant("as", ["ccmp"]), "psk-flags": Variant("u", 0)})
        if password is not None:
            raw["802-11-wireless-security"]["psk"] = Variant("s", password)
        raw["ipv4"] = {"method": Variant("s", "shared"), "never-default": Variant("b", True)}
        raw["ipv6"] = {"method": Variant("s", "disabled")}
        raw["user"] = {"data": Variant("a{ss}", {HOTSPOT_OWNER: mac.hex()})}
        await self._checked_hotspot(identifier, payload, epoch, configure=True)
        self._check_wifi_epoch(epoch)
        try:
            if profile:
                options = {"version-id": Variant("t", profile["versionId"])} if profile["versionId"] is not None else {}
                await self.call(NM, profile["id"], NM + ".Settings.Connection", "Update2", "a{sa{sv}}ua{sv}", [raw, 1, options])
            else:
                await self.call(NM, NM_ROOT + "/Settings", NM + ".Settings", "AddConnection", "a{sa{sv}}", [raw])
        except Exception:
            # Some D-Bus services include rejected settings in errors. Never forward credentials.
            raise RuntimeError(tr(Msg.COULD_NOT_SAVE_HOTSPOT_CONFIGURATION_CHECK_NETWORKMANAGER_PERMISSIONS)) from None

    def _check_hotspot_operation(self, identifier, operation):
        self._check_wifi_epoch(operation["epoch"])
        if self.hotspot_operations.get(identifier) is not operation:
            raise RuntimeError(tr(Msg.THE_HOTSPOT_OPERATION_IS_NO_LONGER_CURRENT))

    async def _wait_hotspot_state(self, identifier, operation, active_path, mode):
        deadline = time.monotonic() + self.hotspot_timeout
        while True:
            device, wireless = await self._hotspot_target(identifier, operation["epoch"])
            self._check_hotspot_operation(identifier, operation)
            active = device.get("ActiveConnection", "/")
            if active == active_path and device.get("State") == 100 and wireless.get("Mode") == mode:
                return
            if active not in ("/", active_path, operation.get("previousActive")):
                raise HotspotError(tr(Msg.ANOTHER_CONNECTION_TOOK_OVER_THIS_ADAPTER_IT_WAS_LEFT_UNCHANGED))
            if device.get("State") in (0, 10, 20, 120) or time.monotonic() >= deadline:
                raise HotspotError(tr(Msg.HOTSPOT_TRANSITION_FAILED_OR_TIMED_OUT))
            await asyncio.sleep(self.hotspot_poll_interval)

    async def _restore_hotspot_client(self, identifier, operation):
        original = operation.get("restore")
        if not original:
            return
        operation.update(status="restoring", message=tr(Msg.RESTORING_WI_FI))
        await self.refresh_wifi()
        device, _ = await self._hotspot_target(identifier, operation["epoch"])
        self._check_hotspot_operation(identifier, operation)
        if device.get("ActiveConnection", "/") != "/":
            active = await self.properties(NM, device["ActiveConnection"], NM + ".Connection.Active")
            if active.get("Connection") == original["id"]:
                await self._wait_hotspot_state(identifier, operation, device["ActiveConnection"], 2)
                return
            raise HotspotError(tr(Msg.ANOTHER_CONNECTION_TOOK_OVER_THIS_ADAPTER_IT_WAS_LEFT_UNCHANGED))
        profiles = await self._saved_wifi()
        profile = next((item for item in profiles if item["uuid"] == original["uuid"]), None)
        if profile is None:
            raise HotspotError(tr(Msg.THE_PREVIOUS_WI_FI_CONFIGURATION_WAS_REMOVED_RECONNECT_MANUALLY))
        usage = await self._wifi_profile_usage()
        if usage is None:
            raise HotspotError(tr(Msg.CANNOT_CONFIRM_EXCLUSIVE_USE_OF_THE_PREVIOUS_WI_FI_CONFIGURATION_RECONNECT_MANUALLY))
        if usage.get(profile["id"], set()) - {identifier}:
            raise HotspotError(tr(Msg.THE_PREVIOUS_WI_FI_CONFIGURATION_IS_IN_USE_BY_ANOTHER_ADAPTER_RECONNECT_MANUALLY))
        profile = next((item for item in self._wifi_device_profiles(identifier, device, profiles, usage)
                        if item["uuid"] == original["uuid"]), None)
        if profile is None:
            raise HotspotError(tr(Msg.THE_PREVIOUS_WI_FI_CONFIGURATION_CHANGED_RECONNECT_MANUALLY))
        if profile["revision"] != original["revision"] or profile.get("unsupported") or profile.get("blocked"):
            raise HotspotError(tr(Msg.THE_PREVIOUS_WI_FI_CONFIGURATION_CHANGED_RECONNECT_MANUALLY))
        device, _ = await self._hotspot_target(identifier, operation["epoch"])
        self._check_hotspot_operation(identifier, operation)
        if device.get("ActiveConnection", "/") != "/":
            raise HotspotError(tr(Msg.ANOTHER_CONNECTION_TOOK_OVER_THIS_ADAPTER_IT_WAS_LEFT_UNCHANGED))
        result = await self.call(NM, NM_ROOT, NM, "ActivateConnection", "ooo", [profile["id"], identifier, "/"])
        await self._wait_hotspot_state(identifier, operation, result[0], 2)

    async def _deactivate_hotspot(self, identifier, operation):
        device, wireless = await self._hotspot_target(identifier, operation["epoch"])
        self._check_hotspot_operation(identifier, operation)
        target = operation["activePath"]
        if device.get("ActiveConnection", "/") != target:
            if device.get("ActiveConnection", "/") == "/":
                return
            raise HotspotError(tr(Msg.ANOTHER_CONNECTION_TOOK_OVER_THIS_ADAPTER_IT_WAS_LEFT_UNCHANGED))
        active = await self.properties(NM, target, NM + ".Connection.Active")
        if active.get("Connection") != operation["profilePath"] or active.get("Devices") != [identifier]:
            raise HotspotError(tr(Msg.THE_HOTSPOT_CONNECTION_CHANGED_REOPEN_IT_AND_TRY_AGAIN))
        self._check_hotspot_operation(identifier, operation)
        await self.call(NM, NM_ROOT, NM, "DeactivateConnection", "o", [target])
        deadline = time.monotonic() + self.wifi_disconnect_timeout
        while True:
            device, _ = await self._hotspot_target(identifier, operation["epoch"])
            self._check_hotspot_operation(identifier, operation)
            if device.get("ActiveConnection", "/") != target:
                return
            if time.monotonic() >= deadline:
                raise HotspotError(tr(Msg.STOPPING_THE_HOTSPOT_TIMED_OUT))
            await asyncio.sleep(self.hotspot_poll_interval)

    async def _run_hotspot(self, identifier, operation, starting):
        try:
            if starting:
                await self._saved_wifi()
                device, wireless = await self._hotspot_target(identifier, operation["epoch"])
                self._check_hotspot_operation(identifier, operation)
                profile = self._owned_hotspot(device, wireless)
                if profile is None or profile["revision"] != operation["revision"]:
                    raise RuntimeError(tr(Msg.THE_HOTSPOT_CONFIGURATION_CHANGED_REOPEN_IT_AND_TRY_AGAIN))
                self._require_safe_hotspot_profile(profile)
                if wireless.get("WirelessCapabilities", 0) & 0x68 != 0x68:
                    raise RuntimeError(tr(Msg.THIS_ADAPTER_DOES_NOT_SUPPORT_WPA2_CCMP_HOTSPOTS))
                if device.get("ActiveConnection", "/") != operation["previousActive"]:
                    raise RuntimeError(tr(Msg.THE_CONNECTION_CHANGED_REOPEN_THE_HOTSPOT_AND_TRY_AGAIN))
                result = await self.call(NM, NM_ROOT, NM, "ActivateConnection", "ooo", [operation["profilePath"], identifier, "/"])
                self._check_hotspot_operation(identifier, operation)
                operation["activePath"] = result[0]
                await self.refresh_wifi()
                await self._wait_hotspot_state(identifier, operation, result[0], 3)
                operation.update(status="active", message=tr(Msg.HOTSPOT_ON))
            else:
                await self._deactivate_hotspot(identifier, operation)
                await self._restore_hotspot_client(identifier, operation)
                operation.update(status="off", message=tr(Msg.HOTSPOT_OFF))
        except asyncio.CancelledError:
            raise
        except Exception as error:
            if self.hotspot_operations.get(identifier) is operation and self.wifi_epoch == operation["epoch"]:
                message = tr(Msg.HOTSPOT_START_FAILED_INSTRUCTIONS) if starting else tr(Msg.HOTSPOT_STOP_FAILED_INSTRUCTIONS)
                if isinstance(error, HotspotError):
                    message = error.args[0]
                if starting:
                    try:
                        if operation.get("activePath"):
                            await self._deactivate_hotspot(identifier, operation)
                        await self._restore_hotspot_client(identifier, operation)
                    except HotspotError as recovery_error:
                        message = tr(Msg.HOTSPOT_FAILED) + " · " + recovery_error.args[0]
                    except Exception:
                        message = tr(Msg.HOTSPOT_WIFI_RESTORE_FAILED_INSTRUCTIONS)
                try:
                    device, _ = await self._hotspot_target(identifier, operation["epoch"])
                    self._check_hotspot_operation(identifier, operation)
                    failed_active = device.get("ActiveConnection", "/")
                except Exception:
                    failed_active = None
                if self.hotspot_operations.get(identifier) is operation and self.wifi_epoch == operation["epoch"]:
                    # Only a retry against our exact AP may reuse its original client.
                    if failed_active != operation.get("activePath") or failed_active is None:
                        operation.pop("restore", None)
                    operation.update(status="failed", message=message, failedActivePath=failed_active)
        finally:
            if self.wifi_epoch == operation["epoch"]:
                await self.refresh_wifi()

    async def _execute_hotspot(self, action, payload):
        identifier, epoch = payload.get("deviceId"), payload.get("wifiEpoch", self.wifi_epoch)
        self._check_wifi_epoch(epoch)
        if action == "wifi_hotspot_configure":
            await self._configure_hotspot(identifier, payload, epoch)
            return
        if action == "wifi_hotspot_start":
            device, wireless, profile = await self._checked_hotspot(identifier, payload, epoch)
            if profile is None:
                raise RuntimeError(tr(Msg.SET_A_PASSWORD_BEFORE_STARTING_THIS_HOTSPOT))
            self._require_safe_hotspot_profile(profile)
            if wireless.get("Mode") == 3:
                raise RuntimeError(tr(Msg.A_HOTSPOT_IS_ALREADY_USING_THIS_ADAPTER))
            previous = device.get("ActiveConnection", "/")
            if payload.get("expectedActive", "/") != previous:
                raise RuntimeError(tr(Msg.THE_CONNECTION_CHANGED_REOPEN_THE_HOTSPOT_AND_TRY_AGAIN))
            restore = next((p for p in self.state["wifi"]["devices"] if p["id"] == identifier), {}).get("saved", [])
            restore = next((p for p in restore if p.get("active")), None)
            operation = {"id": uuid.uuid4().hex, "epoch": epoch, "status": "starting", "previousActive": previous,
                         "hardware": permanent_mac(device, wireless).hex(),
                         "profilePath": profile["id"], "revision": profile["revision"],
                         "restore": deepcopy(restore), "message": tr(Msg.STARTING_HOTSPOT)}
        elif action == "wifi_hotspot_stop":
            device, wireless = await self._hotspot_target(identifier, epoch)
            await self._saved_wifi()
            current = await self._read_hotspot(identifier, device, wireless)
            self._check_wifi_epoch(epoch)
            if (not current["owned"] or current["status"] in HOTSPOT_BUSY or current["activePath"] != payload.get("activePath")
                    or current["operationId"] != payload.get("operationId")):
                raise RuntimeError(tr(Msg.THE_HOTSPOT_CONNECTION_CHANGED_REOPEN_IT_AND_TRY_AGAIN))
            profile = self._owned_hotspot(device, wireless)
            operation = {**self.hotspot_operations.get(identifier, {}), "id": uuid.uuid4().hex, "epoch": epoch,
                         "hardware": permanent_mac(device, wireless).hex(),
                         "profilePath": profile["id"], "activePath": current["activePath"],
                         "status": "stopping", "message": tr(Msg.STOPPING_HOTSPOT)}
        else:
            raise ValueError(tr(Msg.UNKNOWN_HOTSPOT_OPERATION))
        self._check_wifi_epoch(epoch)
        self.hotspot_operations[identifier] = operation
        self.hotspot_tasks[identifier] = asyncio.create_task(self._run_hotspot(identifier, operation, action == "wifi_hotspot_start"))
