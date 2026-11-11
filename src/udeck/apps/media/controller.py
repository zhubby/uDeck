"""QtMultimedia playback. UI state comes from observed player properties."""


from PySide6.QtCore import Property, QObject, Slot
from PySide6.QtMultimedia import QMediaPlayer

from udeck.apps.common.controller import AppController
from udeck.apps.common.state import PlayQueue
from udeck.i18n import Msg, tr
from udeck.sounds import interaction

from .engine import MediaEngine


class MediaController(AppController):
    def __init__(self, app, directory=None, language_path=None):
        super().__init__(app, directory, language_path)
        self.media = MediaEngine(self)
        self.media.changed.connect(self.publish)
        self.media.ended.connect(self.end_file)
        self.media.failed.connect(self.playback_failed)
        self.queue = PlayQueue()
        self.queue.items = self.store.data["queue"]
        self.queue.repeat = self.store.data["preferences"].get("repeat", "off")
        self.queue.shuffle = bool(self.store.data["preferences"].get("shuffle", False))
        self.album = ""
        self.controls = 1
        self.controls_visible = True
        self.inactive = 0
        self.external_cues = []
        self.external_name = ""
        self.paused_by_video = ""
        self.music_token = ""

    @Property(QObject, constant=True)
    def player(self):
        return self.media.player

    @Property(bool, constant=True)
    def softwareRendering(self):
        return self.media.software

    @Slot(float)
    def seek(self, seconds):
        self.media.seek(seconds)

    def play(self, item, seconds=0, queued=False, music_confirmed=False):
        item = self.library.require(item["id"])
        if not self.prepare_play(item, seconds, queued, music_confirmed):
            return
        self.save_position()
        self.current = dict(item)
        self.external_cues, self.external_name = [], ""
        self.clear_menus()
        if self.page != "player":
            self.enter("player")
        self.controls_visible = True
        self.inactive = 0
        self.media.load(item, seconds * 1000)
        self.store.remember(item["id"])
        self.persist()
        self.publish()

    def save_position(self):
        if (self.current and self.media.identifier == self.current["id"]
                and not self.media.loading and not self.media.player.errorString()):
            ended = self.media.player.mediaStatus() == QMediaPlayer.MediaStatus.EndOfMedia
            self.store.data["positions"][self.current["id"]] = 0 if ended else self.media.player.position() / 1000

    def poll(self):
        super().poll()
        self.save_position()
        self.inactive += 1
        self.update_controls()
        if self.inactive % 5 == 0:
            self.attempt(self.persist)
        self.publish()

    def extra_state(self):
        return {"media": self.media.snapshot(), "control": self.controls,
                "controlsVisible": self.controls_visible, "repeat": self.queue.repeat,
                "repeatLabel": {"off": tr(Msg.OFF), "all": tr(Msg.ALL_TRACKS), "one": tr(Msg.CURRENT_TRACK)}[self.queue.repeat],
                "shuffle": self.queue.shuffle, "album": self.album,
                "subtitleText": self.subtitle_text(), "videoFrameRevision": self.media.frame_revision}

    @Slot(str)
    @interaction
    def dispatch(self, action):
        self.inactive = 0
        if self.page == "player" and not self.menus:
            if action in ("left", "right"):
                self.media.seek(self.media.player.position() / 1000 + (-10 if action == "left" else 10))
            elif action in ("up", "down"):
                previous = self.controls
                self.controls = max(0, min(2, self.controls + (-1 if action == "up" else 1)))
                if self.controls != previous:
                    self.feedback("navigate")
            elif action == "accept":
                if self.controls_visible:
                    self.command(("previous", "play-pause", "next")[self.controls])
                self.controls_visible = True
            elif action in ("previous-tab", "next-tab"):
                self.command("previous" if action == "previous-tab" else "next")
            else:
                super().dispatch(action)
            if action != "accept":
                self.controls_visible = True
            self.publish()
            return
        super().dispatch(action)

    @Slot(str)
    @interaction
    def command(self, command):
        if command == "play-pause":
            self.feedback("accept")
            self.paused_by_video = ""
            self.media.toggle()
        elif command in ("previous", "next"):
            self.feedback("accept")
            self.attempt(lambda: self.next_track(-1 if command == "previous" else 1))
        elif command == "now-playing" and self.current:
            if self.page != "player":
                self.enter("player")
        elif command == "hide-controls":
            self.controls_visible = False
            self.clear_menus()
        elif command == "seek":
            self.prompt(tr(Msg.POSITION_IN_SECONDS), lambda value: self.media.seek(float(value)))
        else:
            super().command(command)
        self.publish()

    def end_file(self):
        if self.current:
            self.store.data["positions"][self.current["id"]] = 0
        self.finished_playback()

    def playback_failed(self, text):
        self.error = tr(Msg.PLAYBACK_FAILED_ERROR, error=text)
        self.controls_visible = True
        self.release_music()
        self.publish()

    def output_menu(self):
        options = []
        for device in self.media.devices.audioOutputs():
            key = bytes(device.id()).hex()
            options.append((device.description(), lambda key=key: self.change_output(key)))
        self.menu(tr(Msg.AUDIO_OUTPUT), options, tr(Msg.CURRENT_OUTPUT_NAME, output=self.media.snapshot()["output"]), icon="audio-card")

    def change_output(self, identifier):
        self.media.set_output(identifier)
        self.pop_menu()

    def stop_source(self):
        self.save_position()
        self.attempt(self.persist)
        self.media.close()
        self.release_music()

    def persist(self):
        self.store.data["queue"] = self.queue.items
        self.store.data["preferences"].update(repeat=self.queue.repeat, shuffle=self.queue.shuffle)
        super().persist()

    def close(self):
        self.save_position()
        super().close()
        self.media.close()
        self.release_music()

    def open_item(self, identifier):
        self.play(self.library.require(identifier))

    def update_controls(self):
        pass

    def release_music(self):
        pass

    def subtitle_text(self):
        return ""

    def settings_options(self):
        return [(tr(Msg.AUDIO_OUTPUT), self.output_menu, "", "audio-card")]

    def library_options(self):
        return [(tr(Msg.SEARCH), lambda: self.prompt(tr(Msg.SEARCH_LIBRARY), self.search, self.filter)),
                (tr(Msg.SOURCES), self.sources_menu), (tr(Msg.REFRESH_LIBRARY), self.refresh)]

    def context(self):
        self.menu(tr(Msg.LIBRARY_ACTIONS), self.library_options())

def time_label(seconds):
    seconds = max(0, int(seconds))
    return f"{seconds // 60:02d}:{seconds % 60:02d}"
