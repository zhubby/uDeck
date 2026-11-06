import json
import os
import sys

import pytest

from udeck.terminal.core import (
    LaunchRequest,
    TerminalPreferences,
    parse_launch,
    paste_needs_confirmation,
)


def test_terminal_launch_preserves_argv_cwd_and_environment(tmp_path):
    directory = tmp_path / "中文 目录"
    directory.mkdir()
    arguments = [sys.executable, "-c", "print('hello')", "空 格", "$(literal)", 'a"b']
    request, options = parse_launch(["--working-directory", str(directory), "-T", "终端", "-e", *arguments],
                                    environment={"PATH": os.defpath, "TOKEN": "in-memory"})
    assert request.cwd == str(directory)
    assert request.argv == arguments
    assert request.title == "终端"
    assert request.environment["TOKEN"] == "in-memory"
    assert request.new_window is True
    assert options.mock is False


def test_terminal_double_dash_does_not_parse_program_flags(tmp_path):
    request, _ = parse_launch(["--", "/bin/echo", "--new-window", "-T", "字"], cwd=tmp_path)
    assert request.argv == ["/bin/echo", "--new-window", "-T", "字"]
    assert request.new_window


def test_plain_launch_activates_existing_window_and_inherits_cwd(tmp_path):
    request, _ = parse_launch([], cwd=tmp_path, environment={"PATH": os.defpath})
    assert request.cwd == str(tmp_path)
    assert request.argv == []
    assert request.new_window is False


def test_relative_path_entries_use_callers_working_directory(tmp_path, monkeypatch):
    directory = tmp_path / "中文 bin"
    directory.mkdir()
    executable = directory / "probe"
    executable.write_text("#!/bin/sh\nexit 0\n")
    executable.chmod(0o755)
    monkeypatch.chdir(tmp_path.parent)
    request = LaunchRequest(str(tmp_path), ["probe", "a b"], "", {"PATH": "中文 bin"})
    assert request.executable() == (str(executable), ["a b"])


@pytest.mark.parametrize("arguments", [["-e"], ["--"], ["--working-directory", "/not/a/real/directory"]])
def test_invalid_terminal_launch_is_rejected(arguments):
    with pytest.raises((ValueError, SystemExit)):
        parse_launch(arguments)


def test_launch_serialization_validates_data_without_splitting_arguments(tmp_path):
    request = LaunchRequest(str(tmp_path), ["/bin/echo", "two words"], "title", {"PATH": os.defpath}, True)
    assert LaunchRequest.from_json(request.to_json()) == request
    payload = json.loads(request.to_json())
    payload["argv"] = "echo unsafe"
    with pytest.raises(ValueError):
        LaunchRequest.from_json(json.dumps(payload))
    payload["argv"] = ["/bin/echo", "bad\x00argument"]
    with pytest.raises(ValueError):
        LaunchRequest.from_json(json.dumps(payload))


def test_preferences_are_private_atomic_bounded_and_never_save_terminal_contents(tmp_path):
    path = tmp_path / "config" / "terminal.json"
    preferences = TerminalPreferences(path)
    assert preferences.font_size == 20
    preferences.change_font(100)
    assert preferences.font_size == 28
    preferences.change_font(-100)
    assert preferences.font_size == 14
    preferences.change_font(2)
    preferences.save()
    assert TerminalPreferences(path).font_size == 16
    assert path.stat().st_mode & 0o777 == 0o600
    assert set(json.loads(path.read_text())) == {"version", "fontSize", "colorScheme"}
    path.write_text('{"fontSize": "broken", "transcript": "secret"}')
    assert TerminalPreferences(path).font_size == 20


@pytest.mark.parametrize(("text", "expected"), [("中文 command", False), ("one\ntwo", True),
                                               ("cmd\r", True), ("\x1b[31m", True), ("a\x00b", True)])
def test_multiline_and_control_character_pastes_require_confirmation(text, expected):
    assert paste_needs_confirmation(text) is expected
