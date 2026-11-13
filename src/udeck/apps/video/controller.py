"""Video resume, chapters and subtitles."""

from pathlib import Path

from PySide6.QtCore import QObject, Slot
from PySide6.QtMultimedia import QMediaMetaData

from udeck.apps.media.controller import MediaController, time_label
from udeck.i18n import Msg, tr

from .subtitles import EmbeddedSubtitles, parse_srt


class VideoController(MediaController):
    def __init__(self, directory=None, language_path=None):
        super().__init__("video", directory, language_path)
        self.pointer_pressed = False
        self.subtitle_error = ""
        self.embedded_subtitles = EmbeddedSubtitles(self)
        self.embedded_subtitles.ready.connect(self.subtitles_ready)
        self.embedded_subtitles.failed.connect(self.subtitles_failed)
        self.media.player.sourceChanged.connect(self.clear_subtitles)

    def tabs(self):
        return [tr(Msg.CONTINUE_WATCHING), tr(Msg.ALL_VIDEOS), tr(Msg.FOLDERS)]

    def rows(self):
        rows = super().rows()
        if self.tab == 0:
            return [r for r in rows if self.store.data["positions"].get(r["id"], 0) > 0]
        return rows

    def open_item(self, identifier):
        item = self.library.require(identifier)
        position = self.store.data["positions"].get(identifier, 0)
        if position > 0:
            self.menu(tr(Msg.RESUME_VIDEO_PROMPT), [
                (tr(Msg.CONTINUE_FROM_POSITION, position=time_label(position)), lambda: self.play(item, position)),
                (tr(Msg.START_FROM_BEGINNING), lambda: self.play(item))], item["title"], item["sourceId"])
        else:
            self.play(item)

    def prepare_play(self, item, seconds, queued):
        self.clear_subtitles()

    def update_controls(self):
        if (self.page == "player" and self.inactive >= 5
                and self.media.snapshot()["playing"] and not self.menus and not self.pointer_pressed):
            self.controls_visible = False

    @Slot(bool)
    def pointerPressed(self, pressed):
        self.pointer_pressed = pressed
        self.pointerActivity()

    @Slot()
    def pointerActivity(self):
        if self.page != "player" or self.menus:
            return
        self.inactive = 0
        if not self.controls_visible:
            self.controls_visible = True
            self.publish()

    def next_track(self, delta=1):
        chapters = self.current.get("metadata", {}).get("chapters", []) if self.current else []
        pos = self.media.player.position() / 1000
        starts = [float(c["start_time"]) for c in chapters]
        target = (next((x for x in starts if x > pos + 1), self.media.player.duration() / 1000)
                  if delta > 0 else next((x for x in reversed(starts) if x < pos - 2), 0))
        self.media.seek(target)

    def finished_playback(self):
        self.controls_visible = True
        self.notice = tr(Msg.PLAYBACK_FINISHED)

    def context(self):
        if self.page == "player":
            self.menu(tr(Msg.PLAYBACK_OPTIONS), [
                (tr(Msg.SUBTITLES), lambda: self.track_menu(True)),
                (tr(Msg.EXTERNAL_SUBTITLES_SRT), self.external_subtitles),
                (tr(Msg.AUDIO_TRACKS), lambda: self.track_menu(False)),
                (tr(Msg.CHAPTERS), self.chapter_menu), (tr(Msg.SPEED), self.speed_menu),
                (tr(Msg.GO_TO_POSITION), lambda: self.command("seek")),
                (tr(Msg.HIDE_CONTROLS), lambda: self.command("hide-controls"))])
        else:
            super().context()

    @Slot(QObject)
    def setVideoSink(self, sink):
        self.media.player.setVideoSink(sink)
        if self.media.software:
            sink.videoFrameChanged.connect(self.media.video_frame)
            sink.subtitleTextChanged.connect(self.media.changed)

    def back(self):
        if self.page == "player":
            self.media.player.pause()
            self.save_position()
            self.persist()
        super().back()

    def track_menu(self, subtitles):
        player = self.media.player
        tracks = player.subtitleTracks() if subtitles else player.audioTracks()
        options = [(tr(Msg.OFF), lambda: self.set_track(True, -1))] if subtitles else []
        for index, metadata in enumerate(tracks):
            title = metadata.stringValue(QMediaMetaData.Key.Title)
            language = metadata.stringValue(QMediaMetaData.Key.Language)
            options.append((title or language or str(index + 1),
                            lambda i=index: self.set_track(subtitles, i)))
        self.menu(tr(Msg.SUBTITLES) if subtitles else tr(Msg.AUDIO_TRACKS), options)

    def set_track(self, subtitles, index):
        if subtitles:
            if index >= 0:
                item = self.library.require(self.current["id"])
            self.clear_subtitles()
            # The native renderer loses a cue after seeking into its middle.
            # Read text tracks once and use the position-driven QML overlay.
            self.media.player.setActiveSubtitleTrack(-1)
            if index >= 0:
                self.notice = tr(Msg.LOADING_SUBTITLES)
                self.embedded_subtitles.load(item["path"], index)
        else:
            self.media.player.setActiveAudioTrack(index)
        self.pop_menu()

    def clear_subtitles(self):
        self.embedded_subtitles.clear()
        self.external_cues, self.external_name = [], ""
        if self.error == self.subtitle_error:
            self.error = ""
        self.subtitle_error = ""
        if self.notice == tr(Msg.LOADING_SUBTITLES):
            self.notice = ""

    def subtitles_ready(self):
        try:
            self.library.require(self.current["id"])
        except (OSError, ValueError) as error:
            self.subtitles_failed(str(error))
            return
        if self.notice == tr(Msg.LOADING_SUBTITLES):
            self.notice = ""
        self.publish()

    def subtitles_failed(self, error):
        self.clear_subtitles()
        self.subtitle_error = tr(Msg.SUBTITLE_LOADING_FAILED_ERROR, error=error)
        self.error = self.subtitle_error
        self.publish()

    def chapter_menu(self):
        chapters = self.current.get("metadata", {}).get("chapters", []) if self.current else []
        self.menu(tr(Msg.CHAPTERS), [(c.get("tags", {}).get("title") or time_label(float(c["start_time"])),
                  lambda seconds=float(c["start_time"]): self.jump_chapter(seconds)) for c in chapters])

    def jump_chapter(self, seconds):
        self.media.seek(seconds)
        self.pop_menu()

    def speed_menu(self):
        self.menu(tr(Msg.SPEED), [(f"{rate:g}×", lambda r=rate: self.set_speed(r))
                               for rate in (0.75, 1.0, 1.25, 1.5, 2.0)])

    def set_speed(self, rate):
        self.media.player.setPlaybackRate(rate)
        self.pop_menu()

    def external_subtitles(self):
        if not self.current:
            return
        self.library.require(self.current["id"])
        paths = list(Path(self.current["path"]).parent.glob("*.srt"))
        self.menu(tr(Msg.EXTERNAL_SUBTITLES_SRT), [(p.name, lambda p=p: self.load_subtitles(p)) for p in paths])

    def load_subtitles(self, path):
        self.library.require(self.current["id"])
        if path.stat().st_size > 4 * 1024 * 1024:
            raise ValueError(tr(Msg.SUBTITLE_FILE_EXCEEDS_4_MIB))
        cues = parse_srt(path.read_text(encoding="utf-8-sig"))
        if not cues:
            raise ValueError(tr(Msg.NO_VALID_SRT_CAPTIONS_FOUND))
        self.clear_subtitles()
        self.media.player.setActiveSubtitleTrack(-1)
        self.external_cues, self.external_name = cues, str(path)
        self.pop_menu()

    def subtitle_text(self):
        sink = self.media.player.videoSink()
        if (not self.external_cues and self.media.software and sink
                and self.media.player.activeSubtitleTrack() >= 0):
            return sink.subtitleText()
        position = self.media.player.position() / 1000
        cues = self.external_cues or self.embedded_subtitles.cues or []
        return "\n".join(text for start, end, text in cues if start <= position < end)

    def close(self):
        self.clear_subtitles()
        self.embedded_subtitles.close()
        super().close()
