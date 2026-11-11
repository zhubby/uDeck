"""Video resume, chapters, subtitles and music coordination."""

import re
import uuid
from pathlib import Path

from PySide6.QtCore import QObject, Slot
from PySide6.QtDBus import QDBusConnection, QDBusInterface, QDBusMessage
from PySide6.QtMultimedia import QMediaMetaData

from udeck.app_routing import APP_IDS, object_path, service_name
from udeck.apps.media.controller import MediaController, time_label
from udeck.i18n import Msg, tr


class VideoController(MediaController):
    def __init__(self, directory=None, language_path=None):
        super().__init__("video", directory, language_path)

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

    def prepare_play(self, item, seconds, queued, music_confirmed):
        if not music_confirmed and self.music_call("IsPlaying"):
            self.menu(tr(Msg.MUSIC_IS_PLAYING), [
                (tr(Msg.PAUSE_MUSIC_AND_PLAY_VIDEO), lambda: self.play(item, seconds, music_confirmed=True)),
                (tr(Msg.CANCEL), self.pop_menu)], item["title"], item["sourceId"])
            return False
        if music_confirmed:
            token = uuid.uuid4().hex
            if not self.music_call("PauseForVideo", token):
                raise RuntimeError(tr(Msg.MUSIC_COULD_NOT_BE_PAUSED_TRY_AGAIN))
            self.music_token = token
        return True

    def update_controls(self):
        if (self.page == "player" and self.inactive >= 5
                and self.media.snapshot()["playing"] and not self.menus):
            self.controls_visible = False

    def next_track(self, delta=1):
        chapters = self.current.get("metadata", {}).get("chapters", []) if self.current else []
        pos = self.media.player.position() / 1000
        starts = [float(c["start_time"]) for c in chapters]
        target = (next((x for x in starts if x > pos + 1), self.media.player.duration() / 1000)
                  if delta > 0 else next((x for x in reversed(starts) if x < pos - 2), 0))
        self.media.seek(target)

    def finished_playback(self):
        self.notice = tr(Msg.PLAYBACK_FINISHED)
        self.release_music()

    def settings_options(self):
        return [*super().settings_options(),
                (tr(Msg.RESUME_MUSIC_AFTER_VIDEO_VALUE, value=tr(Msg.ON) if self.store.data["preferences"].get("resumeMusic") else tr(Msg.OFF)), self.toggle_resume_music, "", "media-playlist-repeat")]

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
            self.release_music()
        super().back()

    def toggle_resume_music(self):
        preferences = self.store.data["preferences"]
        preferences["resumeMusic"] = not preferences.get("resumeMusic", False)
        self.persist()
        self.pop_menu()

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
            self.external_cues, self.external_name = [], ""
            self.media.player.setActiveSubtitleTrack(index)
        else:
            self.media.player.setActiveAudioTrack(index)
        self.pop_menu()

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

    def music_call(self, method, *args):
        if self.isolated:
            return False
        identifier = APP_IDS["music"]
        remote = QDBusInterface(service_name(identifier), object_path(identifier), identifier + ".Control", QDBusConnection.sessionBus())
        if not remote.isValid():
            return False
        reply = remote.call(method, *args)
        return reply.arguments()[0] if reply.type() != QDBusMessage.MessageType.ErrorMessage and reply.arguments() else False

    def release_music(self):
        if self.music_token:
            self.music_call("ResumeAfterVideo" if self.store.data["preferences"].get("resumeMusic") else "ReleaseVideo", self.music_token)
            self.music_token = ""

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
        text = path.read_text(encoding="utf-8-sig")
        cues = []
        pattern = r"(?m)(\d\d):(\d\d):(\d\d)[,.](\d\d\d)\s*-->\s*(\d\d):(\d\d):(\d\d)[,.](\d\d\d)[^\n]*\n([\s\S]*?)(?=\n\s*\n|\Z)"
        def seconds(a):
            return a[0] * 3600 + a[1] * 60 + a[2] + a[3] / 1000
        for match in re.finditer(pattern, text):
            values = [int(v) for v in match.groups()[:8]]
            cues.append((seconds(values[:4]), seconds(values[4:]), re.sub(r"<[^>]+>", "", match.group(9)).strip()))
        if not cues:
            raise ValueError(tr(Msg.NO_VALID_SRT_CAPTIONS_FOUND))
        self.media.player.setActiveSubtitleTrack(-1)
        self.external_cues, self.external_name = cues, str(path)
        self.pop_menu()

    def subtitle_text(self):
        sink = self.media.player.videoSink()
        if (not self.external_cues and self.media.software and sink
                and self.media.player.activeSubtitleTrack() >= 0):
            return sink.subtitleText()
        position = self.media.player.position() / 1000
        return "\n".join(text for start, end, text in self.external_cues if start <= position < end)
