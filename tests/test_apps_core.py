import json
from pathlib import Path

import pytest

from udeck.apps.browser.controller import address_url
from udeck.apps.common.library import Source, scan
from udeck.apps.common.state import AppState, PlayQueue


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
