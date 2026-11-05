import json
import os
import subprocess
import sys


def test_all_qml_pages_render_without_engine_warnings(tmp_path):
    result = subprocess.run(
        [sys.executable, "-m", "udeck.main", "--mock", "--windowed", "--smoke-test",
         "--screenshot", str(tmp_path / "preview.png"), "--quit-after", "1.8"],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen", "PYTHONPATH": "src"},
        text=True, capture_output=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout.strip().splitlines()[-1])
    assert report["smoke"] == "passed"
    assert report["qmlErrors"] == []
    assert "Error" not in result.stderr
    assert (tmp_path / "preview.png").stat().st_size > 10000
