"""Music albums, playback queue and background lifecycle."""

import hashlib
from pathlib import Path

from PySide6.QtCore import Slot

from udeck.apps.media.controller import MediaController
from udeck.i18n import Msg, tr


class MusicController(MediaController):
    def __init__(self, directory=None, language_path=None):
        super().__init__("music", directory, language_path)

    def tabs(self):
        return [tr(Msg.ALBUMS), tr(Msg.TRACKS), tr(Msg.QUEUE), tr(Msg.FOLDERS)]

    def rows(self):
        rows = super().rows()
        if self.page == "album":
            return [r for r in rows if self.album_id(r) == self.album]
        if self.tab == 0:
            groups = {}
            for row in rows:
                key = self.album_id(row)
                if key not in groups:
                    groups[key] = {**row, "id": key, "title": row["album"], "kind": "album",
                                   "subtitle": row["artist"] or Path(row["folder"]).name, "tracks": 0}
                groups[key]["tracks"] += 1
            return list(groups.values())
        if self.tab == 2:
            by_id = {r["id"]: r for r in rows}
            return [by_id[i] for i in self.queue.items if i in by_id]
        return rows

    def prepare_play(self, item, seconds, queued):
        if not queued:
            ids = [r["id"] for r in self.rows() if r.get("kind") == "item"]
            self.queue.replace(ids or [item["id"]], item["id"])

    def next_track(self, delta=1):
        identifier = self.queue.advance(delta)
        if identifier:
            self.play(self.library.require(identifier), queued=True)
        else:
            self.media.player.pause()
            self.notice = tr(Msg.QUEUE_FINISHED)

    def finished_playback(self):
        self.attempt(self.next_track)

    def context(self):
        if self.page == "player" or self.tab == 2:
            options = [(tr(Msg.SHOW_QUEUE), self.queue_view),
                       (tr(Msg.SHUFFLE_VALUE, value=tr(Msg.ON) if self.queue.shuffle else tr(Msg.OFF)), self.toggle_shuffle),
                       (tr(Msg.REPEAT_VALUE, value={"off": tr(Msg.OFF), "all": tr(Msg.ALL_TRACKS), "one": tr(Msg.CURRENT_TRACK)}[self.queue.repeat]), self.toggle_repeat)]
            if self.selected in self.queue.items:
                options += [(tr(Msg.MOVE_UP), self.queue_move), (tr(Msg.REMOVE_FROM_QUEUE), self.queue_remove)]
            self.menu(tr(Msg.QUEUE), options)
        else:
            options = self.library_options()
            if self.selected:
                options.insert(0, (tr(Msg.ADD_TO_QUEUE), self.enqueue))
            self.menu(tr(Msg.LIBRARY_ACTIONS), options)

    @Slot()
    def requestClose(self):
        if self.media.snapshot()["playing"]:
            self.menu(tr(Msg.MUSIC_IS_PLAYING), [
                (tr(Msg.CONTINUE_IN_BACKGROUND), self.background, "", "preferences-system-windows"),
                (tr(Msg.STOP_AND_EXIT), self.stop_exit, "", "media-playback-stop"),
                (tr(Msg.CANCEL), self.pop_menu, "", "go-previous")])
        else:
            super().requestClose()

    @staticmethod
    def album_id(item):
        return "album:" + hashlib.sha256((item["album"] + "|" + item["artist"]
                                           + "|" + item["folder"]).encode()).hexdigest()

    def activate(self, row):
        if row.get("kind") == "album":
            self.enter("album")
            self.album, self.selected = row["id"], ""
        else:
            super().activate(row)

    def queue_view(self):
        self.clear_menus()
        if self.page != "library" or self.tab != 2:
            self.enter("library")
            self.tab, self.folder = 2, ""
            self.selected = self.queue.current or ""
        self.publish()

    def enqueue(self):
        row = next((r for r in self.rows() if r["id"] == self.selected), None)
        if row and row.get("kind") == "album":
            ids = [i["id"] for i in self.library.items if self.album_id(i) == row["id"]]
        else:
            ids = [self.library.require(self.selected)["id"]]
        self.queue.append(ids)
        self.persist()
        self.pop_menu()

    def queue_move(self):
        self.queue.move(self.selected, -1)
        self.pop_menu()

    def queue_remove(self):
        self.queue.remove(self.selected)
        self.pop_menu()

    def toggle_shuffle(self):
        self.queue.shuffle = not self.queue.shuffle
        self.pop_menu()
        self.context()

    def toggle_repeat(self):
        self.queue.repeat = {"off": "all", "all": "one", "one": "off"}[self.queue.repeat]
        self.pop_menu()
        self.context()

    def background(self):
        self.clear_menus()
        if self.window:
            self.window.hide()

    def stop_exit(self):
        self.save_position()
        self.attempt(self.persist)
        self.media.close()
        super().requestClose()
