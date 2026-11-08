import fnmatch
import hashlib
import json
import os
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FONTS = ROOT / "src/udeck/terminal/fonts"
MANIFEST = json.loads((FONTS / "manifest.json").read_text())


@pytest.mark.parametrize("name", sorted(MANIFEST["files"]))
def test_terminal_fonts_match_the_original_upstream_assets(name):
    manifest = json.loads((FONTS / "manifest.json").read_text())
    data = (FONTS / name).read_bytes()
    assert len(data) == manifest["files"][name]["bytes"]
    assert hashlib.sha256(data).hexdigest() == manifest["files"][name]["sha256"]
    if name.endswith("-OFL.txt"):
        assert b"SIL OPEN FONT LICENSE Version 1.1" in data


def test_terminal_fonts_and_license_are_included_in_wheel_package_data():
    configuration = tomllib.loads((ROOT / "pyproject.toml").read_text())
    patterns = configuration["tool"]["setuptools"]["package-data"]["udeck.terminal"]
    for name in (*MANIFEST["files"], "manifest.json"):
        assert any(fnmatch.fnmatch("fonts/" + name, pattern) for pattern in patterns), name


def test_nerd_symbols_are_pinned_and_keep_all_icon_set_notices():
    assert MANIFEST["fallback"] == "Symbols Nerd Font Mono"
    assert MANIFEST["versions"]["Symbols Nerd Font Mono"] == "3.5.1"
    assert "CC-BY-4.0" in MANIFEST["licenses"]["Symbols Nerd Font Mono"]
    for name in ("LICENSE", "NOTICE", "Codicons-LICENSE", "Devicons-LICENSE", "Extraglyphs-LICENSE",
                 "FontAwesome-LICENSE", "FontAwesomeExtension-LICENSE", "FontLogos-LICENSE",
                 "MaterialDesign-LICENSE", "Octicons-LICENSE", "Seti-LICENSE", "Pomicons-LICENSE",
                 "PowerlineExtra-LICENSE", "PowerlineSymbols-LICENSE", "IECPowerSymbols-LICENSE",
                 "WeatherIcons-NOTICE", "Apache-2.0"):
        assert f"NerdFontsSymbolsOnly-{name}.txt" in MANIFEST["files"]
    assert all(metadata["license"] for metadata in MANIFEST["files"].values())


@pytest.mark.parametrize("language,family", [("zh_CN", "LXGW WenKai Mono"), ("en", "JetBrains Mono")])
def test_terminal_fonts_follow_language_and_preserve_font_size_controls(tmp_path, language, family):
    result = subprocess.run(
        [sys.executable, str(ROOT / "tests/terminal_font_probe.py"), str(tmp_path / "terminal.png"), language],
        cwd=ROOT, env={**os.environ, "PYTHONPATH": str(ROOT / "src"), "QT_QPA_PLATFORM": "offscreen",
                       "QT_QUICK_BACKEND": "software", "QT_QUICK_CONTROLS_STYLE": "Basic"},
        capture_output=True, text=True, timeout=20,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout.strip().splitlines()[-1])
    assert report["fontFamily"] == report["resolvedFamily"] == family
    if language == "en":
        assert report["boldStyle"] == "Bold"
    assert report["languageSwitches"] == (["en", "zh_CN"] if language == "zh_CN" else ["zh_CN", "en"])
    assert report["sessionPreserved"]
    assert report["fontSizes"] == [20, 14, 28, 20]
    assert report["qmlErrors"] == []
    assert (tmp_path / "terminal.png").stat().st_size > 10000
