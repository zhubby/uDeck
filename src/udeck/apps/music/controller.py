"""[INPUT]: 依赖共享媒体控制器、曲库封面和本地歌词解析。
[OUTPUT]: 提供专辑封面、歌词、播放队列与播放器音量。
[POS]: Music 界面与共享媒体引擎之间的控制层。
[PROTOCOL]: Update this header on change, then check AGENTS.md
"""

import hashlib
from pathlib import Path

from PySide6.QtCore import Property, Signal, Slot

from udeck.apps.media.controller import MediaController
from udeck.i18n import Msg, tr

from .lyrics import track_lyrics


class MusicController(MediaController):
    lyricsChanged = Signal()

    def __init__(self, directory=None, language_path=None):
        super().__init__("music", directory, language_path)
        self._lyrics = {"timed": False, "lines": []}
        preferences = self.store.data["preferences"]
        volume = preferences.get("playbackVolume", 80)
        if type(volume) is int:
            self.media.output.setVolume(max(0, min(100, volume)) / 100)
        self.media.output.setMuted(preferences.get("playbackMuted") is True)

    @Slot(int)
    def setVolume(self, percent):
        self.media.output.setVolume(max(0, min(100, percent)) / 100)

    @Slot()
    def toggleMute(self):
        self.media.output.setMuted(not self.media.output.isMuted())
        self.attempt(self.persist)

    def persist(self):
        self.store.data["preferences"].update(
            playbackVolume=round(self.media.output.volume() * 100),
            playbackMuted=self.media.output.isMuted(),
        )
        super().persist()

    def settings_options(self):
        return super().settings_options() + [
            self.setting_option(tr(Msg.VOLUME), self.volume_menu, "audio-volume-high", self.volume_status()),
        ]

    def volume_status(self):
        state = self.media.snapshot()
        return tr(Msg.MUTE) if state["muted"] else f"{state['volume']}%"

    def volume_menu(self):
        def options():
            state = self.media.snapshot()
            return [
                self.setting_option(tr(Msg.VOLUME_DOWN), lambda: self.adjust_volume(-5), "audio-volume-high",
                                    self.volume_status(), navigate=False),
                self.setting_option(tr(Msg.VOLUME_UP), lambda: self.adjust_volume(5), "audio-volume-high",
                                    self.volume_status(), navigate=False),
                self.setting_option(tr(Msg.UNMUTE if state["muted"] else Msg.MUTE), self.toggleMute,
                                    "audio-volume-muted", navigate=False),
            ]
        self.menu(tr(Msg.VOLUME), options, icon="audio-volume-high")

    def adjust_volume(self, delta):
        self.setVolume(self.media.snapshot()["volume"] + delta)
        self.attempt(self.persist)

    @Property("QVariantMap", notify=lyricsChanged)
    def lyrics(self):
        return self._lyrics

    def snapshot(self, compact=False):
        state = super().snapshot(compact)
        if compact:
            state["current"] = {key: value for key, value in state["current"].items() if key != "metadata"}
        return state

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
                album = groups[key]
                if not album["cover"]:
                    album["cover"] = row["cover"]
                album["tracks"] += 1
            return list(groups.values())
        if self.tab == 2:
            by_id = {r["id"]: r for r in rows}
            return [by_id[i] for i in self.queue.items if i in by_id]
        return rows

    def _library_changed(self):
        if self.current:
            track = next((item for item in self.library.items if item["id"] == self.current["id"]), None)
            if track:
                self.current["cover"] = track["cover"]
        super()._library_changed()

    def prepare_play(self, item, seconds, queued):
        self._lyrics = track_lyrics(item)
        self.lyricsChanged.emit()
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
