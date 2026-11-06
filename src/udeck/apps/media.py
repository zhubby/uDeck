"""QtMultimedia playback. UI state comes from observed player properties."""

import hashlib
import os
import re
import time
from pathlib import Path

from PySide6.QtCore import Property, QObject, QUrl, Signal, Slot
from PySide6.QtDBus import QDBusConnection, QDBusInterface, QDBusMessage
from PySide6.QtGui import QImage
from PySide6.QtMultimedia import QAudioOutput, QMediaDevices, QMediaMetaData, QMediaPlayer
from PySide6.QtQuick import QQuickImageProvider

from ..app_routing import APP_IDS, object_path, service_name
from ..i18n import tr
from .controller import AppController
from .state import PlayQueue


class FrameImages(QQuickImageProvider):
    def __init__(self, controller):
        super().__init__(QQuickImageProvider.ImageType.Image)
        self.controller = controller

    def requestImage(self, identifier, size, requested_size):
        image = self.controller.media.frame_image.copy()
        if image.isNull():
            # A queued image request can arrive while the next source is loading.
            image = QImage(1, 1, QImage.Format.Format_ARGB32_Premultiplied)
            image.fill(0)
        size.setWidth(image.width())
        size.setHeight(image.height())
        return image


class MediaEngine(QObject):
    changed = Signal()
    ended = Signal()
    failed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.player = QMediaPlayer(self)
        self.output = QAudioOutput(self)
        self.devices = QMediaDevices(self)
        self.player.setAudioOutput(self.output)
        self.output.setVolume(0.8)
        self.pending_position = None
        self.identifier = ""
        self.loading = False
        self.software = os.environ.get("QT_QUICK_BACKEND") == "software"
        self.frame_image, self.frame_revision = QImage(), 0
        self.last_frame_time = 0
        self.player.mediaStatusChanged.connect(self.status_changed)
        self.player.errorOccurred.connect(lambda code, text: self.failed.emit(text))
        for signal in (self.player.positionChanged, self.player.durationChanged,
                       self.player.playbackStateChanged, self.player.tracksChanged,
                       self.player.activeTracksChanged, self.player.playbackRateChanged,
                       self.output.deviceChanged, self.devices.audioOutputsChanged):
            signal.connect(lambda *args: self.changed.emit())

    def load(self, item, position=0):
        self.frame_image, self.frame_revision, self.last_frame_time = QImage(), 0, 0
        self.player.stop()
        self.identifier, self.loading = item["id"], True
        self.pending_position = max(0, int(position))
        self.player.setSource(QUrl.fromLocalFile(item["path"]))
        self.player.play()
        self.changed.emit()

    def status_changed(self, status):
        if status in (QMediaPlayer.MediaStatus.LoadedMedia, QMediaPlayer.MediaStatus.BufferedMedia):
            self.loading = False
            if self.pending_position is not None:
                self.player.setPosition(self.pending_position)
                self.pending_position = None
        elif status == QMediaPlayer.MediaStatus.InvalidMedia:
            self.loading = False
        elif status == QMediaPlayer.MediaStatus.EndOfMedia:
            self.ended.emit()
        self.changed.emit()

    def snapshot(self):
        return {"position": self.player.position() / 1000, "duration": self.player.duration() / 1000,
                "playing": self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState,
                "loading": self.loading, "rate": self.player.playbackRate(),
                "output": self.output.device().description() or tr("System default"),
                "error": self.player.errorString(), "status": self.player.mediaStatus().name}

    def video_frame(self, frame):
        if not frame.isValid() or time.monotonic() - self.last_frame_time < 1 / 15:
            return
        image = frame.toImage()
        if not image.isNull():
            self.frame_image = image
            self.frame_revision += 1
            self.last_frame_time = time.monotonic()
            self.changed.emit()

    def toggle(self):
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def seek(self, seconds):
        position = max(0, min(self.player.duration(), int(seconds * 1000)))
        self.player.setPosition(position)

    def set_output(self, device_id):
        device = next((d for d in self.devices.audioOutputs() if bytes(d.id()).hex() == device_id), None)
        if device is None:
            raise OSError(tr("Audio output disappeared"))
        self.output.setDevice(device)
        if self.output.device().id() != device.id():
            raise OSError(tr("The audio output could not be changed"))
        self.changed.emit()

    def close(self):
        self.identifier = ""
        self.player.stop()
        self.player.setSource(QUrl())


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

    @Slot(QObject)
    def setVideoSink(self, sink):
        self.media.player.setVideoSink(sink)
        if self.media.software:
            sink.videoFrameChanged.connect(self.media.video_frame)

    @Slot(float)
    def seek(self, seconds):
        self.media.seek(seconds)

    def tabs(self):
        return ([tr("Albums"), tr("Tracks"), tr("Queue"), tr("Folders")] if self.app == "music"
                else [tr("Continue watching"), tr("All videos"), tr("Folders")])

    @staticmethod
    def album_id(item):
        return "album:" + hashlib.sha256((item["album"] + "|" + item["artist"]
                                           + "|" + item["folder"]).encode()).hexdigest()

    def rows(self):
        rows = super().rows()
        if self.app == "music":
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
        elif self.tab == 0:
            return [r for r in rows if self.store.data["positions"].get(r["id"], 0) > 0]
        return rows

    def activate(self, row):
        if row.get("kind") == "album":
            self.enter("album")
            self.album, self.selected = row["id"], ""
        else:
            super().activate(row)

    def open_item(self, identifier):
        item = self.library.require(identifier)
        if self.app == "video":
            position = self.store.data["positions"].get(identifier, 0)
            if position > 0:
                self.menu(tr("Resume video?"), [
                    (tr("Continue from {position}", position=time_label(position)), lambda: self.play(item, position)),
                    (tr("Start from beginning"), lambda: self.play(item))], item["title"], item["sourceId"])
                return
        self.play(item)

    def play(self, item, seconds=0, queued=False, music_confirmed=False):
        item = self.library.require(item["id"])
        if self.app == "music":
            self.paused_by_video = ""
        if self.app == "video" and not music_confirmed and self.music_call("IsPlaying"):
            self.menu(tr("Music is playing"), [
                (tr("Pause music and play video"), lambda: self.play(item, seconds, music_confirmed=True)),
                (tr("Cancel"), self.pop_menu)], item["title"], item["sourceId"])
            return
        if self.app == "video" and music_confirmed:
            import uuid

            token = uuid.uuid4().hex
            if not self.music_call("PauseForVideo", token):
                raise RuntimeError(tr("Music could not be paused. Try again."))
            self.music_token = token
        if self.app == "music" and not queued:
            rows = self.rows()
            ids = [r["id"] for r in rows if r.get("kind") == "item"]
            self.queue.replace(ids or [item["id"]], item["id"])
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
        if (self.app == "video" and self.page == "player" and self.inactive >= 5
                and self.media.snapshot()["playing"] and not self.menus):
            self.controls_visible = False
        if self.inactive % 5 == 0:
            self.attempt(self.persist)
        self.publish()

    def extra_state(self):
        return {"media": self.media.snapshot(), "control": self.controls,
                "controlsVisible": self.controls_visible, "repeat": self.queue.repeat,
                "repeatLabel": {"off": tr("Off"), "all": tr("All tracks"), "one": tr("Current track")}[self.queue.repeat],
                "shuffle": self.queue.shuffle, "album": self.album,
                "subtitleText": self.subtitle_text(), "videoFrameRevision": self.media.frame_revision}

    def back(self):
        if self.page == "player" and self.app == "video":
            self.media.player.pause()
            self.save_position()
            self.persist()
            self.release_music()
        super().back()

    @Slot(str)
    def dispatch(self, action):
        self.inactive = 0
        if self.page == "player" and not self.menus:
            if action in ("left", "right"):
                self.media.seek(self.media.player.position() / 1000 + (-10 if action == "left" else 10))
            elif action in ("up", "down"):
                self.controls = max(0, min(2, self.controls + (-1 if action == "up" else 1)))
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
    def command(self, command):
        if command == "play-pause":
            self.paused_by_video = ""
            self.media.toggle()
        elif command in ("previous", "next"):
            self.attempt(lambda: self.next_track(-1 if command == "previous" else 1))
        elif command == "now-playing" and self.current:
            if self.page != "player":
                self.enter("player")
        elif command == "hide-controls":
            self.controls_visible = False
            self.clear_menus()
        elif command == "seek":
            self.prompt(tr("Position in seconds"), lambda value: self.media.seek(float(value)))
        else:
            super().command(command)
        self.publish()

    def next_track(self, delta=1):
        if self.app == "music":
            identifier = self.queue.advance(delta)
            if identifier:
                self.play(self.library.require(identifier), queued=True)
            else:
                self.media.player.pause()
                self.notice = tr("Queue finished")
        else:
            chapters = self.current.get("metadata", {}).get("chapters", []) if self.current else []
            pos = self.media.player.position() / 1000
            starts = [float(c["start_time"]) for c in chapters]
            target = (next((x for x in starts if x > pos + 1), self.media.player.duration() / 1000)
                      if delta > 0 else next((x for x in reversed(starts) if x < pos - 2), 0))
            self.media.seek(target)

    def end_file(self):
        if self.current:
            self.store.data["positions"][self.current["id"]] = 0
        if self.app == "music":
            self.attempt(self.next_track)
        else:
            self.notice = tr("Playback finished")
            self.release_music()

    def playback_failed(self, text):
        self.error = tr("Playback failed: {error}", error=text)
        self.controls_visible = True
        self.release_music()
        self.publish()

    def output_menu(self):
        options = []
        for device in self.media.devices.audioOutputs():
            key = bytes(device.id()).hex()
            options.append((device.description(), lambda key=key: self.change_output(key)))
        self.menu(tr("Audio output"), options, tr("Current: {output}", output=self.media.snapshot()["output"]))

    def change_output(self, identifier):
        self.media.set_output(identifier)
        self.pop_menu()

    def settings_options(self):
        options = [(tr("Audio output"), self.output_menu)]
        if self.app == "video":
            options.append((tr("Resume music after video: {value}", value=tr("On") if self.store.data["preferences"].get("resumeMusic") else tr("Off")), self.toggle_resume_music))
        return options

    def toggle_resume_music(self):
        preferences = self.store.data["preferences"]
        preferences["resumeMusic"] = not preferences.get("resumeMusic", False)
        self.persist()
        self.pop_menu()

    def context(self):
        if self.app == "video" and self.page == "player":
            self.menu(tr("Playback options"), [
                (tr("Subtitles"), lambda: self.track_menu(True)),
                (tr("External subtitles (SRT)"), self.external_subtitles),
                (tr("Audio tracks"), lambda: self.track_menu(False)),
                (tr("Chapters"), self.chapter_menu),
                (tr("Speed"), self.speed_menu),
                (tr("Go to position"), lambda: self.command("seek")),
                (tr("Hide controls"), lambda: self.command("hide-controls"))])
        elif self.app == "music" and (self.page == "player" or self.tab == 2):
            options = [(tr("Show queue"), lambda: self.queue_view()),
                       (tr("Shuffle: {value}", value=tr("On") if self.queue.shuffle else tr("Off")), self.toggle_shuffle),
                       (tr("Repeat: {value}", value={"off": tr("Off"), "all": tr("All tracks"), "one": tr("Current track")}[self.queue.repeat]), self.toggle_repeat)]
            if self.selected in self.queue.items:
                options += [(tr("Move up"), lambda: self.queue_move()),
                            (tr("Remove from queue"), lambda: self.queue_remove())]
            self.menu(tr("Queue"), options)
        else:
            options = [(tr("Search"), lambda: self.prompt(tr("Search library"), self.search, self.filter)),
                       (tr("Sources"), self.sources_menu), (tr("Refresh library"), self.refresh)]
            if self.app == "music" and self.selected:
                options.insert(0, (tr("Add to queue"), self.enqueue))
            self.menu(tr("Library actions"), options)

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

    def track_menu(self, subtitles):
        player = self.media.player
        tracks = player.subtitleTracks() if subtitles else player.audioTracks()
        options = [(tr("Off"), lambda: self.set_track(True, -1))] if subtitles else []
        for index, metadata in enumerate(tracks):
            title = metadata.stringValue(QMediaMetaData.Key.Title)
            language = metadata.stringValue(QMediaMetaData.Key.Language)
            options.append((title or language or str(index + 1),
                            lambda i=index: self.set_track(subtitles, i)))
        self.menu(tr("Subtitles") if subtitles else tr("Audio tracks"), options)

    def set_track(self, subtitles, index):
        if subtitles:
            self.external_cues, self.external_name = [], ""
            self.media.player.setActiveSubtitleTrack(index)
        else:
            self.media.player.setActiveAudioTrack(index)
        self.pop_menu()

    def chapter_menu(self):
        chapters = self.current.get("metadata", {}).get("chapters", []) if self.current else []
        self.menu(tr("Chapters"), [(c.get("tags", {}).get("title") or time_label(float(c["start_time"])),
                  lambda seconds=float(c["start_time"]): self.jump_chapter(seconds)) for c in chapters])

    def jump_chapter(self, seconds):
        self.media.seek(seconds)
        self.pop_menu()

    def speed_menu(self):
        self.menu(tr("Speed"), [(f"{rate:g}×", lambda r=rate: self.set_speed(r))
                               for rate in (0.75, 1.0, 1.25, 1.5, 2.0)])

    def set_speed(self, rate):
        self.media.player.setPlaybackRate(rate)
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

    @Slot()
    def requestClose(self):
        if self.app == "music" and self.media.snapshot()["playing"]:
            self.menu(tr("Music is playing"), [
                (tr("Continue in background"), self.background),
                (tr("Stop and exit"), self.stop_exit), (tr("Cancel"), self.pop_menu)])
        else:
            super().requestClose()

    def background(self):
        self.clear_menus()
        if self.window:
            self.window.hide()

    def stop_exit(self):
        self.save_position()
        self.attempt(self.persist)
        self.media.close()
        super().requestClose()

    def close(self):
        self.save_position()
        super().close()
        self.media.close()
        self.release_music()

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
        self.menu(tr("External subtitles (SRT)"), [(p.name, lambda p=p: self.load_subtitles(p)) for p in paths])

    def load_subtitles(self, path):
        self.library.require(self.current["id"])
        if path.stat().st_size > 4 * 1024 * 1024:
            raise ValueError(tr("Subtitle file exceeds 4 MiB"))
        text = path.read_text(encoding="utf-8-sig")
        cues = []
        pattern = r"(?m)(\d\d):(\d\d):(\d\d)[,.](\d\d\d)\s*-->\s*(\d\d):(\d\d):(\d\d)[,.](\d\d\d)[^\n]*\n([\s\S]*?)(?=\n\s*\n|\Z)"
        def seconds(a):
            return a[0] * 3600 + a[1] * 60 + a[2] + a[3] / 1000
        for match in re.finditer(pattern, text):
            values = [int(v) for v in match.groups()[:8]]
            cues.append((seconds(values[:4]), seconds(values[4:]), re.sub(r"<[^>]+>", "", match.group(9)).strip()))
        if not cues:
            raise ValueError(tr("No valid SRT captions found"))
        self.media.player.setActiveSubtitleTrack(-1)
        self.external_cues, self.external_name = cues, str(path)
        self.pop_menu()

    def subtitle_text(self):
        position = self.media.player.position() / 1000
        return "\n".join(text for start, end, text in self.external_cues if start <= position < end)


def time_label(seconds):
    seconds = max(0, int(seconds))
    return f"{seconds // 60:02d}:{seconds % 60:02d}"
