"""Stock uConsole key reports, based on ClockworkPi's two firmware layers.

The firmware does not send Fn, keyboard backlight or keyboard lock events. The
power switch belongs to the system, not the USB keyboard. Keep these visible
without including them in the number of keys the application can observe.
"""

from PySide6.QtCore import Qt

from .i18n import Msg, tr


def cap(identifier, label=None, icon=None, *, weight=1, detectable=True, rotation=0):
    label = label or identifier.upper()
    return {"id": identifier, "label": label, "labelKey": getattr(label, "key", ""), "key": icon or "",
            "weight": weight, "detectable": detectable, "rotation": rotation}


KEYBOARD_ROWS = [
    [cap("grave", "`", "keyboard_tilde")] + [cap(str(n), icon=f"keyboard_{n}") for n in (*range(1, 10), 0)]
    + [cap("minus", "−", "keyboard_minus"), cap("equals", "=", "keyboard_equals")],
    [cap("tab", "Tab", "keyboard_tab")] + [cap(c, icon=f"keyboard_{c}") for c in "qwertyuiop"]
    + [cap("bracket-open", "[", "keyboard_bracket_open"), cap("bracket-close", "]", "keyboard_bracket_close")],
    [cap("escape", "Esc", "keyboard_escape")] + [cap(c, icon=f"keyboard_{c}") for c in "asdfghjkl"]
    + [cap("semicolon", ";", "keyboard_semicolon"), cap("apostrophe", "'", "keyboard_apostrophe"),
       cap("backslash", "\\", "keyboard_slash_back")],
    [cap("shift-left", "L Shift", "keyboard_shift")] + [cap(c, icon=f"keyboard_{c}") for c in "zxcvbnm"]
    + [cap("comma", ",", "keyboard_comma"), cap("period", ".", "keyboard_period"),
       cap("slash", "/", "keyboard_slash_forward"), cap("backspace", "Backspace", "keyboard_backspace_icon"),
       cap("shift-right", "R Shift", "keyboard_shift")],
    [cap("ctrl-left", "L Ctrl"), cap("alt-left", "L Alt"), cap("meta", "Cmd", "keyboard_command"),
     cap("fn", "Fn ×2", detectable=False), cap("space", "Space", "keyboard_space", weight=2.5),
     cap("enter", "Enter", "keyboard_enter", weight=1.5), cap("alt-right", "R Alt"), cap("ctrl-right", "R Ctrl")],
    [cap(f"f{n}", f"F{n}", f"keyboard_f{n}") for n in range(1, 13)],
    [cap("print", "PrtSc", "keyboard_printscreen"), cap("pause", "Pause"),
     cap("caps-lock", "Caps", "keyboard_capslock_icon"), cap("insert", "Ins", "keyboard_insert"),
     cap("delete", "Del", "keyboard_delete"), cap("home", "Home", "keyboard_home"),
     cap("end", "End", "keyboard_end"), cap("page-up", "PgUp", "keyboard_page_up"),
     cap("page-down", "PgDn", "keyboard_page_down")],
    [cap("volume-down", tr(Msg.VOLUME_DOWN_SHORT)), cap("volume-up", tr(Msg.VOLUME_UP_SHORT)), cap("mute", tr(Msg.MUTE)),
     cap("brightness-down", tr(Msg.BRIGHTNESS_DOWN_SHORT)), cap("brightness-up", tr(Msg.BRIGHTNESS_UP_SHORT))],
]
GAMEPAD_KEYS = [
    cap("previous-page", "L / M1", "gamecube_trigger_l"), cap("select", "Select"),
    cap("start", "Start", "gamecube_button_start"), cap("next-page", "R / M2", "gamecube_trigger_r"),
    cap("up", tr(Msg.UP), "keyboard_arrow_up"), cap("context", "X", "gamecube_button_x"),
    cap("left", tr(Msg.LEFT), "keyboard_arrow_up", rotation=270),
    cap("right", tr(Msg.RIGHT), "keyboard_arrow_up", rotation=90),
    cap("quick-settings", "Y", "gamecube_button_y"), cap("accept", "A", "gamecube_button_color_a"),
    cap("down", tr(Msg.DOWN), "keyboard_arrow_up", rotation=180), cap("back", "B", "gamecube_button_color_b"),
]
POINTER_KEYS = [
    cap("pointer-left", tr(Msg.TRACKBALL_LEFT), "keyboard_arrow_up", rotation=270),
    cap("pointer-up", tr(Msg.TRACKBALL_UP), "keyboard_arrow_up"),
    cap("pointer-down", tr(Msg.TRACKBALL_DOWN), "keyboard_arrow_up", rotation=180),
    cap("pointer-right", tr(Msg.TRACKBALL_RIGHT), "keyboard_arrow_up", rotation=90),
    cap("pointer-click", tr(Msg.MIDDLE_CLICK), "mouse_scroll"),
    cap("wheel-up", tr(Msg.SCROLL_UP), "mouse_scroll_up"), cap("wheel-down", tr(Msg.SCROLL_DOWN), "mouse_scroll_down"),
]
INTERNAL_KEYS = [cap("keyboard-light", tr(Msg.BACKLIGHT), detectable=False),
                 cap("keyboard-lock", tr(Msg.KEY_LOCK), detectable=False),
                 cap("power", tr(Msg.POWER), detectable=False)]
KEY_SPECS = {key["id"]: key for key in sum(KEYBOARD_ROWS, []) + GAMEPAD_KEYS + POINTER_KEYS + INTERNAL_KEYS}

# Linux evdev codes, also used to interpret XKB native scan codes (evdev + 8).
LINUX_KEYS = {
    1: "escape", **{n + 2: str((n + 1) % 10) for n in range(10)}, 12: "minus", 13: "equals",
    14: "backspace", 15: "tab", **{16 + i: c for i, c in enumerate("qwertyuiop")},
    26: "bracket-open", 27: "bracket-close", 28: "enter", 29: "ctrl-left",
    **{30 + i: c for i, c in enumerate("asdfghjkl")}, 39: "semicolon", 40: "apostrophe", 41: "grave",
    42: "shift-left", 43: "backslash", **{44 + i: c for i, c in enumerate("zxcvbnm")},
    51: "comma", 52: "period", 53: "slash", 54: "shift-right", 56: "alt-left", 57: "space",
    58: "caps-lock", **{58 + n: f"f{n}" for n in range(1, 11)}, 87: "f11", 88: "f12",
    97: "ctrl-right", 99: "print", 100: "alt-right", 102: "home", 103: "up", 104: "page-up",
    105: "left", 106: "right", 107: "end", 108: "down", 109: "page-down", 110: "insert",
    111: "delete", 113: "mute", 114: "volume-down", 115: "volume-up", 119: "pause",
    125: "meta", 126: "meta", 224: "brightness-down", 225: "brightness-up",
}
QT_KEYS = {
    **{ord(c.upper()): c for c in "abcdefghijklmnopqrstuvwxyz0123456789"},
    **{getattr(Qt.Key, f"Key_F{n}"): f"f{n}" for n in range(1, 13)},
    **{getattr(Qt.Key, "Key_" + name): identifier for name, identifier in {
        "Up": "up", "Down": "down", "Left": "left", "Right": "right", "Return": "enter", "Enter": "enter",
        "Escape": "escape", "Backspace": "backspace", "Tab": "tab", "Backtab": "tab", "Space": "space",
        "QuoteLeft": "grave", "Minus": "minus", "Equal": "equals", "BracketLeft": "bracket-open",
        "BracketRight": "bracket-close", "Backslash": "backslash", "Semicolon": "semicolon",
        "Apostrophe": "apostrophe", "Comma": "comma", "Period": "period", "Slash": "slash",
        "Shift": "shift-left", "Control": "ctrl-left", "Alt": "alt-left", "AltGr": "alt-right",
        "Meta": "meta", "Super_L": "meta", "Super_R": "meta", "CapsLock": "caps-lock",
        "Insert": "insert", "Delete": "delete", "Home": "home", "End": "end", "PageUp": "page-up",
        "PageDown": "page-down", "Print": "print", "SysReq": "print", "Pause": "pause",
        "VolumeDown": "volume-down", "VolumeUp": "volume-up", "VolumeMute": "mute",
        "MonBrightnessDown": "brightness-down", "MonBrightnessUp": "brightness-up",
    }.items()},
    **{ord(symbol): identifier for symbol, identifier in zip(
        '~!@#$%^&*()_+{}|:"<>?',
        ["grave", *"1234567890", "minus", "equals", "bracket-open", "bracket-close", "backslash",
         "semicolon", "apostrophe", "comma", "period", "slash"], strict=True)},
}
