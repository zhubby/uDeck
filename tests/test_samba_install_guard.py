import importlib.machinery
import importlib.util
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest


def load_guard():
    loader = importlib.machinery.SourceFileLoader("guard", str(Path(__file__).resolve().parents[1] / "packaging/samba-install-guard"))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module.Guard


@pytest.mark.parametrize("failure", [False, True])
def test_guard_precedes_dependency_install_and_preserves_existing_service(tmp_path, failure):
    Guard = load_guard()
    existing = tmp_path / "etc/systemd/system/smbd.service"
    existing.parent.mkdir(parents=True)
    existing.symlink_to("/dev/null")
    policy = tmp_path / "usr/sbin/policy-rc.d"
    policy.parent.mkdir(parents=True)
    policy.write_text("existing policy")
    calls = []

    def run(arguments, **kwargs):
        calls.append(arguments)
        return SimpleNamespace(returncode=0)

    try:
        with Guard(root=tmp_path, run=run):
            assert not (tmp_path / "run/systemd/system/smbd.service.d").exists()
            guard = tmp_path / "etc/systemd/system/nmbd.service.d/90-udeck-install-guard.conf"
            assert "ConditionPathExists=" in guard.read_text()
            installed = tmp_path / "usr/lib/systemd/system/nmbd.service"
            installed.parent.mkdir(parents=True)
            installed.write_text("new Samba service")
            if failure:
                raise ValueError("APT failed")
    except ValueError:
        assert failure
    assert existing.is_symlink() and existing.readlink() == Path("/dev/null")
    assert policy.read_text() == "existing policy"
    assert not guard.exists()
    assert ["env", "DPKG_MAINTSCRIPT_PACKAGE=udeck", "deb-systemd-helper", "disable", "nmbd.service"] in calls
    assert not any("smbd.service" in command for command in calls)


def test_failed_disable_keeps_durable_guard_and_next_install_recovers(tmp_path):
    Guard = load_guard()

    def fail_disable(arguments, **kwargs):
        if "deb-systemd-helper" in arguments:
            raise subprocess.CalledProcessError(1, arguments)
        return SimpleNamespace(returncode=0)

    with pytest.raises(RuntimeError):
        with Guard(root=tmp_path, run=fail_disable):
            installed = tmp_path / "usr/lib/systemd/system/smbd.service"
            installed.parent.mkdir(parents=True)
            installed.write_text("new service")
    guard = tmp_path / "etc/systemd/system/smbd.service.d/90-udeck-install-guard.conf"
    assert guard.exists()  # A reboot must not expose the newly installed service.
    calls = []

    def run(arguments, **kwargs):
        calls.append(arguments)
        return SimpleNamespace(returncode=0)

    with Guard(root=tmp_path, run=run):
        assert guard.exists()
    assert not guard.exists()
    assert ["env", "DPKG_MAINTSCRIPT_PACKAGE=udeck", "deb-systemd-helper", "disable", "smbd.service"] in calls


def test_interruption_keeps_guard_until_a_later_install(tmp_path):
    with pytest.raises(KeyboardInterrupt):
        with load_guard()(root=tmp_path, run=lambda *args, **kwargs: SimpleNamespace(returncode=0)):
            raise KeyboardInterrupt
    assert (tmp_path / "etc/systemd/system/smbd.service.d/90-udeck-install-guard.conf").is_file()


def test_interrupted_installer_reaps_command_before_returning(tmp_path):
    script = Path(__file__).resolve().parents[1] / "packaging/samba-install-guard"
    ready, terminated = tmp_path / "ready", tmp_path / "terminated"
    child = """
import os, signal, sys, time
from pathlib import Path
def stop(signum, frame):
    Path(sys.argv[2]).write_text('terminated')
    raise SystemExit(0)
signal.signal(signal.SIGTERM, stop)
Path(sys.argv[1]).write_text(str(os.getpid()))
time.sleep(60)
"""
    parent = """
import runpy, signal, sys
def stop(signum, frame):
    raise KeyboardInterrupt
signal.signal(signal.SIGTERM, stop)
try:
    runpy.run_path(sys.argv[1])['install']([sys.executable, '-c', sys.argv[2], *sys.argv[3:]])
except KeyboardInterrupt:
    pass
"""
    process = subprocess.Popen([sys.executable, "-c", parent, str(script), child, str(ready), str(terminated)])
    try:
        deadline = time.monotonic() + 5
        while not ready.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert ready.exists()
        process.send_signal(signal.SIGTERM)
        assert process.wait(timeout=5) == 0
        assert terminated.read_text() == "terminated"
        with pytest.raises(ProcessLookupError):
            os.kill(int(ready.read_text()), 0)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
