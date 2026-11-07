"""Global interface themes, independent of document and terminal palettes."""

from .i18n import tr

DEFAULT_THEME = "classic"
THEMES = {"classic": tr("Classic"), "dark": tr("Dark")}


def theme_code(value):
    return value if isinstance(value, str) and value in THEMES else DEFAULT_THEME
