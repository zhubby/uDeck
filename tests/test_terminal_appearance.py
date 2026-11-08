import configparser
import json
import os
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_wheel_includes_both_native_palette_templates():
    configuration = tomllib.loads((ROOT / "pyproject.toml").read_text())
    assert set(configuration["tool"]["setuptools"]["data-files"]["share/udeck-terminal/color-schemes"]) == {
        "packaging/terminal.colorscheme", "packaging/terminal-dark.colorscheme",
    }


@pytest.mark.parametrize("theme,filename,background,foreground", [
    ("classic", "terminal.colorscheme", "#151719", "#f1eee7"),
    ("dark", "terminal-dark.colorscheme", "#0b0e12", "#f5f2eb"),
])
def test_native_terminal_palette_matches_system_theme(theme, filename, background, foreground):
    palette = configparser.ConfigParser()
    assert palette.read(ROOT / "packaging" / filename)

    def color(section):
        return "#" + "".join(f"{int(channel):02x}" for channel in palette[section]["Color"].split(","))

    assert color("Background") == background
    assert color("Foreground") == foreground
    assert color("ForegroundIntense") == "#fffcf5"
    expected = [
        ("#14191f", "#717d8a"), ("#e9858a", "#ffadb0"),
        ("#a3c999", "#c2e2b8"), ("#edb866", "#ffd38e"),
        ("#91b9e2", "#b4d4f5"), ("#c1a1de", "#dcc0f4"),
        ("#8fcfc6", "#b5e8e0"), ("#d1d6de", "#f5f2eb"),
    ] if theme == "dark" else [
        ("#202426", "#6c7478"), ("#de6c6e", "#f49092"),
        ("#8fbb8e", "#aed7aa"), ("#edb866", "#ffd38e"),
        ("#7da7cf", "#a1c9f0"), ("#b694cb", "#d7b6eb"),
        ("#7fbfb8", "#a1ded6"), ("#cccfca", "#f1eee7"),
    ]
    assert [(color(f"Color{index}"), color(f"Color{index}Intense")) for index in range(8)] == expected


@pytest.mark.parametrize("language", ["en", "zh_CN"])
@pytest.mark.parametrize("theme", ["classic", "dark"])
def test_terminal_appearance_and_nerd_glyphs_follow_system_settings(tmp_path, language, theme):
    result = subprocess.run(
        [sys.executable, str(ROOT / "tests/terminal_appearance_probe.py"), str(tmp_path), language, theme],
        cwd=ROOT, env={**os.environ, "PYTHONPATH": str(ROOT / "src"), "QT_QPA_PLATFORM": "offscreen",
                       "QT_QUICK_BACKEND": "software", "QT_QUICK_CONTROLS_STYLE": "Basic"},
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout.strip().splitlines()[-1])
    assert report["qmlErrors"] == []
    assert report["theme"] == theme and report["language"] == language
    assert report["windows"] == 2 and report["sessions"] == 3
    assert report["sessionsPreserved"] and report["focusPreserved"]
    assert report["nerdCodepoints"] == [0xE0B0, 0xF07C, 0xF120, 0xF0001]
    assert (tmp_path / f"terminal-{theme}-{language}.png").stat().st_size > 10000


@pytest.mark.parametrize("scheme", ["udeck", "udeck-dark"])
def test_debian_package_refuses_missing_or_stale_native_palettes(tmp_path, scheme):
    commands = tmp_path / "bin"
    commands.mkdir()
    tool = commands / "dpkg-deb"
    tool.write_text("#!/bin/sh\nexit 0\n")
    tool.chmod(0o755)
    plugin = tmp_path / "QMLTermWidget"
    (plugin / "color-schemes").mkdir(parents=True)
    (plugin / "libqmltermwidget.so").write_bytes(b"\x7fELF")
    for name, source in (("udeck", "terminal.colorscheme"), ("udeck-dark", "terminal-dark.colorscheme")):
        if name != scheme:
            (plugin / "color-schemes" / (name + ".colorscheme")).write_bytes((ROOT / "packaging" / source).read_bytes())
    for content in (None, b"stale palette"):
        if content is not None:
            (plugin / "color-schemes" / (scheme + ".colorscheme")).write_bytes(content)
        result = subprocess.run(
            [sys.executable, str(ROOT / "tools/build-terminal-deb"), "--plugin", str(plugin)],
            env={**os.environ, "PATH": str(commands) + os.pathsep + os.environ["PATH"]},
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode != 0
        assert "Rebuild the native plugin" in result.stderr, result.stdout + result.stderr
