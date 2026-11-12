import asyncio
import os

import pytest


class Runtime:
    def __init__(self):
        self.running = False
        self.calls = []
        self.fail = False

    async def validate(self, value, addresses):
        self.calls.append(("validate", value["root"], set(addresses)))

    async def start(self, value, addresses):
        self.calls.append(("start", value["root"], set(addresses)))
        if self.fail:
            self.fail = False
            raise OSError("TCP port 445 is already in use")
        self.running = True

    async def stop(self):
        self.calls.append(("stop",))
        self.running = False

    async def alive(self):
        return self.running


def setup_manager(tmp_path):
    from udeck.smb_files.lifecycle import Actor, SmbManager
    runtime = Runtime()
    actor = Actor(uid=1000, gid=1000, name="testuser", pid=os.getpid())

    async def access(root, owner):
        return None

    manager = SmbManager(tmp_path / "smb.json", runtime=runtime, access=access)
    row = {"key": "mac:one@home", "addresses": ["192.0.2.5", "2001:db8::5"]}
    value = {"root": str(tmp_path), "networks": [row["key"]], "duration": 0}
    return manager, runtime, actor, row, value


def test_smb_defaults_are_separate_and_timed_settings_never_restore(tmp_path):
    from udeck.smb_files.lifecycle import SmbSettings
    settings = SmbSettings(tmp_path / "smb.json")
    assert settings.load()["root"] == ""
    assert settings.load()["enabled"] is False
    value = {**settings.load(), "enabled": True, "root": str(tmp_path), "networks": ["home"],
             "uid": 1000, "gid": 1000, "username": "testuser", "identity": [1, 2], "duration": 3600}
    settings.save(value)
    assert settings.load()["enabled"] is False
    value["duration"] = 0
    settings.save(value)
    assert settings.load()["enabled"] is True
    assert settings.path.stat().st_mode & 0o777 == 0o600


def test_smb_selected_addresses_and_revocation_kill_all_connections(tmp_path):
    async def scenario():
        manager, runtime, actor, row, value = setup_manager(tmp_path)
        await manager.configure(value, actor=actor, candidates=[row])
        assert manager.status()["urls"] == ["smb://192.0.2.5/udeck", "smb://[2001:db8::5]/udeck"]
        await manager.tick(candidates=[{**row, "key": "mac:one@other"}])
        assert not runtime.running and manager.status()["state"] == "waiting"
        assert runtime.calls[-1] == ("stop",)
        await manager.tick(candidates=[row])
        assert runtime.running
        await manager.stop(actor=actor)
        assert not runtime.running and not manager.status()["enabled"]
    asyncio.run(scenario())


@pytest.mark.parametrize("failure", ["save", "start", "start-and-rollback-write"])
def test_smb_reconfiguration_is_transactional(tmp_path, monkeypatch, failure):
    async def scenario():
        manager, runtime, actor, row, value = setup_manager(tmp_path)
        original = tmp_path / "original"
        replacement = tmp_path / "replacement"
        original.mkdir()
        replacement.mkdir()
        value["root"] = str(original)
        await manager.configure(value, actor=actor, candidates=[row])
        before = manager.settings.path.read_bytes()
        if failure == "save":
            def fail_save(value):
                raise OSError("disk full")
            monkeypatch.setattr(manager.settings, "save", fail_save)
        else:
            runtime.fail = True
            if failure == "start-and-rollback-write":
                save = manager.settings.save
                calls = 0

                def fail_second_write(value):
                    nonlocal calls
                    calls += 1
                    if calls > 1:
                        raise OSError("disk became full after startup")
                    save(value)
                monkeypatch.setattr(manager.settings, "save", fail_second_write)
        with pytest.raises(OSError):
            await manager.configure({**value, "root": str(replacement)}, actor=actor, candidates=[row])
        assert manager.status()["root"] == str(original) and runtime.running
        assert manager.settings.path.read_bytes() == before
        assert manager.status()["enabled"]
    asyncio.run(scenario())


@pytest.mark.parametrize("cause", ["expiry", "owner", "root", "crash"])
def test_smb_failures_stop_and_do_not_silently_restart(tmp_path, cause):
    async def scenario():
        manager, runtime, actor, row, value = setup_manager(tmp_path)
        root = tmp_path / "share"
        root.mkdir()
        value.update(root=str(root), duration=3600)
        await manager.configure(value, actor=actor, candidates=[row])
        if cause == "expiry":
            manager.deadline = 0
        elif cause == "root":
            root.rename(tmp_path / "old")
            root.mkdir()
        elif cause == "crash":
            runtime.running = False
        await manager.tick(candidates=[row], owner_alive=cause != "owner")
        assert not runtime.running and not manager.status()["enabled"]
        await manager.tick(candidates=[row])
        assert not runtime.running
    asyncio.run(scenario())


def test_smb_rejects_spoofed_user_and_invalid_selection(tmp_path):
    async def scenario():
        from udeck.smb_files.lifecycle import Actor
        manager, runtime, actor, row, value = setup_manager(tmp_path)
        for invalid in ({**value, "networks": []}, {**value, "networks": ["other"]}, {**value, "duration": True}):
            with pytest.raises(ValueError):
                await manager.configure(invalid, actor=actor, candidates=[row])
        await manager.configure({**value, "uid": 0, "username": "root"}, actor=actor, candidates=[row])
        assert manager.value["uid"] == 1000 and manager.value["username"] == actor.name
        with pytest.raises(PermissionError):
            await manager.stop(actor=Actor(uid=1001, gid=1001, name="other", pid=123))
        assert runtime.running
    asyncio.run(scenario())


def test_samba_config_has_no_wildcard_or_privileged_guest():
    from udeck.smb_files.runtime import samba_config
    config = samba_config("testuser", ["192.0.2.4", "2001:db8::4"])
    assert "interfaces = 192.0.2.4/32 2001:db8::4/128" in config
    assert "guest account = testuser" in config and "force user = testuser" in config
    assert "server min protocol = SMB2_02" in config and "guest only = yes" in config
    assert "read only = no" in config and "follow symlinks = no" in config
    assert "[udeck]" in config and "[homes]" not in config
    with pytest.raises(ValueError):
        samba_config("root", ["192.0.2.4"])
    with pytest.raises(ValueError):
        samba_config("test\nuser", ["192.0.2.4"])


def test_failed_service_stop_reports_effective_state_and_allows_retry(tmp_path):
    async def scenario():
        manager, runtime, actor, row, value = setup_manager(tmp_path)
        await manager.configure(value, actor=actor, candidates=[row])
        stop = runtime.stop

        async def denied():
            raise RuntimeError("systemd stop failed")

        runtime.stop = denied
        with pytest.raises(RuntimeError, match="systemd stop failed"):
            await manager.stop(actor=actor)
        assert manager.status()["enabled"] and manager.status()["state"] == "running"
        assert manager.status()["errors"] == ["systemd stop failed"]
        runtime.stop = stop
        await manager.stop(actor=actor)
        assert not manager.status()["enabled"] and not runtime.running
    asyncio.run(scenario())


def test_explicit_stop_save_failure_preserves_effective_configuration(tmp_path, monkeypatch):
    async def scenario():
        manager, runtime, actor, row, value = setup_manager(tmp_path)
        await manager.configure(value, actor=actor, candidates=[row])
        before = manager.settings.path.read_bytes()

        def fail_save(value):
            raise OSError("disk full")

        monkeypatch.setattr(manager.settings, "save", fail_save)
        with pytest.raises(OSError, match="disk full"):
            await manager.stop(actor=actor)
        assert manager.status()["enabled"] and runtime.running
        assert manager.settings.path.read_bytes() == before
    asyncio.run(scenario())
