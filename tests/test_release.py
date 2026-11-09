import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


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
