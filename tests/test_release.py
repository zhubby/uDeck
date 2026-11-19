"""
[INPUT]: 依赖发布构建器、Debian 安装清单与源码目录。
[OUTPUT]: 验证版本、包元数据、构建环境边界、Python 载荷和安装入口。
[POS]: 发布边界回归；包生命周期由独立 Debian 探针验证。
[PROTOCOL]: Update this header on change, then check AGENTS.md
"""

import hashlib
import importlib.util
import io
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
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


@pytest.mark.parametrize("version", ["01.2.3", "1.2", "1.0.0-rc.1", "1.0.0+build", "version"])
def test_release_requires_a_stable_semantic_version(source, version):
    (source / "src/udeck/__init__.py").write_text(f"__version__ = {version!r}\n")
    with pytest.raises(ValueError, match="stable"):
        release_module().release_version(source)


@pytest.mark.parametrize("field,value", [("Package", "other"), ("Version", "0.2.0"), ("Architecture", "amd64")])
def test_mislabeled_binary_is_rejected_before_publication(tmp_path, monkeypatch, field, value):
    module = release_module()
    fields = {"Package": "udeck", "Version": "0.2.1", "Architecture": "arm64"}
    fields[field] = value
    control = "".join(f"{key}: {value}\n" for key, value in fields.items())
    monkeypatch.setattr(module.subprocess, "check_output", lambda *args, **kwargs: control)
    package = tmp_path / "udeck_0.2.1_arm64.deb"
    package.write_bytes(b"binary with an apparently correct filename")
    with pytest.raises(ValueError, match=field):
        module.package_metadata(package, "0.2.1")


def test_manifest_package_metadata_comes_from_the_verified_binary(tmp_path, monkeypatch):
    module = release_module()
    control = "Package: udeck\nVersion: 0.2.1\nArchitecture: arm64\nDescription: uDeck\n desktop suite\n"
    monkeypatch.setattr(module.subprocess, "check_output", lambda *args, **kwargs: control)
    package = tmp_path / "udeck_0.2.1_arm64.deb"
    package.write_bytes(b"verified binary payload")
    metadata = module.package_metadata(package, "0.2.1")
    assert metadata == {"file": package.name, "package": "udeck", "version": "0.2.1",
                        "architecture": "arm64", "control": control,
                        "sha256": hashlib.sha256(package.read_bytes()).hexdigest()}


def identity_payload(contents):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode='w') as archive:
        if contents is not None:
            encoded = contents.encode()
            info = tarfile.TarInfo('./usr/lib/python3/dist-packages/udeck/_build_identity.py')
            info.size = len(encoded)
            archive.addfile(info, io.BytesIO(encoded))
    return buffer.getvalue()


@pytest.mark.parametrize('contents', [None, 'OTHER = {}', 'BUILD_IDENTITY = unknown()', 'BUILD_IDENTITY = []'])
def test_package_identity_requires_a_literal_dictionary(monkeypatch, contents):
    module = release_module()
    monkeypatch.setattr(module.subprocess, 'check_output', lambda *args, **kwargs: identity_payload(contents))
    with pytest.raises(ValueError, match='identity'):
        module.package_identity(Path('package.deb'))


def test_release_assembly_rejects_a_package_from_another_source(tmp_path, monkeypatch):
    module = release_module()
    built = tmp_path / 'built'
    built.mkdir()
    for name in ('udeck_1.0.2_arm64.deb', 'udeck_1.0.2.dsc', 'udeck_1.0.2.tar.xz',
                 'udeck_1.0.2_arm64.buildinfo', 'udeck_1.0.2_arm64.changes'):
        (built / name).write_text('artifact')
    expected = {'buildId': 'expected'}
    monkeypatch.setattr(module, 'package_metadata', lambda *args: {})
    monkeypatch.setattr(module, 'package_identity', lambda *args: {'buildId': 'another source'})
    with pytest.raises(ValueError, match='does not match'):
        module.assemble(ROOT, built, tmp_path / 'output', '1.0.2', identity=expected)


def test_daily_checks_cannot_build_deb_and_release_stays_release_only():
    checks = (ROOT / '.github/workflows/checks.yml').read_text()
    release = (ROOT / '.github/workflows/release.yml').read_text()
    assert re.search(r'\non:\n  push:\n  pull_request:\n', checks)
    assert 'tools/test-suite --output artifacts/ci-tests' in checks
    invocations = [line for line in checks.splitlines() if 'python tools/build-release ' in line]
    assert invocations and all('--check-version' in line for line in invocations)
    assert not re.search(r'build-deb|dpkg-buildpackage|gh release upload', checks)
    assert re.search(r'\non:\n  release:\n    types: \[published\]\n', release)
    assert not re.search(r'^  (push|pull_request|workflow_dispatch):', release, re.MULTILINE)
    assert 'gh release download' in release
    assert 'debian_package_probe.py \\' in release and '--previous' in release


def published_release(version, **fields):
    return {'tag_name': 'v' + version, 'draft': False, 'prerelease': False,
            'assets': [{'name': f'udeck_{version}_arm64.deb', 'state': 'uploaded'},
                       {'name': 'SHA256SUMS', 'state': 'uploaded'}], **fields}


def test_previous_release_uses_version_order_across_all_api_pages():
    releases = [[published_release('2.0.0'), published_release('1.0.0')],
                [published_release('1.9.0'), published_release('1.10.0'), published_release('1.8.9')]]
    assert release_module().previous_release(releases, '1.10.0') == 'v1.9.0'


def test_previous_release_requires_a_published_stable_complete_arm64_bundle():
    releases = [[published_release('1.0.0'), published_release('1.9.0', draft=True),
                 published_release('1.8.0', prerelease=True), published_release('1.7.0', assets=[]),
                 published_release('1.6.0', tag_name='v1.6.0-rc.1'), published_release('1.5.0', assets=[
                     {'name': 'udeck_1.5.0_arm64.deb', 'state': 'uploaded'}]),
                 published_release('1.4.0', assets=[
                     {'name': 'udeck_1.4.0_arm64.deb', 'state': 'new'},
                     {'name': 'SHA256SUMS', 'state': 'uploaded'}])]]
    assert release_module().previous_release(releases, '2.0.0') == 'v1.0.0'


def test_first_release_runs_clean_install_without_a_previous_package():
    assert release_module().previous_release([[published_release('1.0.0')]], '1.0.0') == ''


@pytest.mark.parametrize('with_identity', [True, False])
def test_package_build_keeps_source_identity_out_of_child_environment(source, tmp_path, monkeypatch, with_identity):
    module = release_module()
    for name in ('vendor', 'packaging', 'tools', 'tests', 'docs', '.github'):
        (source / name).mkdir()
    for name in ('AGENTS.md', 'README.md', 'pyproject.toml', 'uv.lock', '.python-version', 'LICENSE'):
        (source / name).write_text('fixture\n')
    (source / 'src/udeck/AGENTS.md').write_text('__init__.py: fixture\n')
    monkeypatch.setattr(module, '__file__', str(source / 'tools/build-release'))
    commands = tmp_path / 'bin'
    commands.mkdir()
    (commands / 'dpkg').write_text('#!/bin/sh\necho arm64\n')
    (commands / 'dpkg-buildpackage').write_text(
        f'#!{sys.executable}\n'
        'import json, os\nfrom pathlib import Path\n'
        'names = ("UDECK_SOURCE_REVISION", "UDECK_SOURCE_DIRTY", "DEB_BUILD_OPTIONS", "UDECK_TEST_BUILD_SENTINEL")\n'
        'Path(os.environ["UDECK_TEST_CHILD_ENV"]).write_text(json.dumps({name: os.environ.get(name) for name in names}))\n'
        'raise SystemExit(23)\n')
    for command in commands.iterdir():
        command.chmod(0o755)
    for name, value in {'UDECK_SOURCE_REVISION': 'a' * 40, 'UDECK_SOURCE_DIRTY': 'true'}.items():
        if with_identity:
            monkeypatch.setenv(name, value)
        else:
            monkeypatch.delenv(name, raising=False)
    captured = tmp_path / 'child-environment.json'
    monkeypatch.setenv('PATH', str(commands) + os.pathsep + os.environ['PATH'])
    monkeypatch.setenv('UDECK_TEST_CHILD_ENV', str(captured))
    monkeypatch.setenv('UDECK_TEST_BUILD_SENTINEL', 'preserved')
    monkeypatch.setenv('DEB_BUILD_OPTIONS', 'parallel=2')
    parent = dict(os.environ)

    with pytest.raises(subprocess.CalledProcessError) as error:
        module.main(['--output', str(tmp_path / 'release')])

    assert error.value.returncode == 23
    assert json.loads(captured.read_text()) == {
        'UDECK_SOURCE_REVISION': None, 'UDECK_SOURCE_DIRTY': None,
        'DEB_BUILD_OPTIONS': 'parallel=2', 'UDECK_TEST_BUILD_SENTINEL': 'preserved'}
    assert not {name for name in parent.keys() | os.environ.keys() if parent.get(name) != os.environ.get(name)}


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
