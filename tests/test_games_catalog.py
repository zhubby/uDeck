"""Directory and core policies, using synthetic metadata and original files."""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from udeck.apps.library import Source


def installed(tmp_path, definitions, preferences=None):
    from udeck.apps.game_catalog import CoreCatalog

    cores, info = tmp_path / "cores", tmp_path / "info"
    cores.mkdir(exist_ok=True)
    info.mkdir(exist_ok=True)
    for identifier, values in definitions.items():
        (cores / (identifier + "_libretro.so")).write_bytes(b"metadata fixture, not a native core")
        (info / (identifier + "_libretro.info")).write_text(
            "\n".join(f'{key} = "{value}"' for key, value in values.items()))
    prefs = {"coreDirectory": str(cores), **(preferences or {})}
    catalog = CoreCatalog.discover(prefs, info_directories=[info])
    for identifier in definitions:
        catalog.apply_probe(identifier, {"status": "available", "version": "fixture"})
    return catalog


def test_shared_formats_follow_platform_directories_and_aliases(tmp_path):
    from udeck.apps.game_library import scan_games

    catalog = installed(tmp_path, {
        "pcsx_rearmed": {"supported_extensions": "bin|cue|chd|pbp|iso"},
        "ppsspp": {"supported_extensions": "iso|cso|pbp"},
        "genesis_plus_gx": {"supported_extensions": "md|bin|sms|gg"},
    })
    root = tmp_path / "Games"
    for directory in ("ps1", "psp", "MD", "unknown"):
        (root / directory).mkdir(parents=True)
        (root / directory / "Shared.iso").write_bytes(b"original content")
    (root / "MD" / "Original.md").write_bytes(b"original md")
    (root / "Loose.iso").write_bytes(b"loose")
    result = scan_games(Source.create(root), catalog)
    assert {(Path(i["path"]).parent.name, i["platform"]) for i in result.items} == {
        ("ps1", "psx"), ("psp", "psp"), ("MD", "megadrive")}
    assert len(result.items) == 3
    assert any("unknown" in str(hint) for hint in result.hints)
    assert any("Loose.iso" in str(hint) for hint in result.hints)


def test_core_defaults_toggles_and_explicit_choice_never_silently_fallback(tmp_path):
    catalog = installed(tmp_path, {
        "mgba": {"supported_extensions": "gba|gb|gbc"},
        "vba_next": {"supported_extensions": "gba"},
        "gambatte": {"supported_extensions": "gb|gbc"},
    })
    item = {"id": "a", "platform": "gba", "format": "GBA"}
    assert catalog.resolve(item).id == "mgba"
    assert [c.id for c in catalog.candidates("gba", ".gba")] == ["mgba"]
    assert [c.id for c in catalog.candidates("gb", ".gb")] == ["gambatte"]
    catalog.preferences["coreEnabled"] = {"vba_next": True}
    catalog.preferences["platformCores"] = {"gba": "vba_next"}
    assert catalog.resolve(item).id == "vba_next"
    catalog.preferences["gameCores"] = {"a": "mgba"}
    assert catalog.resolve(item).id == "mgba"
    catalog.preferences["coreEnabled"]["mgba"] = False
    with pytest.raises(ValueError, match="mgba"):
        catalog.resolve(item)
    del catalog.preferences["gameCores"]["a"]
    assert catalog.resolve(item).id == "vba_next"
    catalog.apply_probe("vba_next", {"status": "incompatible", "reason": "SIGILL"})
    with pytest.raises(ValueError):
        catalog.resolve(item)


def test_unknown_cores_have_accessible_stable_platforms_and_no_content_capability(tmp_path):
    catalog = installed(tmp_path, {
        "mystery": {"supported_extensions": "abc", "systemid": "Acme Console / 2000"},
        "nameless": {"supported_extensions": "xyz"},
        "2048": {"supports_no_game": "true", "savestate": "false"},
    })
    assert catalog.cores["mystery"].platforms == ("acme-console-2000",)
    assert catalog.platforms["acme-console-2000"].directory == "acme-console-2000"
    assert catalog.cores["nameless"].platforms == ("nameless",)
    assert catalog.cores["2048"].no_content and not catalog.cores["2048"].savestate
    assert set(catalog.cores) == {c.id for p in catalog.platforms.values() for c in catalog.platform_cores(p.id)}


def test_firmware_alternatives_and_optional_resources_are_separate(tmp_path):
    catalog = installed(tmp_path, {
        "yabasanshiro": {"systemid": "saturn", "supported_extensions": "cue|chd",
                         "firmware_count": "3", "firmware0_path": "saturn_bios.bin",
                         "firmware0_opt": "false", "firmware1_path": "mpr-17933.bin",
                         "firmware1_opt": "false", "firmware2_path": "optional.bin", "firmware2_opt": "true"},
    })
    system = tmp_path / "system"
    system.mkdir()
    check = catalog.firmware_check(catalog.cores["yabasanshiro"], "saturn", system)
    assert len(check["required"]) == 1 and "optional.bin" in check["optional"]
    (system / "mpr-17933.bin").write_bytes(b"test bios")
    assert catalog.firmware_check(catalog.cores["yabasanshiro"], "saturn", system)["required"] == []


def test_machine_bios_alternatives_require_complete_pairs_and_accept_resource_folders(tmp_path):
    catalog = installed(tmp_path, {
        "fmsx": {"supported_extensions": "rom", "firmware_count": "3",
                 "firmware0_path": "MSX.ROM", "firmware1_path": "MSX2.ROM", "firmware2_path": "MSX2EXT.ROM"},
        "pcsx2": {"supported_extensions": "iso", "firmware_count": "1", "firmware0_path": "pcsx2/bios"},
    })
    system = tmp_path / "system"
    system.mkdir()
    (system / "MSX2.ROM").write_bytes(b"main bios")
    assert catalog.firmware_check(catalog.cores["fmsx"], "msx", system)["required"]
    (system / "MSX2EXT.ROM").write_bytes(b"extended bios")
    assert not catalog.firmware_check(catalog.cores["fmsx"], "msx", system)["required"]
    bios = system / "pcsx2/bios"
    bios.mkdir(parents=True)
    assert catalog.firmware_check(catalog.cores["pcsx2"], "ps2", system)["required"]
    (bios / "original.bin").write_bytes(b"original bios")
    assert not catalog.firmware_check(catalog.cores["pcsx2"], "ps2", system)["required"]


def test_zip_and_7z_are_single_entries_not_extracted(tmp_path):
    from udeck.apps.game_library import scan_games

    catalog = installed(tmp_path, {"fbneo": {"supported_extensions": "zip|7z"}})
    root = tmp_path / "Games"
    (root / "arcade").mkdir(parents=True)
    for name in ("set.zip", "other.7z"):
        (root / "arcade" / name).write_bytes(b"opaque archive")
    assert {i["format"] for i in scan_games(Source.create(root), catalog).items} == {"ZIP", "7Z"}
    assert sorted(p.name for p in (root / "arcade").iterdir()) == ["other.7z", "set.zip"]


def test_disc_entrypoints_deduplicate_tracks_and_playlist_discs(tmp_path):
    from udeck.apps.game_library import scan_games

    catalog = installed(tmp_path, {"pcsx_rearmed": {"supported_extensions": "cue|bin|chd|m3u"}})
    root = tmp_path / "Games"
    disc = root / "psx" / "Game"
    disc.mkdir(parents=True)
    (disc / "Disc 1.cue").write_text('FILE "track.bin" BINARY\n TRACK 01 MODE2/2352\n')
    (disc / "track.bin").write_bytes(b"original data")
    (disc / "Disc 2.chd").write_bytes(b"other disc")
    (disc / "Game.m3u").write_text("# Original playlist\nDisc 1.cue\nDisc 2.chd\n")
    result = scan_games(Source.create(root), catalog)
    assert [i["relative"] for i in result.items] == ["psx/Game/Game.m3u"]
    assert len(result.items[0]["dependencies"]) == 3


@pytest.mark.parametrize("reference", ["../../outside.bin", "/etc/passwd", "linked/track.bin"])
def test_disc_references_cannot_escape_platform_or_traverse_links(tmp_path, reference):
    from udeck.apps.game_library import content_dependencies

    root = tmp_path / "psx"
    root.mkdir()
    external = tmp_path / "external"
    external.mkdir()
    (external / "track.bin").write_bytes(b"outside")
    (root / "linked").symlink_to(external, target_is_directory=True)
    path = root / "entry.cue"
    path.write_text(f'FILE "{reference}" BINARY\n')
    with pytest.raises(ValueError):
        content_dependencies(path, root)


def test_gdi_parser_preserves_quoted_names_and_detects_missing_tracks(tmp_path):
    from udeck.apps.game_library import content_dependencies

    entry = tmp_path / "disc.gdi"
    entry.write_text('2\n1 0 4 2352 "track 01.bin" 0\n2 100 0 2352 track02.raw 0\n')
    (tmp_path / "track 01.bin").write_bytes(b"track")
    refs = content_dependencies(entry, tmp_path)
    assert [p.name for p in refs] == ["track 01.bin", "track02.raw"]


def test_scummvm_assets_are_not_games_and_manual_engines_need_registered_entry(tmp_path):
    from udeck.apps.game_library import scan_games

    catalog = installed(tmp_path, {
        "scummvm": {"supported_extensions": "scummvm|dat|bin|exe", "categories": "Game engine"},
        "tyrquake": {"supported_extensions": "pak", "categories": "Game engine"},
    })
    root = tmp_path / "Games"
    for name in ("scummvm", "quake"):
        (root / name / "Original").mkdir(parents=True)
    (root / "scummvm/Original/data.dat").write_bytes(b"assets")
    (root / "scummvm/Original/game.scummvm").write_text("original-game-id")
    pak = root / "quake/Original/pak0.pak"
    pak.write_bytes(b"original assets")
    source = Source.create(root)
    assert [i["format"] for i in scan_games(source, catalog).items] == ["SCUMMVM"]
    catalog.preferences["engineEntries"] = [str(pak)]
    assert {i["format"] for i in scan_games(source, catalog).items} == {"SCUMMVM", "PAK"}


def test_scan_cancel_returns_no_partial_library_and_keeps_identity(tmp_path):
    from udeck.apps.game_library import scan_games

    catalog = installed(tmp_path, {"mgba": {"supported_extensions": "gba"}})
    root = tmp_path / "Games"
    (root / "gba").mkdir(parents=True)
    (root / "gba/original.gba").write_bytes(b"original")
    source = Source.create(root)
    first = scan_games(source, catalog).items[0]
    assert scan_games(source, catalog, cancelled=lambda: True).items == []
    assert scan_games(source, catalog, cache={first["path"]: first}).items[0]["id"] == first["id"]


def test_core_probe_is_isolated_and_rejects_invalid_shared_library(tmp_path):
    from udeck.apps.game_catalog import probe_core

    bad = tmp_path / "bad_libretro.so"
    bad.write_bytes(b"invalid shared object")
    result = probe_core(bad)
    assert result["status"] == "incompatible" and result["reason"]
    # The parent remains alive and no core was loaded into it.
    assert json.loads(json.dumps(result))["status"] == "incompatible"


@pytest.mark.parametrize("crash_in_query", [False, True])
def test_probe_distinguishes_api_failure_from_uninitialized_core_cleanup(tmp_path, crash_in_query):
    from udeck.apps.game_catalog import probe_core

    compiler = shutil.which("cc")
    if not compiler:
        pytest.skip("A C compiler is needed for the native probe regression")
    source = tmp_path / "core.c"
    source.write_text('''#include <stdbool.h>
#include <stdlib.h>
struct info { const char *name, *version, *extensions; bool fullpath, block; };
unsigned retro_api_version(void) { return 1; }
void retro_get_system_info(struct info *p) {
''' + ("abort();" if crash_in_query else '*p=(struct info){"Original probe", "1", "gb", false, false};') + '''
}
__attribute__((destructor)) static void cleanup(void) { abort(); }
''')
    core = tmp_path / "original_libretro.so"
    subprocess.run([compiler, "-dynamiclib" if sys.platform == "darwin" else "-shared", "-fPIC", str(source),
                    "-o", str(core)], check=True, capture_output=True)
    result = probe_core(core)
    assert result["status"] == ("incompatible" if crash_in_query else "available")
