"""Global interface themes; document palettes remain independent."""

from .i18n import Msg, tr

DEFAULT_THEME = "classic"
THEMES = {"classic": tr(Msg.CLASSIC), "dark": tr(Msg.DARK)}


def theme_code(value):
    return value if isinstance(value, str) and value in THEMES else DEFAULT_THEME
