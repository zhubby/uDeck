"""
[INPUT]: 依赖包内构建身份和发布快照生成器。
[OUTPUT]: 验证源码摘要、Git 身份与运行时回读。
[POS]: 构建身份回归；不运行 GitHub 或安装设备。
[PROTOCOL]: Update this header on change, then check AGENTS.md
"""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def builder():
    from importlib.machinery import SourceFileLoader

    spec = importlib.util.spec_from_loader('identity_builder', SourceFileLoader('identity_builder', str(ROOT / 'tools/build-release')))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_unstamped_checkout_reports_an_unrecorded_identity(tmp_path):
    package = tmp_path / 'udeck'
    package.mkdir()
    for name in ('__init__.py', 'build_info.py'):
        (package / name).write_bytes((ROOT / 'src/udeck' / name).read_bytes())
    output = subprocess.check_output([sys.executable, '-c', 'import json;from udeck.build_info import snapshot;print(json.dumps(snapshot()))'],
                                     cwd=tmp_path, env={'PYTHONPATH': str(tmp_path)}, text=True)
    result = json.loads(output)
    assert result['recorded'] is False
    assert result['sourceRevision'] is None
    assert result['sourceContentSha256'] is None


def test_source_identity_distinguishes_dirty_content_with_same_version(tmp_path):
    module = builder()
    source = tmp_path / 'source'
    (source / 'src/udeck').mkdir(parents=True)
    (source / 'src/udeck/__init__.py').write_text('__version__ = "1.0.2"\n')
    (source / 'src/udeck/build_info.py').write_bytes((ROOT / 'src/udeck/build_info.py').read_bytes())
    (source / 'settings').write_text('first\n')
    subprocess.run(['git', 'init', '-q', str(source)], check=True)
    subprocess.run(['git', '-C', str(source), 'add', '.'], check=True)
    subprocess.run(['git', '-C', str(source), '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '-qm', 'initial'], check=True)
    first = module.source_identity(source, source, '1.0.2')
    assert first['sourceDirty'] is False
    (source / 'settings').write_text('second\n')
    second = module.source_identity(source, source, '1.0.2')
    assert second['sourceDirty'] is True
    assert second['sourceRevision'] == first['sourceRevision']
    assert second['buildId'] != first['buildId']
    assert second['sourceContentSha256'] != first['sourceContentSha256']
    module.stamp_identity(source, second)
    output = subprocess.check_output([sys.executable, '-c', 'import json;from udeck.build_info import snapshot;print(json.dumps(snapshot()))'],
                                     cwd=tmp_path, env={'PYTHONPATH': str(source / 'src')}, text=True)
    assert json.loads(output) == second
    assert module.source_identity(source, source, '1.0.2')['sourceContentSha256'] == second['sourceContentSha256']


def test_source_identity_tracks_executable_mode_and_symbolic_link_target(tmp_path):
    module = builder()
    (tmp_path / 'file').write_text('payload')
    first = module.source_identity(tmp_path, tmp_path, '1.0.2')
    (tmp_path / 'file').chmod(0o755)
    second = module.source_identity(tmp_path, tmp_path, '1.0.2')
    assert first['sourceContentSha256'] != second['sourceContentSha256']
    (tmp_path / 'link').symlink_to('file')
    third = module.source_identity(tmp_path, tmp_path, '1.0.2')
    (tmp_path / 'link').unlink()
    (tmp_path / 'link').symlink_to('elsewhere')
    assert module.source_identity(tmp_path, tmp_path, '1.0.2')['sourceContentSha256'] != third['sourceContentSha256']


def test_source_identity_ignores_only_nonpackage_inputs_and_transient_caches(tmp_path):
    module = builder()
    for path in ('docs/uconsole/reference.md', 'artifacts/result.json', 'src/udeck/__pycache__/module.pyc',
                 'src/udeck/runtime_console/build/source.py'):
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text('first')
    first = module.source_identity(tmp_path, tmp_path, '1.0.2')
    for path in ('docs/uconsole/reference.md', 'artifacts/result.json', 'src/udeck/__pycache__/module.pyc'):
        (tmp_path / path).write_text('changed but excluded')
    assert module.source_identity(tmp_path, tmp_path, '1.0.2')['sourceContentSha256'] == first['sourceContentSha256']
    (tmp_path / 'src/udeck/runtime_console/build/source.py').write_text('package source changed')
    assert module.source_identity(tmp_path, tmp_path, '1.0.2')['sourceContentSha256'] != first['sourceContentSha256']


def test_container_build_can_embed_verified_host_git_identity(tmp_path, monkeypatch):
    module = builder()
    monkeypatch.setenv('UDECK_SOURCE_REVISION', 'a' * 40)
    monkeypatch.setenv('UDECK_SOURCE_DIRTY', 'true')
    identity = module.source_identity(tmp_path, tmp_path, '1.0.2')
    assert identity['sourceRevision'] == 'a' * 40
    assert identity['sourceDirty'] is True
    monkeypatch.setenv('UDECK_SOURCE_DIRTY', 'unknown')
    import pytest

    with pytest.raises(ValueError, match='Supplied source identity'):
        module.source_identity(tmp_path, tmp_path, '1.0.2')
