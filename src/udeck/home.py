from .i18n import tr

HOME_SHORTCUTS = (
    {"id": "io.github.zhubby.uDeck.Terminal.desktop", "homeKind": "terminal",
     "name": tr("终端"), "subtitle": tr("Local shell sessions and command-line tools"),
     "icon": "io.github.zhubby.uDeck.Terminal", "category": "System"},
    {"id": "io.github.zhubby.uDeck.Music.desktop", "homeKind": "music",
     "name": tr("Music"), "subtitle": tr("Browse albums, tracks and playlists"),
     "icon": "io.github.zhubby.uDeck.Music", "category": "AudioVideo"},
    {"id": "io.github.zhubby.uDeck.Video.desktop", "homeKind": "video",
     "name": tr("Video"), "subtitle": tr("Watch your local video library"),
     "icon": "io.github.zhubby.uDeck.Video", "category": "AudioVideo"},
    {"id": "io.github.zhubby.uDeck.Reader.desktop", "homeKind": "reader",
     "name": tr("Reader"), "subtitle": tr("Read EPUB, PDF and text books"),
     "icon": "io.github.zhubby.uDeck.Reader", "category": "Office"},
    {"id": "io.github.zhubby.uDeck.Emulator.desktop", "homeKind": "emulator",
     "name": tr("Emulator"), "subtitle": tr("Open your game library and saved progress"),
     "icon": "io.github.zhubby.uDeck.Emulator", "category": "Game"},
    {"id": "settings", "homeKind": "settings", "name": tr("Settings"),
     "subtitle": tr("Network, audio, display and device preferences"),
     "icon": "preferences-system", "category": "System"},
)


def home_shortcuts(applications):
    available = {application["id"]: application for application in applications}
    return [
        {**available.get(shortcut["id"], {}), **shortcut,
         "disabled": shortcut["id"] != "settings" and shortcut["id"] not in available,
         "reason": tr("This app is not installed.") if shortcut["id"] not in available
         and shortcut["id"] != "settings" else ""}
        for shortcut in HOME_SHORTCUTS
    ]
