import json
import os
import shutil
import subprocess
import sys

import pytest


@pytest.mark.skipif(not shutil.which("dbus-run-session") or not shutil.which("rclone"),
                    reason="A session D-Bus daemon and rclone are required")
def test_headless_save_service_protocol_and_restart(tmp_path):
    bus_config = tmp_path / "session.conf"
    bus_config.write_text('<busconfig><type>session</type><listen>unix:tmpdir=/tmp</listen>'
                          '<auth>EXTERNAL</auth><policy context="default">'
                          '<allow send_destination="*"/><allow receive_sender="*"/><allow own="*"/>'
                          '</policy></busconfig>')
    result = subprocess.run(["dbus-run-session", "--config-file", str(bus_config), "--", sys.executable,
                             "tests/emulator_save_daemon_probe.py", str(tmp_path / "probe")],
                            env={**os.environ, "PYTHONPATH": "src"}, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout.strip().splitlines()[-1])["restart"] == "passed"
