"""
[INPUT]: 依赖发布构建器、Debian 安装清单与源码目录。
[OUTPUT]: 验证版本一致性、Python 载荷完整性和安装入口。
[POS]: 发布边界回归；包生命周期由独立 Debian 探针验证。
[PROTOCOL]: Update this header on change, then check AGENTS.md
"""

import importlib.util
import os
import shlex
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_debian_payload_contains_every_python_module_at_its_import_path():
    installed = set()
    for line in (ROOT / "debian/udeck.install").read_text().splitlines():
        fields = shlex.split(line, comments=True)
        if not fields:
            continue
        *patterns, destination = fields
        for pattern in patterns:
            for source in ROOT.glob(pattern):
                if source.is_dir():
                    installed.update(Path(destination) / source.name / path.relative_to(source)
                                     for path in source.rglob("*.py"))
                elif source.suffix == ".py":
                    installed.add(Path(destination) / source.name)
    expected = {Path("usr/lib/python3/dist-packages") / path.relative_to(ROOT / "src")
                for path in (ROOT / "src/udeck").rglob("*.py")}
    assert not expected - installed, sorted(str(path) for path in expected - installed)


def release_module():
    path = ROOT / "tools/build-release"
    assert path.is_file(), "The unified release builder has not been implemented"
    from importlib.machinery import SourceFileLoader

    spec = importlib.util.spec_from_loader("build_release", SourceFileLoader("build_release", str(path)))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def source(tmp_path):
    (tmp_path / "src/udeck").mkdir(parents=True)
    (tmp_path / "src/udeck/__init__.py").write_text('__version__ = "0.2.1"\n')
    (tmp_path / "debian").mkdir()
    (tmp_path / "debian/changelog").write_text("udeck (0.2.1) unstable; urgency=medium\n")
    return tmp_path


def test_release_tag_source_and_debian_version_must_agree(source):
    assert release_module().release_version(source, "v0.2.1") == "0.2.1"


@pytest.mark.parametrize("tag", ["v0.2.0", "main", "v0.2.1;echo injected", "../../0.2.1"])
def test_mismatched_or_unsafe_release_tag_is_rejected_before_build(source, tag):
    with pytest.raises(ValueError, match="tag"):
        release_module().release_version(source, tag)


def test_stale_debian_changelog_is_rejected_before_build(source):
    (source / "debian/changelog").write_text("udeck (0.2.0) unstable; urgency=medium\n")
    with pytest.raises(ValueError, match="changelog"):
        release_module().release_version(source, "v0.2.1")


def test_installer_reexecutes_absolute_path_after_changing_directory(tmp_path):
    bundle = tmp_path / "release bundle"
    bundle.mkdir()
    shutil.copy2(ROOT / "packaging/install-release", bundle / "install.sh")
    (bundle / "udeck_0.2.3_arm64.deb").touch()
    commands = tmp_path / "bin"
    commands.mkdir()
    scripts = {"sha256sum": "exit 0", "python3": "exit 0", "dpkg-deb": "echo udeck",
               "id": "echo 1000", "sudo": 'printf "%s\\n" "$@" > "$UDECK_TEST_SUDO_ARGS"'}
    for name, contents in scripts.items():
        command = commands / name
        command.write_text("#!/bin/sh\n" + contents + "\n")
        command.chmod(0o755)
    arguments = tmp_path / "sudo-arguments"
    subprocess.run(["sh", "release bundle/install.sh"], cwd=tmp_path, check=True,
                   env={**os.environ, "PATH": str(commands) + os.pathsep + os.environ["PATH"],
                        "UDECK_TEST_SUDO_ARGS": str(arguments)})
    assert arguments.read_text().splitlines() == ["sh", str(bundle / "install.sh")]
