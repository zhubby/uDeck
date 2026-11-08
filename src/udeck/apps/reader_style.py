"""Validated reader typography and palette preferences."""


READER_FONT_SIZES = (18, 20, 24, 28, 32, 36)
READER_LINE_HEIGHTS = (1.4, 1.6, 1.7, 1.8, 2.0)
READER_FONT_FAMILIES = {
    "sans": "system-ui, sans-serif",
    "serif": "Georgia, 'Noto Serif CJK SC', serif",
    "mono": "ui-monospace, monospace",
}
READER_BACKGROUNDS = {
    "paper": {"background": "#ece7da", "text": "#282722", "dark": False},
    "warm": {"background": "#f2e5c7", "text": "#332a1d", "dark": False},
    "gray": {"background": "#d7dadd", "text": "#202426", "dark": False},
    "night": {"background": "#202426", "text": "#eee8da", "dark": True},
}
READER_CONTENT_WIDTHS = (720, 1000, 1200)
READER_DEFAULTS = {
    "fontSize": 24,
    "lineHeight": 1.7,
    "fontFamily": "sans",
    "background": "paper",
    "contentWidth": 1000,
    "dark": False,
}


def _choice(value, choices, default):
    if type(value) in (int, float) and value in choices:
        return value
    return default


def normalize_reader_preferences(preferences):
    preferences = preferences if isinstance(preferences, dict) else {}
    background = preferences.get("background")
    if background not in READER_BACKGROUNDS:
        background = "night" if preferences.get("dark") is True else READER_DEFAULTS["background"]
    return {
        "fontSize": _choice(preferences.get("fontSize"), READER_FONT_SIZES, READER_DEFAULTS["fontSize"]),
        "lineHeight": _choice(preferences.get("lineHeight"), READER_LINE_HEIGHTS, READER_DEFAULTS["lineHeight"]),
        "fontFamily": preferences.get("fontFamily") if preferences.get("fontFamily") in READER_FONT_FAMILIES
        else READER_DEFAULTS["fontFamily"],
        "background": background,
        "contentWidth": _choice(preferences.get("contentWidth"), READER_CONTENT_WIDTHS,
                                 READER_DEFAULTS["contentWidth"]),
        "dark": READER_BACKGROUNDS[background]["dark"],
    }
