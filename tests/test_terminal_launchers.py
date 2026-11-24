"""
[INPUT]: 依赖应用目录、固定模块启动入口与进程替身。
[OUTPUT]: 验证终端和应用启动不读取系统默认程序或桌面 Exec。
[POS]: 全局应用启动边界回归；替身阻止真实进程启动。
[PROTOCOL]: Update this header on change, then check AGENTS.md
"""

import sys
from types import SimpleNamespace

import pytest

from udeck.app_routing import NATIVE_APPS, native_app_id
from udeck.desktop import DesktopCatalog, open_terminal


@pytest.mark.parametrize("identifier", sorted(NATIVE_APPS))
def test_native_identity_accepts_only_fixed_ids(identifier):
    assert native_app_id(identifier) == identifier
    assert native_app_id(identifier + ".desktop") == identifier
    assert native_app_id(identifier + ".desktop.desktop") is None
    assert native_app_id(identifier.lower()) is None


@pytest.mark.parametrize("identifier", [None, "", "xarchiver.desktop", "org.example.Reader", "io.github.zhubby.uDeck"])
def test_external_identity_is_rejected(identifier):
    assert native_app_id(identifier) is None


def test_file_terminal_passes_directory_to_fixed_native_module(tmp_path, monkeypatch):
    directory = tmp_path / '中文 空格 "quote" $literal'
    directory.mkdir()
    calls = []
    monkeypatch.setattr("udeck.desktop.subprocess.Popen", lambda *args, **kwargs: calls.append((args, kwargs)))
    open_terminal(directory)
    assert calls == [(([sys.executable, "-m", "udeck.terminal.main", "--working-directory", str(directory)],),
                      {"cwd": str(directory), "start_new_session": True})]


def test_terminal_rejects_missing_directory(tmp_path):
    with pytest.raises(ValueError):
        open_terminal(tmp_path / "missing")


@pytest.mark.parametrize("name,module,arguments", [
    ("Reader", "udeck.apps.main", ["reader"]),
    ("Terminal", "udeck.terminal.main", []),
])
def test_native_desktop_override_cannot_replace_command(tmp_path, monkeypatch, name, module, arguments):
    identifier = "io.github.zhubby.uDeck." + name + ".desktop"
    (tmp_path / identifier).write_text("[Desktop Entry]\nType=Application\nName=Hijacked\nTerminal=true\nExec=xarchiver\nPath=/tmp\n")
    catalog = DesktopCatalog([tmp_path])
    catalog.entries()
    calls = []
    monkeypatch.setattr("udeck.desktop.subprocess.Popen", lambda *args, **kwargs: calls.append((args, kwargs)))
    catalog.launch(identifier)
    assert calls == [(([sys.executable, "-m", module, *arguments],), {"start_new_session": True})]


def test_external_desktop_entry_cannot_launch(tmp_path, monkeypatch):
    (tmp_path / "example.desktop").write_text("[Desktop Entry]\nType=Application\nName=Example\nExec=xarchiver\n")
    catalog = DesktopCatalog([tmp_path])
    catalog.entries()
    monkeypatch.setattr("udeck.desktop.subprocess.Popen", lambda *_args, **_kwargs: pytest.fail("External process started"))
    with pytest.raises(ValueError):
        catalog.launch("example.desktop")


def test_native_file_arguments_are_absolute_and_cannot_become_terminal_commands(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    calls = []
    monkeypatch.setattr("udeck.desktop.subprocess.Popen", lambda args, **_kwargs: calls.append(args))
    catalog = DesktopCatalog([tmp_path])
    catalog.launch("io.github.zhubby.uDeck.Video.desktop", ["--help.mp4", "中文 $literal.mp4"])
    assert calls == [[sys.executable, "-m", "udeck.apps.main", "video", str(tmp_path / "--help.mp4"), str(tmp_path / "中文 $literal.mp4")]]
    with pytest.raises(ValueError):
        catalog.launch("io.github.zhubby.uDeck.Terminal.desktop", ["--command=external"])


@pytest.mark.parametrize("connected,registered", [(False, False), (True, False), (True, True)])
def test_terminal_home_requires_udeck_shell_and_never_minimizes_to_other_apps(monkeypatch, connected, registered):
    from udeck.terminal import runtime

    calls, errors = [], []
    bus = SimpleNamespace(isConnected=lambda: connected,
                          interface=lambda: SimpleNamespace(isServiceRegistered=lambda _name: SimpleNamespace(value=lambda: registered)),
                          asyncCall=lambda message: calls.append(message.member()))
    monkeypatch.setattr(runtime, "QDBusConnection", SimpleNamespace(sessionBus=lambda: bus))
    window = SimpleNamespace(showMinimized=lambda: pytest.fail("Terminal exposed arbitrary desktop windows"))
    coordinator = SimpleNamespace(windows=[{"window": window, "controller": SimpleNamespace(showError=errors.append)}])
    assert runtime.Coordinator.desktop_action(coordinator, "Home", window) is (connected and registered)
    assert calls == (["Home"] if connected and registered else [])
    assert bool(errors) is not (connected and registered)
