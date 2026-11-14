"""Interoperability with real JSON playlists, independent of native cores."""

import json
from pathlib import Path

import pytest
from test_games_catalog import installed


def write_playlist(path, items, **fields):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"version": "1.5", **fields, "items": items}), encoding="utf-8")
    return path


def entry(path, label="Original", database="Nintendo - Game Boy.lpl", **fields):
    return {"path": str(path), "label": label, "db_name": database,
            "core_path": "DETECT", "core_name": "DETECT", "crc32": "DETECT", **fields}


def test_database_directories_distinguish_game_boy_color_without_splitting_core_support(tmp_path):
    catalog = installed(tmp_path, {"gambatte": {"supported_extensions": "gb|gbc"}})
    assert catalog.platform_for_directory("Nintendo - Game Boy Color").id == "gb"
    assert catalog.platform_for_directory("GB").id == "gb"
    assert catalog.database_for_path("gb", Path("Test.gbc"), "gb") == "Nintendo - Game Boy Color"


def test_playlist_round_trip_preserves_unknown_fields_and_refuses_external_edits(tmp_path):
    from udeck.apps.emulator.playlists import PlaylistDocument

    path = write_playlist(tmp_path / "Custom.lpl", [entry("/games/a.gb", custom={"a": 1})],
                          sort_mode=2, custom_playlist=["opaque"])
    document = PlaylistDocument.load(path)
    document.data["items"][0]["label"] = "New label"
    document.save()
    value = json.loads(path.read_text())
    assert value["custom_playlist"] == ["opaque"] and value["sort_mode"] == 2
    assert value["items"][0]["custom"] == {"a": 1}
    before = path.read_bytes()
    path.write_bytes(before.replace(b'New label', b'Other app'))
    with pytest.raises(ValueError, match="changed|modified"):
        document.save()
    assert b'Other app' in path.read_bytes()


@pytest.mark.parametrize("old,path", [
    ("D:\\ROMs", "D:\\ROMs\\Nintendo - Game Boy\\a.zip#folder/a.gb"),
    ("/old/ROMs", "/old/ROMs/Nintendo - Game Boy/a.zip#folder/a.gb"),
])
def test_portable_content_separates_archive_from_launch_path(tmp_path, old, path):
    from udeck.apps.emulator.playlists import content_reference

    reference = content_reference(path, old, tmp_path / "roms")
    assert reference.path == tmp_path / "roms/Nintendo - Game Boy/a.zip"
    assert reference.member == "folder/a.gb" and reference.basename == "a"
    assert reference.launch_path == str(reference.path) + "#folder/a.gb"
    assert reference.suffix == ".gb"


def test_portable_relocation_checks_path_components_not_text_prefixes(tmp_path):
    from udeck.apps.emulator.playlists import content_reference

    reference = content_reference("/games-other/a.gb", "/games", tmp_path)
    assert reference.path == Path("/games-other/a.gb")
    with pytest.raises(ValueError):
        content_reference("/games/a.zip#../escape.gb", "", tmp_path)


def test_playlist_entries_keep_labels_and_share_identity_across_collections(tmp_path):
    from udeck.apps.emulator.playlists import ContentIdentities, read_library

    root = tmp_path / "roms"
    root.mkdir()
    game = root / "Original.gb"
    game.write_bytes(b"original game")
    playlists = tmp_path / "playlists"
    write_playlist(playlists / "Custom.lpl", [entry(game, "My label")])
    write_playlist(playlists / "Other.lpl", [entry(game, "Another label")])
    identities = ContentIdentities(tmp_path / "identities.json")
    identities.register(game, "", "preserved-game-id")
    identities.save()
    catalog = installed(tmp_path, {})
    result = read_library(playlists, root, catalog, identities)
    assert [i["title"] for i in result.items] == ["My label", "Another label"]
    assert {i["id"] for i in result.items} == {"preserved-game-id"}
    assert len({i["entryId"] for i in result.items}) == 2
    assert len(result.playlists) == 2


def test_missing_rom_and_bad_playlist_do_not_hide_good_and_empty_playlists(tmp_path):
    from udeck.apps.emulator.playlists import ContentIdentities, read_library

    playlists = tmp_path / "playlists"
    write_playlist(playlists / "Good.lpl", [entry(tmp_path / "missing.gb")])
    write_playlist(playlists / "Empty.lpl", [])
    (playlists / "Bad.lpl").write_text("{broken")
    result = read_library(playlists, tmp_path, installed(tmp_path, {}),
                          ContentIdentities(tmp_path / "identities.json"))
    assert len(result.playlists) == 3 and len(result.items) == 1
    assert result.items[0]["contentError"] and result.items[0]["title"] == "Original"
    assert result.errors and "Bad.lpl" in str(result.errors)


def test_playlist_core_precedes_defaults_and_archive_uses_member_extension(tmp_path):
    catalog = installed(tmp_path, {"gambatte": {"supported_extensions": "gb"},
                                   "sameboy": {"supported_extensions": "gb|gbc"}},
                        {"coreEnabled": {"sameboy": True}})
    item = {"id": "g", "path": "/games/pack.zip", "format": "GBC", "platform": "gb",
            "archiveMember": "original.gbc", "playlistCoreId": "sameboy",
            "playlistDefaultCoreId": "gambatte", "playlistPath": "/lists/GB.lpl"}
    assert catalog.resolve(item).id == "sameboy"
    item["playlistCoreId"] = "not_installed"
    with pytest.raises(ValueError):
        catalog.resolve(item)


def test_generation_previews_only_new_entries_and_preserves_manual_metadata(tmp_path):
    from udeck.apps.emulator.playlists import generate_playlists

    root = tmp_path / "roms/Nintendo - Game Boy"
    root.mkdir(parents=True)
    first, second = root / "One.gb", root / "Two.gb"
    first.write_bytes(b"one")
    second.write_bytes(b"two")
    path = write_playlist(tmp_path / "playlists/Nintendo - Game Boy.lpl",
                          [entry(first, "Custom label", custom=123)], custom_top=True)
    catalog = installed(tmp_path, {"gambatte": {"supported_extensions": "gb"}})
    catalog.preferences["coreEnabled"] = {"gambatte": False}
    proposal = generate_playlists(root.parent, path.parent, catalog)
    assert len(proposal.additions) == 1
    assert len(json.loads(path.read_text())["items"]) == 1
    proposal.commit()
    value = json.loads(path.read_text())
    assert value["custom_top"] is True and value["items"][0]["label"] == "Custom label"
    assert value["items"][0]["custom"] == 123 and value["items"][1]["label"] == "Two"
    assert value["items"][1]["crc32"] == "DETECT"


def test_entry_edit_refuses_external_changes_to_the_same_content(tmp_path):
    from udeck.apps.emulator.playlists import ContentIdentities, read_library, update_entry

    path = write_playlist(tmp_path / "Custom.lpl", [entry(tmp_path / "Original.gb")])
    item = read_library(tmp_path, tmp_path, installed(tmp_path, {}),
                        ContentIdentities(tmp_path / "identities.json")).items[0]
    item["romRoot"] = str(tmp_path)
    external = json.loads(path.read_text())
    external["items"][0].update(label="Edited in RetroArch", core_path="other_libretro.so")
    path.write_text(json.dumps(external))
    with pytest.raises(ValueError, match="changed|modified"):
        update_entry(item, {"core_path": "gambatte_libretro.so"})
    assert json.loads(path.read_text()) == external


def test_successive_entry_edits_keep_a_fresh_signature_and_unknown_fields(tmp_path):
    from udeck.apps.emulator.playlists import ContentIdentities, read_library, update_entry

    path = write_playlist(tmp_path / "Custom.lpl", [entry(tmp_path / "Original.gb", opaque=42)])
    item = read_library(tmp_path, tmp_path, installed(tmp_path, {}),
                        ContentIdentities(tmp_path / "identities.json")).items[0]
    item["romRoot"] = str(tmp_path)
    update_entry(item, {"core_path": "gambatte_libretro.so"})
    update_entry(item, {"core_path": "sameboy_libretro.so"})
    assert json.loads(path.read_text())["items"][0]["opaque"] == 42
    assert json.loads(path.read_text())["items"][0]["core_path"] == "sameboy_libretro.so"


@pytest.mark.parametrize("default", ["not_installed", "sameboy"])
def test_unavailable_explicit_playlist_default_is_reported_instead_of_switching_core(tmp_path, default):
    catalog = installed(tmp_path, {"gambatte": {"supported_extensions": "gb"},
                                   "sameboy": {"supported_extensions": "gb"}},
                        {"coreEnabled": {"sameboy": False}})
    item = {"id": "g", "path": "/roms/game.gb", "platform": "gb", "playlistPath": "/lists/Custom.lpl",
            "playlistDefaultCoreId": default}
    with pytest.raises(ValueError):
        catalog.resolve(item)


def test_mixed_list_uses_each_database_and_infers_missing_database_from_rom_folder(tmp_path):
    from udeck.apps.emulator.playlists import ContentIdentities, read_library

    root = tmp_path / "roms"
    gameboy = root / "Nintendo - Game Boy Color/Original.gbc"
    nes = root / "Nintendo - Nintendo Entertainment System/Other.nes"
    for path in (gameboy, nes):
        path.parent.mkdir(parents=True)
        path.write_bytes(b"original")
    write_playlist(tmp_path / "playlists/Mixed.lpl", [entry(gameboy, database=""),
                   entry(nes, database="Nintendo - Nintendo Entertainment System.lpl")])
    result = read_library(tmp_path / "playlists", root, installed(tmp_path, {}),
                          ContentIdentities(tmp_path / "identities.json"))
    assert [i["platform"] for i in result.items] == ["gb", "nes"]
    assert [i["dbName"] for i in result.items] == ["Nintendo - Game Boy Color", "Nintendo - Nintendo Entertainment System"]
