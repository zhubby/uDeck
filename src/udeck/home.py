from .i18n import Msg, tr

HOME_SHORTCUTS = (
    {"id": "io.github.zhubby.uDeck.Terminal.desktop", "homeKind": "terminal",
     "name": tr(Msg.TERMINAL), "subtitle": tr(Msg.LOCAL_SHELL_SESSIONS_AND_COMMAND_LINE_TOOLS),
     "icon": "io.github.zhubby.uDeck.Terminal", "category": "System"},
    {"id": "io.github.zhubby.uDeck.Music.desktop", "homeKind": "music",
     "name": tr(Msg.MUSIC), "subtitle": tr(Msg.BROWSE_ALBUMS_TRACKS_AND_PLAYLISTS),
     "icon": "io.github.zhubby.uDeck.Music", "category": "AudioVideo"},
    {"id": "io.github.zhubby.uDeck.Video.desktop", "homeKind": "video",
     "name": tr(Msg.VIDEO), "subtitle": tr(Msg.WATCH_YOUR_LOCAL_VIDEO_LIBRARY),
     "icon": "io.github.zhubby.uDeck.Video", "category": "AudioVideo"},
    {"id": "io.github.zhubby.uDeck.Reader.desktop", "homeKind": "reader",
     "name": tr(Msg.READER), "subtitle": tr(Msg.READ_EPUB_MOBI_PDF_AND_TEXT_BOOKS),
     "icon": "io.github.zhubby.uDeck.Reader", "category": "Office"},
    {"id": "io.github.zhubby.uDeck.Emulator.desktop", "homeKind": "emulator",
     "name": tr(Msg.EMULATOR), "subtitle": tr(Msg.OPEN_YOUR_GAME_LIBRARY_AND_SAVED_PROGRESS),
     "icon": "io.github.zhubby.uDeck.Emulator", "category": "Game"},
    {"id": "io.github.zhubby.uDeck.Browser.desktop", "homeKind": "browser",
     "name": tr(Msg.BROWSER), "subtitle": tr(Msg.BROWSE_THE_WEB_WITH_TABS_AND_BOOKMARKS),
     "icon": "io.github.zhubby.uDeck.Browser", "category": "Network"},
    {"id": "settings", "homeKind": "settings", "name": tr(Msg.SETTINGS),
     "subtitle": tr(Msg.NETWORK_AUDIO_DISPLAY_AND_DEVICE_PREFERENCES),
     "icon": "preferences-system", "category": "System"},
)


def home_shortcuts(applications):
    available = {application["id"]: application for application in applications}
    return [
        {**available.get(shortcut["id"], {}), **shortcut,
         "disabled": shortcut["id"] != "settings" and shortcut["id"] not in available,
         "reason": tr(Msg.THIS_APP_IS_NOT_INSTALLED) if shortcut["id"] not in available
         and shortcut["id"] != "settings" else ""}
        for shortcut in HOME_SHORTCUTS
    ]
