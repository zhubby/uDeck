from udeck.i18n import render
from udeck.launch import LaunchTracker

APP = {"id": "org.example.Reader.desktop", "name": "Reader", "icon": "book"}
OTHER = {"id": "org.example.Music.desktop", "name": "Music", "icon": "music"}


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def tracker():
    clock = Clock()
    return LaunchTracker(clock=clock), clock


def test_launch_waits_for_window_instead_of_command_return():
    launches, clock = tracker()
    token, created = launches.begin(APP, observable=True)
    assert created
    assert launches.snapshot()["pending"]
    assert not launches.snapshot()["visible"]
    launches.submitted(token)
    clock.now = 0.18
    assert launches.snapshot()["visible"]
    launches.windows_changed([{"appId": "org.example.Reader", "active": False}])
    assert launches.snapshot()["pending"]
    launches.windows_changed([{"appId": "org.example.Reader", "active": True}])
    assert not launches.snapshot()["pending"]


def test_fast_window_never_displays_overlay():
    launches, clock = tracker()
    launches.begin(APP, observable=True)
    clock.now = 0.05
    launches.windows_changed([{"appId": "org.example.Reader", "active": True}])
    clock.now = 0.2
    assert not launches.snapshot()["visible"]


def test_window_before_submission_callback_does_not_end_next_launch():
    launches, clock = tracker()
    first, _ = launches.begin(APP, observable=True)
    launches.windows_changed([{"appId": "org.example.Reader", "active": True}])
    second, _ = launches.begin(OTHER, observable=True)
    launches.submitted(first)
    launches.fail(first, RuntimeError("old error"))
    clock.now = 0.3
    assert launches.snapshot()["requestId"] == second
    assert launches.snapshot()["visible"]


def test_dismiss_preserves_pending_request_and_duplicate_does_not_restart():
    launches, clock = tracker()
    token, _ = launches.begin(APP, observable=True)
    clock.now = 0.3
    launches.dismiss()
    assert not launches.snapshot()["pending"]
    repeated, created = launches.begin(APP, observable=True)
    assert not created
    assert repeated == token
    assert launches.snapshot()["visible"]


def test_old_background_window_and_timeout_cannot_clear_new_overlay():
    launches, clock = tracker()
    launches.begin(APP, observable=True)
    launches.dismiss()
    clock.now = 1
    token, _ = launches.begin(OTHER, observable=True)
    launches.windows_changed([{"appId": "org.example.Reader", "active": True}])
    clock.now = 8.1
    assert launches.snapshot()["requestId"] == token
    assert render(launches.snapshot()["message"], "zh_CN") == "正在打开应用…"
    clock.now = 9
    assert render(launches.snapshot()["message"], "zh_CN") == "仍在等待应用窗口…"


def test_unrelated_title_or_child_window_does_not_finish_request():
    launches, _clock = tracker()
    launches.begin(APP, observable=True)
    launches.windows_changed([
        {"appId": "org.example.Unrelated", "name": "Reader", "active": True},
        {"appId": "org.example.Reader", "active": True, "parent": True},
    ])
    assert launches.snapshot()["pending"]


def test_startup_wm_class_and_desktop_identity_match_without_title_guessing():
    launches, _clock = tracker()
    launches.begin({**APP, "startupWMClass": "ExampleReader"}, observable=True)
    launches.windows_changed([{"appId": "examplereader", "active": True}])
    assert not launches.snapshot()["pending"]


def test_observable_launch_times_out_without_claiming_failure():
    launches, clock = tracker()
    token, _ = launches.begin(APP, observable=True)
    launches.submitted(token)
    clock.now = 8
    assert render(launches.snapshot()["message"], "zh_CN") == "仍在等待应用窗口…"
    clock.now = 20
    notices = launches.advance(observable=True)
    assert len(notices) == 1
    assert "尚未检测到应用窗口" in render(notices[0], "zh_CN")
    assert not launches.snapshot()["pending"]
    assert launches.advance(observable=True) == []


def test_unobservable_fallback_is_measured_from_submission():
    launches, clock = tracker()
    token, _ = launches.begin(APP, observable=False)
    clock.now = 3
    assert launches.advance(observable=False) == []
    launches.submitted(token)
    clock.now = 5.49
    assert launches.advance(observable=False) == []
    clock.now = 5.5
    notices = launches.advance(observable=False)
    assert len(notices) == 1
    assert "已发送启动请求" in render(notices[0], "zh_CN")
    assert not launches.snapshot()["pending"]


def test_protocol_loss_degrades_to_neutral_submission_notice():
    launches, clock = tracker()
    token, _ = launches.begin(APP, observable=True)
    launches.submitted(token)
    clock.now = 3
    notices = launches.advance(observable=False)
    assert "已发送启动请求" in render(notices[0], "zh_CN")
    assert not launches.snapshot()["pending"]


def test_losing_foreground_dismisses_without_later_reopening():
    launches, clock = tracker()
    token, _ = launches.begin(APP, observable=True)
    launches.foreground_changed(False)
    clock.now = 1
    launches.foreground_changed(True)
    assert not launches.snapshot()["visible"]
    assert launches.begin(APP, observable=True) == (token, False)


def test_launch_failure_is_named_and_only_finishes_its_request():
    launches, clock = tracker()
    first, _ = launches.begin(APP, observable=True)
    launches.dismiss()
    second, _ = launches.begin(OTHER, observable=True)
    notice = launches.fail(first, RuntimeError("permission denied"))
    assert "Reader" in render(notice, "en")
    assert "permission denied" in render(notice, "en")
    clock.now = 1
    assert launches.snapshot()["requestId"] == second
    assert launches.snapshot()["visible"]


def test_dismissed_request_timeout_cannot_clear_newer_overlay():
    launches, clock = tracker()
    launches.begin(APP, observable=True)
    launches.dismiss()
    clock.now = 1
    token, _ = launches.begin(OTHER, observable=True)
    clock.now = 20
    notices = launches.advance(observable=True)
    assert len(notices) == 1
    assert "Reader" in render(notices[0], "en")
    assert launches.snapshot()["requestId"] == token
    assert launches.snapshot()["visible"]
