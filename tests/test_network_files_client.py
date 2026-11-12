import pytest

from udeck.network_files import client


@pytest.mark.parametrize("remote_error", [None, "Could not save settings"])
def test_stop_attempts_systemd_shutdown_even_if_disable_or_remote_stop_fails(monkeypatch, remote_error):
    calls = []

    async def remote(member, value=None):
        assert member == "Stop"
        if remote_error:
            raise RuntimeError(remote_error)
        return {"state": "stopped"}

    def command(arguments):
        calls.append(arguments)
        if "disable" in arguments:
            raise RuntimeError("Could not disable the unit")

    monkeypatch.setattr(client, "remote", remote)
    monkeypatch.setattr(client, "systemd_installed", lambda: True)
    monkeypatch.setattr(client, "command", command)
    with pytest.raises(RuntimeError):
        client.stop()
    assert calls == [
        ["systemctl", "--user", "disable", client.UNIT],
        ["systemctl", "--user", "stop", client.UNIT],
    ]


def test_persistence_failure_leaves_the_existing_web_share_untouched(monkeypatch):
    methods, commands = [], []

    async def remote(member, value=None):
        methods.append(member)
        return {"enabled": True, "duration": 0}

    def command(arguments):
        commands.append(arguments)
        if arguments[0] == "loginctl":
            raise RuntimeError("linger denied")

    monkeypatch.setattr(client, "remote", remote)
    monkeypatch.setattr(client, "systemd_installed", lambda: True)
    monkeypatch.setattr(client, "unit_enabled", lambda: True, raising=False)
    monkeypatch.setattr(client, "command", command)
    with pytest.raises(RuntimeError, match="linger denied"):
        client.start({"duration": 0})
    assert "Configure" not in methods and "Stop" not in methods
    assert commands[-1] == ["systemctl", "--user", "enable", client.UNIT]
