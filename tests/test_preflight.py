import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def preflight():
    path = ROOT / "src/udeck/preflight.py"
    assert path.is_file(), "The standalone compatibility checker has not been implemented"
    spec = importlib.util.spec_from_file_location("standalone_preflight", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("distribution", [
    'ID=debian\nVERSION_ID="13"\nVERSION_CODENAME=trixie\n',
    'ID=raspbian\nVERSION_ID="13"\nVERSION_CODENAME=trixie\n',
])
def test_trixie_arm64_is_installable_before_runtime_dependencies_are_installed(distribution):
    report = preflight().assess_system(distribution, "arm64", (3, 13, 5))
    assert report["supported"] is True
    assert report["errors"] == []


@pytest.mark.parametrize("distribution,architecture,python,reason", [
    ("ID=debian\nVERSION_CODENAME=bullseye", "arm64", (3, 9, 2), "v3.1"),
    ("ID=debian\nVERSION_CODENAME=bookworm", "arm64", (3, 11, 2), "trixie"),
    ("ID=debian\nVERSION_CODENAME=trixie", "armhf", (3, 13, 5), "arm64"),
    ("ID=debian\nVERSION_CODENAME=trixie", "arm64", (3, 14, 0), "Python"),
    ("ID=ubuntu\nVERSION_CODENAME=trixie", "arm64", (3, 13, 5), "Debian"),
])
def test_unsupported_systems_return_actionable_errors(distribution, architecture, python, reason):
    report = preflight().assess_system(distribution, architecture, python)
    assert report["supported"] is False
    assert reason in " ".join(report["errors"])


def test_missing_and_incompatible_packages_are_distinguished():
    report = preflight().assess_packages({
        "python3-pyside6.qtquick": "6.9.1-1", "labwc": "0.8.3-1",
        "bluez": "5.82-1.1", "pipewire-audio": "1.4.2-1",
    })
    assert "python3-pyside6.qtquick" in report["incompatible"]
    assert "labwc" in report["incompatible"]
    assert "gvfs" in report["missing"]
    assert "wpasupplicant" in report["missing"]
    assert "bluez" not in report["missing"]
    assert report["ready"] is False


def test_raspberry_pi_newer_labwc_version_satisfies_minimum():
    report = preflight().assess_packages({"labwc": "0.20.2-1~bpo13+1"})
    assert "labwc" not in report["missing"]
    assert "labwc" not in report["incompatible"]


def test_preflight_runs_without_the_application_or_qt_on_pythonpath(tmp_path):
    script = tmp_path / "udeck-preflight"
    source = ROOT / "src/udeck/preflight.py"
    assert source.is_file(), "The standalone compatibility checker has not been implemented"
    script.write_bytes(source.read_bytes())
    result = subprocess.run([sys.executable, "-I", str(script), "--json"], cwd=tmp_path,
                            capture_output=True, text=True, timeout=15)
    report = json.loads(result.stdout)
    assert isinstance(report["supported"], bool)
    assert result.returncode == (0 if report["supported"] else 1)
