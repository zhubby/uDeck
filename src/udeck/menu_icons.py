"""System menu presentation, independent of labels and action payloads."""

SETTING_ICON_PREFIX = "udeck-setting:"
SETTING_ARTWORK = {
    "audio-volume-high": "volume-up-fill",
    "audio-volume-muted": "volume-mute-fill",
    "display-brightness": "brightness-high-fill",
    "audio-card": "headphones",
    "audio-input-microphone": "mic-fill",
    "microphone-sensitivity-muted": "mic-mute-fill",
    "network-wireless": "wifi",
    "bluetooth": "bluetooth",
    "battery": "battery-half",
    "input-gaming": "controller",
    "input-keyboard": "keyboard-fill",
    "preferences-desktop-keyboard-shortcuts": "command",
    "preferences-desktop-locale": "translate",
    "preferences-desktop-theme": "palette-fill",
    "preferences-system-time": "clock-fill",
    "system-lock-screen": "lock-fill",
    "video-display": "display",
    "system-log-out": "box-arrow-right",
    "system-reboot": "arrow-clockwise",
    "system-shutdown": "power",
    "preferences-system-windows": "window-stack",
    "list-add": "plus-circle-fill",
    "edit-delete": "trash3-fill",
    "network-connect": "link-45deg",
    "folder": "folder-fill",
    "network-disconnect": "x-circle-fill",
    "document-open-recent": "clock-history",
    "dialog-information": "info-circle-fill",
    "dialog-password": "key-fill",
    "document-edit": "pencil-square",
    "dialog-warning": "exclamation-triangle-fill",
    "view-refresh": "arrow-clockwise",
    "edit-find": "search",
    "process-stop": "stop-circle-fill",
    "preferences-system": "gear-fill",
}

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
    "sharing": "network-connect",
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

NAVIGATION_ACTIONS = {
    "setting", "power-menu", "switcher", "timezone-region", "audio-card", "device",
    "wifi-device", "wifi-connect", "wifi-saved", "wifi-saved-connect", "wifi-profile",
    "wifi-password", "wifi-details", "hotspot-device", "hotspot-name", "hotspot-password",
    "shortcut-group", "shortcut-detail", "shortcut-record",
}


def system_menu_icons(options, source=""):
    settings_menu = source in {
        "settings", "quick-settings", "language", "theme", "timezone-areas", "timezone-cities",
        "wifi", "wifi-device", "wifi-saved", "wifi-network", "wifi-profiles", "wifi-details",
        "hotspot", "hotspot-device", "bluetooth", "volume", "audio-input", "audio-output", "audio-cards", "audio-profiles",
        "shortcuts", "shortcuts-group", "shortcut-action",
    } or source.startswith("sharing") or any(option.get("action") in ACTION_ICONS or option.get("action") == "setting"
             or option.get("action") == "system" and option.get("systemAction") in SYSTEM_ICONS
             for option in options)
    if not settings_menu:
        return options
    rows = []
    for option in options:
        row = dict(option)
        action = row.get("action")
        if source != "settings":
            row["singleLine"] = True
            row["navigate"] = (row.get("navigate", False) or action in NAVIGATION_ACTIONS) and not isinstance(row.get("checked"), bool)
        if not row.get("icon"):
            if action == "setting":
                icon = SETTING_ICONS.get(row.get("idSetting", row.get("id")), "preferences-system")
            elif action == "system":
                icon = SYSTEM_ICONS.get(row.get("systemAction"), "preferences-system")
            elif action == "audio-profile" and row.get("profile", {}).get("microphone"):
                icon = "audio-input-microphone"
            elif action and action.startswith("shortcut-"):
                icon = "preferences-desktop-keyboard-shortcuts"
            else:
                icon = ACTION_ICONS.get(action, "dialog-warning" if row.get("disabled") else "dialog-information")
            row["icon"] = icon
        if row["icon"] in SETTING_ARTWORK:
            row["icon"] = SETTING_ICON_PREFIX + SETTING_ARTWORK[row["icon"]]
        rows.append(row)
    return rows
