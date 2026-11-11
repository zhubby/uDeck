"""Theme icon names for system menu actions, independent of translated labels."""

SETTING_ICONS = {
    "volume": "audio-volume-high", "volume-level": "audio-volume-high",
    "brightness": "display-brightness", "output": "audio-card",
    "microphone": "audio-input-microphone", "microphone-level": "audio-input-microphone",
    "wifi": "network-wireless", "hotspot": "network-wireless",
    "bluetooth": "bluetooth", "audio-modes": "audio-card", "battery": "battery",
    "input": "udeck-setting:controller", "key-test": "udeck-setting:keyboard-fill",
    "shortcuts": "udeck-setting:command",
    "language": "preferences-desktop-locale", "theme": "preferences-desktop-theme",
    "ui-sounds": "audio-volume-high", "timezone": "preferences-system-time",
    "lock": "system-lock-screen", "blank": "video-display",
    "logout": "system-log-out", "reboot": "system-reboot", "poweroff": "system-shutdown",
}

ACTION_ICONS = {
    "language": "preferences-desktop-locale", "theme": "preferences-desktop-theme",
    "timezone-region": "preferences-system-time", "timezone-set": "preferences-system-time",
    "power-menu": "system-shutdown", "switcher": "preferences-system-windows",
    "audio-card": "audio-card", "audio-profile": "audio-card", "device": "bluetooth",
    "device-pair": "list-add", "device-remove": "edit-delete",
    "wifi-power": "network-wireless", "wifi-device": "network-wireless",
    "wifi-connect": "network-wireless", "wifi-join": "network-connect",
    "wifi-disconnect": "network-disconnect", "wifi-saved": "document-open-recent",
    "wifi-saved-connect": "network-wireless", "wifi-profile": "network-wireless",
    "wifi-details": "dialog-information", "wifi-autoconnect": "network-connect",
    "wifi-password": "dialog-password", "wifi-forget": "edit-delete",
    "hotspot-device": "network-wireless", "hotspot-start": "network-connect",
    "hotspot-stop": "network-disconnect", "hotspot-name": "document-edit",
    "hotspot-password": "dialog-password", "hotspot-band": "network-wireless",
}

SYSTEM_ICONS = {
    "refresh": "view-refresh", "mute": "audio-volume-muted",
    "audio_input": "audio-input-microphone", "audio_input_mute": "microphone-sensitivity-muted",
    "audio_output": "audio-card", "bluetooth_power": "bluetooth",
    "bluetooth_scan": "edit-find", "bluetooth_stop": "process-stop",
    "bluetooth_connect": "network-connect", "bluetooth_disconnect": "network-disconnect",
    "wifi_scan": "view-refresh", "wifi_cancel_connect": "process-stop",
}


def system_menu_icons(options, source=""):
    settings_menu = source in {
        "quick-settings", "language", "theme", "timezone-areas", "timezone-cities",
        "wifi", "wifi-device", "wifi-saved", "wifi-network", "wifi-profiles", "wifi-details",
        "hotspot", "hotspot-device", "bluetooth", "audio-input", "audio-output", "audio-cards", "audio-profiles",
    } or any(option.get("action") in ACTION_ICONS or option.get("action") == "setting"
             or option.get("action") == "system" and option.get("systemAction") in SYSTEM_ICONS
             for option in options)
    if not settings_menu:
        return options
    rows = []
    for option in options:
        row = dict(option)
        action = row.get("action")
        if not row.get("icon"):
            if action == "setting":
                icon = SETTING_ICONS.get(row.get("idSetting", row.get("id")), "preferences-system")
            elif action == "system":
                icon = SYSTEM_ICONS.get(row.get("systemAction"), "preferences-system")
            elif action == "audio-profile" and row.get("profile", {}).get("microphone"):
                icon = "audio-input-microphone"
            else:
                icon = ACTION_ICONS.get(action, "dialog-warning" if row.get("disabled") else "dialog-information")
            row["icon"] = icon
        rows.append(row)
    return rows
