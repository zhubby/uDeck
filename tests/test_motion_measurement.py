"""
[INPUT]: 依赖独立测量工具的时间线统计函数。
[OUTPUT]: 验证输入屏障、呈现分母、锁存、长帧和资源门槛。
[POS]: 动画探针的纯数据回归，不依赖渲染速度。
[PROTOCOL]: Update this header on change, then check AGENTS.md
"""

import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('measure_motion',
    Path(__file__).resolve().parents[1] / 'tools/measure-motion.py')
motion = importlib.util.module_from_spec(spec)
spec.loader.exec_module(motion)


def frame(at, *, index=0, staged=None, moving=False, scope='home'):
    return {'at': at, 'stagedAt': at if staged is None else staged, 'moving': moving,
            'scope': scope, 'state': {'page': 'home', 'index': index, 'modal': False}}


def command(at, index, *, kind='navigation'):
    return {'id': index, 'started': at, 'deadline': at + .2, 'scenario': 'home', 'kind': kind,
            'changed': True, 'expected': {'page': 'home', 'index': index, 'modal': False}}


def test_missing_first_frame_keeps_the_input_in_the_failure_denominator():
    result = motion.analyze_timeline([command(1, 1), command(2, 2)], [frame(1.016, index=1)], 60)
    assert result['inputs']['sent'] == 2
    assert result['inputs']['presented'] == 1
    assert result['inputs']['failed'] == 1
    assert result['inputs']['presentationRate'] == .5
    assert result['inputResults'][1]['status'] == 'timeout'
    assert not result['thresholdResults']['allInputsPresented']['passed']


def test_a_swap_of_old_animation_state_is_not_a_response_to_new_input():
    result = motion.analyze_timeline([command(1, 1)],
        [frame(1.002, index=1, staged=.99), frame(1.040, index=1)], 60)
    assert result['inputResults'][0]['firstPresentationMs'] == pytest.approx(40)


def test_rapid_reversal_does_not_credit_a_later_return_to_a_skipped_selection():
    commands = [command(1, 1), command(1.02, 0), command(1.04, 1)]
    result = motion.analyze_timeline(commands, [frame(1.03, index=0), frame(1.05, index=1)], 60)
    assert [row['status'] for row in result['inputResults']] == ['timeout', 'presented', 'presented']
    assert result['inputResults'][0]['supersededAt'] == 1.02


def test_long_frame_is_retained_but_static_and_setup_gaps_are_not_drops():
    frames = [frame(0), frame(1, moving=True), frame(1.016, moving=True),
              frame(1.096), frame(8), frame(10, moving=True, scope='files'),
              frame(10.016, scope='files')]
    result = motion.analyze_timeline([], frames, 60)
    assert result['activeFrameGapsMs'] == pytest.approx([16, 80, 16])
    assert result['frames']['continuousSwapCount'] == 7
    assert result['frames']['activeGapCount'] == 3
    assert result['frames']['gapsOverThreeBudgets'] == 1
    assert not result['thresholdResults']['activeFrameMax']['passed']


def test_thresholds_scale_with_refresh_rate_and_include_the_long_tail():
    commands = [command(1, 1), command(2, 2, kind='modal')]
    frames = [frame(1.020, index=1, moving=True), frame(1.030), frame(2.025, index=2)]
    at_60 = motion.analyze_timeline(commands, frames, 60)
    at_120 = motion.analyze_timeline(commands, frames, 120)
    assert at_60['thresholdResults']['navigationFirstP95']['passed']
    assert not at_120['thresholdResults']['navigationFirstP95']['passed']
    assert at_120['thresholdResults']['pageModalFirstP95']['passed']
    summary = motion.summarize_ms([1] * 99 + [900])
    assert summary['count'] == 100 and summary['p95Ms'] == 1
    assert summary['maxMs'] == 900


def test_no_frames_cannot_pass_the_active_frame_budget_and_invalid_refresh_is_rejected():
    result = motion.analyze_timeline([], [], 60)
    assert result['thresholdResults']['activeFrameP95']['status'] == 'insufficient-data'
    assert not result['thresholdResults']['activeFrameP95']['passed']
    with pytest.raises(ValueError):
        motion.analyze_timeline([], [], 0)


def test_matching_state_during_setup_or_another_scenario_cannot_credit_input():
    result = motion.analyze_timeline([command(1, 1)],
        [frame(1.010, index=1, scope=None), frame(1.020, index=1, scope='files')], 60)
    assert result['inputs'] == {'sent': 1, 'presented': 0, 'failed': 1, 'presentationRate': 0}


def test_next_gui_animation_state_cannot_replace_the_frame_already_synchronizing():
    recorder = motion.PresentationRecorder()
    old = {'stagedAt': 1.0, 'state': {'index': 1}}
    new = {'stagedAt': 1.01, 'state': {'index': 2}}
    recorder.stage(old)
    recorder.synchronize()
    recorder.stage(new)
    recorder.swap(1.02)
    recorder.synchronize()
    recorder.swap(1.03)
    assert recorder.frames == [{'at': 1.02, **old}, {'at': 1.03, **new}]


def test_continuous_idle_redraw_fails_even_when_the_other_idle_window_is_quiet():
    quiet = {'swaps': 2, 'expectedMaximumClockSwaps': 11}
    busy = {'swaps': 40, 'expectedMaximumClockSwaps': 11}
    assert motion.idle_redraw_threshold([quiet, quiet])['passed']
    result = motion.idle_redraw_threshold([quiet, busy])
    assert not result['passed']
    assert result['observedSwaps'] == [2, 40]
    assert result['maximumClockSwaps'] == [11, 11]


def test_diagnostic_stage_trace_is_opt_in_and_writes_stderr(monkeypatch, capsys):
    monkeypatch.delenv('UDECK_MOTION_TRACE', raising=False)
    motion.trace_stage('startup')
    assert capsys.readouterr().err == ''
    monkeypatch.setenv('UDECK_MOTION_TRACE', '1')
    motion.trace_stage('cleanup engine-delete')
    output = capsys.readouterr()
    assert output.out == ''
    assert 'cleanup engine-delete' in output.err


def test_power_preflight_rejects_the_probe_output_even_if_another_output_is_on():
    result = motion.analyze_output_power('DSI-1 off\nHDMI-A-1 on\n', 'DSI-1')
    assert not result['passed'] and result['status'] == 'off'
    assert result['outputs'] == {'DSI-1': 'off', 'HDMI-A-1': 'on'}
    assert motion.analyze_output_power('DSI-1 on\n', 'DSI-1')['passed']
    assert not motion.analyze_output_power('DSI-1 off\n', 'unknown')['passed']
    assert motion.analyze_output_power('', 'DSI-1')['status'] == 'unknown'


def test_input_delivery_timeout_cannot_receive_credit_from_a_matching_frame():
    item = {**command(1, 1), 'deliveryCompleted': False}
    result = motion.analyze_timeline([item], [frame(1.01, index=1)], 60)
    assert result['inputs']['failed'] == 1
    assert result['inputResults'][0]['failure'] == 'input-delivery-barrier-timeout'
