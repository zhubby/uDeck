import os
import pwd
import sys
from types import SimpleNamespace

from udeck.desktop import DesktopCatalog, open_terminal


def test_file_terminal_passes_directory_as_cwd_without_interpolation(tmp_path, monkeypatch):
    directory = tmp_path / '中文 空格 "quote" $literal'
    directory.mkdir()
    calls = []
    monkeypatch.setattr("udeck.desktop.shutil.which", lambda name: "/usr/bin/" + name)
    monkeypatch.setattr("udeck.desktop.subprocess.Popen", lambda *args, **kwargs: calls.append((args, kwargs)))
    open_terminal(directory)
    assert calls == [((["/usr/bin/xdg-terminal-exec", "--dir=" + str(directory)],), {"cwd": str(directory), "start_new_session": True})]


def test_file_terminal_alternative_forces_a_session_even_with_an_existing_window(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr("udeck.desktop.shutil.which", lambda name: "/usr/bin/x-terminal-emulator" if name == "x-terminal-emulator" else None)
    monkeypatch.setattr("udeck.desktop.subprocess.Popen", lambda *args, **kwargs: calls.append((args, kwargs)))
    open_terminal(tmp_path)
    assert calls == [((["/usr/bin/x-terminal-emulator", "-e", pwd.getpwuid(os.getuid()).pw_shell or "/bin/sh"],),
                      {"cwd": str(tmp_path), "start_new_session": True})]


def test_terminal_true_without_gi_uses_xdg_then_alternative(tmp_path, monkeypatch):
    (tmp_path / "example.desktop").write_text('[Desktop Entry]\nType=Application\nName=Example\nTerminal=true\nExec=/bin/echo "中文 空格"\n')
    catalog = DesktopCatalog([tmp_path])
    catalog.entries()
    calls = []
    monkeypatch.setitem(sys.modules, "gi", None)
    monkeypatch.setattr("udeck.desktop.subprocess.Popen", lambda *args, **kwargs: calls.append(args[0]))
    monkeypatch.setattr("udeck.desktop.shutil.which", lambda name: "/usr/bin/" + name)
    catalog.launch("example.desktop")
    assert calls[-1] == ["/usr/bin/xdg-terminal-exec", "--", "/bin/echo", "中文 空格"]
    monkeypatch.setattr("udeck.desktop.shutil.which", lambda name: "/usr/bin/x-terminal-emulator" if name == "x-terminal-emulator" else None)
    catalog.launch("example.desktop")
    assert calls[-1] == ["/usr/bin/x-terminal-emulator", "-e", "/bin/echo", "中文 空格"]


def test_gio_path_retains_distribution_terminal_true_resolution(tmp_path, monkeypatch):
    (tmp_path / "example.desktop").write_text('[Desktop Entry]\nType=Application\nName=Example\nTerminal=true\nExec=/bin/echo\n')
    catalog = DesktopCatalog([tmp_path])
    catalog.entries()
    launches = []
    app = SimpleNamespace(launch=lambda *args: launches.append(args) or True)
    monkeypatch.setitem(sys.modules, "gi", SimpleNamespace(require_version=lambda *args: None))
    monkeypatch.setitem(sys.modules, "gi.repository", SimpleNamespace(Gio=SimpleNamespace(DesktopAppInfo=SimpleNamespace(new_from_filename=lambda path: app))))
    catalog.launch("example.desktop")
    assert launches == [([], None)]
