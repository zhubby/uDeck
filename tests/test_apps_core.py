"""[INPUT]: 依赖临时文件、应用状态和媒体扫描。
[OUTPUT]: 验证库索引、播放队列、音频封面和网页地址契约。
[POS]: 内置应用的核心回归入口。
[PROTOCOL]: Update this header on change, then check AGENTS.md
"""

import json
import shutil
import subprocess
import threading
from pathlib import Path
from urllib.parse import unquote, urlsplit

import pytest
from PySide6.QtGui import QImage

from udeck.apps.browser.controller import address_url
from udeck.apps.common.library import ScanTask, Source, scan
from udeck.apps.common.state import AppState, PlayQueue
from udeck.apps.music.controller import MusicController


def test_atomic_state_preserves_old_file_on_failed_replace(tmp_path, monkeypatch):
    state = AppState("music", tmp_path)
    state.data["positions"]["track"] = 12
    state.save()
    old = state.path.read_bytes()
    state.data["positions"]["track"] = 18
    monkeypatch.setattr("udeck.apps.common.state.os.replace", lambda *args: (_ for _ in ()).throw(OSError("full")))
    with pytest.raises(OSError):
        state.save()
    assert state.path.read_bytes() == old
    assert not list(tmp_path.glob(".*.tmp"))


def test_library_identity_is_per_source_content_and_not_scan_order(tmp_path):
    one, two = tmp_path / "one", tmp_path / "two"
    one.mkdir()
    two.mkdir()
    (one / "same.txt").write_text("Original text")
    (two / "same.txt").write_text("Original text")
    a, b = Source.create(one), Source.create(two)
    first = scan(a, "reader")[0]
    assert first["id"] != scan(b, "reader")[0]["id"]
    (one / "earlier.txt").write_text("Another book")
    assert next(x for x in scan(a, "reader") if x["title"] == "same")["id"] == first["id"]
    (one / "same.txt").write_text("Changed text")
    assert next(x for x in scan(a, "reader") if x["title"] == "same")["id"] != first["id"]


def test_scan_does_not_escape_source_or_follow_symlinks_and_can_cancel(tmp_path):
    root = tmp_path / "card"
    root.mkdir()
    outside = tmp_path / "private.txt"
    outside.write_text("private")
    (root / "link.txt").symlink_to(outside)
    assert scan(Source.create(root), "reader") == []
    (root / "real.txt").write_text("book")
    assert scan(Source.create(root), "reader", cancelled=lambda: True) == []


def test_source_replacement_at_same_path_is_not_the_original_mount(tmp_path):
    root = tmp_path / "card"
    root.mkdir()
    source = Source.create(root)
    root.rename(tmp_path / "old-card")
    root.mkdir()
    assert not source.available()


def test_music_scan_finds_embedded_cover_from_legacy_index(tmp_path, monkeypatch):
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.skip("ffmpeg and ffprobe are required")
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    source_dir = tmp_path / "album"
    source_dir.mkdir()
    track = source_dir / "02.mp3"
    plain = source_dir / "01.mp3"
    for path in (track, plain):
        arguments = ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=0.2"]
        if path == track:
            arguments += ["-f", "lavfi", "-i", "color=c=red:s=96x96", "-map", "0:a", "-map", "1:v",
                          "-c:v", "mjpeg", "-frames:v", "1", "-disposition:v", "attached_pic"]
        subprocess.run([*arguments, "-c:a", "mp3", "-metadata", "album=专辑",
                        "-metadata", "artist=艺人", str(path)], check=True, timeout=8)

    source = Source.create(source_dir)
    previous = scan(source, "music", metadata=True)
    for item in previous:
        item["metadata"].pop("streams", None)
    tasks = []

    def run_scan():
        task = ScanTask(1, source, "music", threading.Event(), {item["path"]: item for item in previous})
        indexed, covers = [], {}
        task.signals.done.connect(lambda _g, _s, items, _e: indexed.extend(items))
        task.signals.covers.connect(lambda _g, _s, batch: covers.update(batch))
        tasks.append(task)
        task.run()
        return indexed, covers

    indexed, covers = run_scan()
    assert [x["id"] for x in indexed] == [x["id"] for x in previous]
    assert set(covers) == {indexed[1]["id"]}
    extracted = Path(unquote(urlsplit(covers[indexed[1]["id"]]).path))
    image = QImage(str(extracted))
    assert extracted.is_relative_to(tmp_path / "cache")
    assert not image.isNull() and image.width() == image.height()
    assert image.pixelColor(0, 0).red() > 200

    sidecar = source_dir / "cover.jpg"
    assert image.save(str(sidecar))
    indexed, covers = run_scan()
    assert {item["cover"] for item in indexed} == {sidecar.as_uri()}
    assert not covers


def test_music_cover_updates_album_and_current_track(qt_application, tmp_path):
    controller = MusicController(tmp_path)
    try:
        source = tmp_path / "album"
        source.mkdir()
        (source / "01.mp3").write_bytes(b"first")
        (source / "02.mp3").write_bytes(b"second")
        first, second = scan(Source.create(source), "music")
        controller.library.items = [first, second]
        controller.current = dict(second)
        cover = (tmp_path / "cover.jpg").as_uri()
        controller.library._covers(0, second["sourceId"], {second["id"]: cover})
        assert controller.rows()[0]["cover"] == cover
        assert controller.current["id"] == second["id"]
        assert controller.current["cover"] == cover
    finally:
        controller.close()


def test_middle_content_edits_change_identity_even_with_same_head_tail_and_size(tmp_path):
    book = tmp_path / "long.txt"
    book.write_bytes(b"a" * 200000)
    first = scan(Source.create(tmp_path), "reader")[0]["id"]
    with book.open("r+b") as stream:
        stream.seek(100000)
        stream.write(b"changed")
    assert scan(Source.create(tmp_path), "reader")[0]["id"] != first


def test_queue_removing_current_does_not_restart_and_retains_next_track():
    queue = PlayQueue()
    queue.replace(["a", "b", "c"], "b")
    queue.remove("b")
    assert queue.current == "b"
    assert queue.advance() == "c"
    assert queue.advance() is None
    assert queue.current is None


def test_queue_insert_and_move_do_not_change_current():
    queue = PlayQueue()
    queue.replace(["a", "b"], "a")
    queue.append(["c"])
    queue.move("c", -1)
    assert queue.items == ["a", "c", "b"]
    assert queue.current == "a"
    assert queue.advance() == "c"


@pytest.mark.parametrize(("text", "expected"), [
    ("example.org/path", "https://example.org/path"),
    ("http://127.0.0.1:8999/a?q=中文", "http://127.0.0.1:8999/a?q=中文"),
    ("hello world", "https://duckduckgo.com/?q=hello+world"),
])
def test_browser_resolves_real_addresses_and_search_terms(text, expected):
    assert address_url(text) == expected


@pytest.mark.parametrize("text", ["javascript:alert(1)", "file:///etc/passwd", "data:text/html,x"])
def test_browser_address_rejects_privileged_schemes(text):
    with pytest.raises(ValueError):
        address_url(text)


def test_corrupt_state_is_recoverable_without_losing_original(tmp_path):
    path = tmp_path / "reader.json"
    path.write_text("{broken")
    state = AppState("reader", tmp_path)
    assert state.error
    assert state.data["positions"] == {}
    assert path.read_text() == "{broken"
    assert Path(state.path) == path
    assert json.loads(json.dumps(state.data))["version"] == 1
