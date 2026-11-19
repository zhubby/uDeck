"""
[INPUT]: 依赖逐文件 pytest 执行器与临时测试文件。
[OUTPUT]: 验证进程隔离、失败保留与超时报告。
[POS]: 日常 CI 调度回归；不执行完整产品测试。
[PROTOCOL]: Update this header on change, then check AGENTS.md
"""

import importlib.util
import json
import os
import sys
from pathlib import Path


def runner():
    from importlib.machinery import SourceFileLoader

    path = Path(__file__).resolve().parents[1] / 'tools/test-suite'
    spec = importlib.util.spec_from_loader('suite_runner', SourceFileLoader('suite_runner', str(path)))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_each_file_has_a_distinct_process_and_failure_does_not_hide_later_results(tmp_path):
    tests = tmp_path / 'tests'
    tests.mkdir()
    (tests / 'test_a.py').write_text('import os\ndef test_a():\n    open("pid-a", "w").write(str(os.getpid()))\n')
    (tests / 'test_b.py').write_text('def test_b():\n    assert False, "retained failure"\n')
    (tests / 'test_c.py').write_text('import os\ndef test_c():\n    open("pid-c", "w").write(str(os.getpid()))\n')
    report = runner().run_suite(tmp_path, sorted(tests.glob('*.py')), tmp_path / 'output', 20, sys.executable)
    assert report['status'] == 'failed'
    assert len(report['files']) == 3
    assert report['totals'] == {'tests': 3, 'failures': 1, 'errors': 0, 'skipped': 0}
    assert (tmp_path / 'pid-a').read_text() != (tmp_path / 'pid-c').read_text()
    assert 'retained failure' in (tmp_path / 'output' / report['files'][1]['log']).read_text()
    assert json.loads((tmp_path / 'output/summary.json').read_text()) == report


def test_timeout_is_a_failure_and_process_is_reaped(tmp_path):
    file = tmp_path / 'test_timeout.py'
    file.write_text('import time\ndef test_wait():\n    time.sleep(10)\n')
    report = runner().run_suite(tmp_path, [file], tmp_path / 'output', .2, sys.executable)
    assert report['status'] == 'failed'
    assert report['files'][0]['timedOut']
    if os.name == 'posix':
        import pytest

        with pytest.raises(ProcessLookupError):
            os.kill(report['files'][0]['pid'], 0)


def test_existing_output_is_preserved_and_rejected(tmp_path):
    import pytest

    output = tmp_path / 'output'
    output.mkdir()
    evidence = output / 'earlier.log'
    evidence.write_text('prior run')
    file = tmp_path / 'test_ok.py'
    file.write_text('def test_ok():\n    pass\n')
    with pytest.raises(ValueError, match='new output directory'):
        runner().run_suite(tmp_path, [file], output, 20, sys.executable)
    assert evidence.read_text() == 'prior run'
