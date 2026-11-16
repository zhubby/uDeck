"""
[INPUT]: 依赖 QML 缓存目录选择与隔离源码夹具。
[OUTPUT]: 验证相同时间戳的源码更新会切换缓存目录。
[POS]: 启动缓存回归，覆盖共享 QML 与 Python 接口更新。
[PROTOCOL]: Update this header on change, then check AGENTS.md
"""

import os

import pytest

from udeck.qml_cache import configure_qml_cache


@pytest.fixture
def source(tmp_path, monkeypatch):
    monkeypatch.delenv("QML_DISK_CACHE_PATH", raising=False)
    monkeypatch.delenv("QML_DISABLE_DISK_CACHE", raising=False)
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    root = tmp_path / "udeck"
    (root / "qml").mkdir(parents=True)
    (root / "qml/Main.qml").write_text("Item { x: 1 }")
    (root / "controller.py").write_text("API = 1")
    return root


@pytest.mark.parametrize("name", ["qml/Main.qml", "controller.py"])
def test_same_size_and_timestamp_source_update_changes_cache(source, monkeypatch, name):
    configure_qml_cache(source)
    previous = os.environ["QML_DISK_CACHE_PATH"]
    path = source / name
    stamp = path.stat()
    path.write_text(path.read_text().replace("1", "2"))
    os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
    monkeypatch.delenv("QML_DISK_CACHE_PATH")
    configure_qml_cache(source)
    assert os.environ["QML_DISK_CACHE_PATH"] != previous


def test_unchanged_source_reuses_cache_despite_data_files(source, monkeypatch):
    configure_qml_cache(source)
    previous = os.environ["QML_DISK_CACHE_PATH"]
    (source / "cover.png").write_bytes(b"image")
    monkeypatch.delenv("QML_DISK_CACHE_PATH")
    configure_qml_cache(source)
    assert os.environ["QML_DISK_CACHE_PATH"] == previous


def test_explicit_cache_directory_is_preserved(source, monkeypatch):
    monkeypatch.setenv("QML_DISK_CACHE_PATH", "/custom/cache")
    configure_qml_cache(source)
    assert os.environ["QML_DISK_CACHE_PATH"] == "/custom/cache"


def test_disabled_disk_cache_needs_no_source_scan(source, monkeypatch):
    monkeypatch.setenv("QML_DISABLE_DISK_CACHE", "1")
    configure_qml_cache(source / "missing")
    assert "QML_DISK_CACHE_PATH" not in os.environ
