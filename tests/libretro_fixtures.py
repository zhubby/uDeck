"""Explicit playlist setup for existing native and QML probes."""

from pathlib import Path

from udeck.apps.emulator.playlists import generate_playlists


def configure_library(controller, rom_root):
    rom_root = Path(rom_root)
    playlists = rom_root.parent / "playlists"
    thumbnails = rom_root.parent / "thumbnails"
    playlists.mkdir(exist_ok=True)
    thumbnails.mkdir(exist_ok=True)
    generate_playlists(rom_root, playlists, controller.catalog).commit()
    controller.library.playlist_path = str(playlists)
    controller.library.thumbnail_path = str(thumbnails)
    controller.store.data["preferences"].update(playlistDirectory=str(playlists),
                                               thumbnailDirectory=str(thumbnails), emulatorSchema=3)
    controller.library.configure_root(rom_root)
