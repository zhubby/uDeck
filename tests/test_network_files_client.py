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
