import hashlib
import importlib
import importlib.util
import json
import struct
import wave
from pathlib import Path

import pytest
from PySide6.QtCore import QCoreApplication, QObject, Signal

from udeck.core import ConfigStore


@pytest.mark.parametrize("value", [None, "false", 0, 1, [], {}])
def test_invalid_sound_preferences_keep_the_quiet_default(tmp_path, value):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"preferences": {"uiSounds": value}}))
    assert ConfigStore(path).data["preferences"].get("uiSounds") is True


def test_sound_preference_survives_another_process_saving_focus(tmp_path):
    path = tmp_path / "settings.json"
    shell, application = ConfigStore(path), ConfigStore(path)
    application.data["preferences"]["uiSounds"] = False
    application.save()
    shell.remember("keep.desktop")
    assert ConfigStore(path).data["preferences"].get("uiSounds") is False
    assert ConfigStore(path).data["recent"] == ["keep.desktop"]


def test_bundled_sounds_are_offline_pcm_with_original_license_and_provenance():
    root = Path(__file__).resolve().parents[1] / "src/udeck/assets/interface-sounds"
    assert (root / "manifest.json").is_file(), "Bundle the selected Kenney sounds"
    manifest = json.loads((root / "manifest.json").read_text())
    assert manifest["archiveSha256"] == "f2193d072726d6758a5f7871b2dcc54dcce0d5c35c6f0a62f92549b327c81232"
    assert b"Creative Commons Zero, CC0" in (root / "License.txt").read_bytes()
    durations = {"tick_001.wav": 0.045, "select_001.wav": 0.0404,
                 "open_001.wav": 0.1478, "back_001.wav": 0.061,
                 "toggle_001.wav": 0.1364, "toggle_002.wav": 0.1364,
                 "confirmation_003.wav": 0.322, "error_008.wav": 0.1393}
    assert set(manifest["files"]) == set(durations)
    for filename, duration in durations.items():
        path = root / filename
        metadata = manifest["files"][filename]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == metadata["sha256"]
        assert metadata["archivePath"] == "Audio/" + filename.replace(".wav", ".ogg")
        assert len(metadata["sourceSha256"]) == 64
        with wave.open(str(path)) as sound:
            assert (sound.getnchannels(), sound.getsampwidth(), sound.getframerate()) == (1, 2, 48000)
            assert sound.getnframes() / sound.getframerate() == pytest.approx(duration, abs=0.002)
            samples = struct.unpack("<" + str(sound.getnframes()) + "h", sound.readframes(sound.getnframes()))
            assert 0 < max(abs(sample) for sample in samples) / 32768 < 0.3


@pytest.fixture
def audio(tmp_path, monkeypatch):
    assert importlib.util.find_spec("udeck.sounds") is not None, "Add semantic UI sound playback"
    module = importlib.import_module("udeck.sounds")
    application = QCoreApplication.instance() or QCoreApplication([])
    played, effects = [], []

    class Window(QObject):
        activeChanged = Signal()
        active = True

        def isActive(self):
            return self.active

    class Device:
        missing = False

        def isNull(self):
            return self.missing

    class Devices(QObject):
        audioOutputsChanged = Signal()
        device = Device()

        @staticmethod
        def defaultAudioOutput():
            return Devices.device

    class Effect(QObject):
        Status = module.QSoundEffect.Status

        def __init__(self, parent=None):
            super().__init__(parent)
            self.playing = False
            self.ready = True
            effects.append(self)

        def setSource(self, source):
            self.source = source

        def setAudioDevice(self, device):
            self.device = device

        def status(self):
            return self.Status.Ready if self.ready else self.Status.Error

        def isPlaying(self):
            return self.playing

        def play(self):
            self.playing = True
            played.append(self.source.fileName())

        def stop(self):
            self.playing = False

    monkeypatch.setattr(module, "QMediaDevices", Devices)
    monkeypatch.setattr(module, "QSoundEffect", Effect)
    clock = [100.0]
    monkeypatch.setattr(module.time, "monotonic", lambda: clock[0])
    window = Window()
    path = tmp_path / "settings.json"
    player = module.InterfaceSounds(path, window)

    class Audio:
        def flush(self):
            application.processEvents()

        def finish(self):
            for effect in effects:
                effect.playing = False

        def enabled(self, value):
            config = ConfigStore(path)
            config.data["preferences"]["uiSounds"] = value
            config.save()

    harness = Audio()
    harness.player, harness.window = player, window
    harness.played, harness.effects = played, effects
    harness.clock, harness.devices = clock, player._devices
    yield harness
    player.close()
    application.processEvents()


def test_one_interaction_plays_only_its_most_specific_sound(audio):
    for event in ("navigate", "accept", "open"):
        audio.player.request(event)
    audio.flush()
    assert audio.played == ["open_001.wav"]
    audio.player.request("accept")
    audio.player.request("error")
    audio.flush()
    assert audio.played == ["open_001.wav", "error_008.wav"]
    assert sum(effect.isPlaying() for effect in audio.effects) == 1


def test_navigation_is_throttled_and_cannot_interrupt_result_feedback(audio):
    audio.player.request("navigate")
    audio.flush()
    audio.finish()
    audio.clock[0] += 0.02
    audio.player.request("navigate")
    audio.flush()
    assert audio.played == ["tick_001.wav"]
    audio.clock[0] += 0.1
    audio.player.request("navigate")
    audio.flush()
    assert audio.played == ["tick_001.wav", "tick_001.wav"]
    audio.player.request("success")
    audio.flush()
    audio.clock[0] += 0.2
    audio.player.request("navigate")
    audio.flush()
    assert audio.played[-1] == "confirmation_003.wav"


def test_disable_and_focus_loss_discard_pending_audio_without_replaying_it(audio):
    audio.player.request("accept")
    audio.enabled(False)
    audio.flush()
    assert audio.played == []
    audio.enabled(True)
    audio.player.request("open")
    audio.window.active = False
    audio.window.activeChanged.emit()
    audio.flush()
    audio.window.active = True
    audio.window.activeChanged.emit()
    audio.flush()
    assert audio.played == []
    audio.player.request("accept")
    audio.flush()
    assert audio.played == ["select_001.wav"]
    audio.window.active = False
    audio.window.activeChanged.emit()
    assert not any(effect.isPlaying() for effect in audio.effects)


def test_device_loss_and_bad_samples_fail_silently(audio):
    audio.player.request("open")
    audio.devices.device.missing = True
    audio.flush()
    assert audio.played == []
    audio.devices.audioOutputsChanged.emit()
    audio.devices.device.missing = False
    audio.devices.audioOutputsChanged.emit()
    audio.player.request("error")
    for effect in audio.effects:
        effect.ready = False
    audio.flush()
    assert audio.played == []


def test_disabled_interface_does_not_create_or_play_audio(audio):
    audio.player.close()
    audio.effects.clear()
    module = importlib.import_module("udeck.sounds")
    player = module.InterfaceSounds(Path("unused-settings.json"), audio.window, silent=True)
    player.request("accept")
    audio.flush()
    assert audio.effects == [] and audio.played == []
    player.close()
