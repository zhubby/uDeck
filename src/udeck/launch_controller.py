from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PySide6.QtCore import QTimer

from .i18n import error_text, tr
from .launch import LaunchTracker
from .mock import mock_apps


class LaunchControls:
    def _init_loading(self, defer_startup):
        self.startup = {"active": defer_startup, "phase": "preparing" if defer_startup else "complete"}
        self.launches = LaunchTracker()
        self.app_launch = self.launches.snapshot()
        self.launch_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="udeck-launch")
        self._launch_closing = False
        self.launchFinished.connect(self._launch_finished)
        self.startupLoaded.connect(self._startup_loaded)
        self.launch_timer = QTimer(self)
        self.launch_timer.setInterval(50)
        self.launch_timer.timeout.connect(self._advance_launches)

    def _startup_frame(self):
        if not self.startup["active"] or self._launch_closing:
            return
        if self.startup["phase"] == "preparing":
            self.startup["phase"] = "scanning"
            QTimer.singleShot(0, self._load_startup)
        elif self.startup["phase"] == "ready":
            self.startup = {"active": False, "phase": "complete"}
            self._publish()

    def _load_startup(self):
        if self._launch_closing:
            return

        def complete(future):
            try:
                result = (future.result(), None)
            except Exception as error:
                result = ([], error)
            if not self._launch_closing:
                self.startupLoaded.emit(result)

        self.launch_executor.submit(mock_apps if self.mock else self.catalog.entries).add_done_callback(complete)

    def _complete_startup(self, result):
        if self._launch_closing:
            return
        self.applications, error = result
        self.startup["phase"] = "ready"
        if error:
            self.notify(tr("Could not read the application list: {error}", error=error_text(error)))
        if not self.mock:
            self._browse(Path.home())
        self._publish()

    def _window_observable(self):
        return self.mock or bool(self.window_service and self.window_service.available)

    def _refresh_launch(self):
        self.app_launch = self.launches.snapshot()
        if self.launches.requests:
            if not self.launch_timer.isActive():
                self.launch_timer.start()
        else:
            self.launch_timer.stop()

    def _start_application(self, item):
        if self._launch_closing:
            return
        token, created = self.launches.begin(item, observable=self._window_observable())
        self._refresh_launch()
        self._publish()
        if not created:
            return
        if self.mock:
            self.config.remember(item["id"])
            self.launches.submitted(token)

            def preview_finished():
                if not self._launch_closing:
                    self.launches.finish(token)
                    self._refresh_launch()
                    self._publish()

            QTimer.singleShot(650, self, preview_finished)
            return

        def complete(future):
            try:
                future.result()
                error = None
            except Exception as failure:
                error = failure
            if not self._launch_closing:
                self.launchFinished.emit((token, item["id"], error))

        self.launch_executor.submit(lambda: self.catalog.launch(item["id"])).add_done_callback(complete)

    def _complete_launch(self, result):
        if self._launch_closing:
            return
        token, identifier, error = result
        notice = None
        if error:
            notice = self.launches.fail(token, error)
        else:
            self.launches.submitted(token)
            try:
                self.config.remember(identifier)
            except OSError as failure:
                notice = tr('操作已执行，但更新状态失败：{value0}', value0=failure)
        self._refresh_launch()
        if notice:
            self.notify(notice)
        else:
            self._publish()

    def _advance_launches(self):
        previous = self.app_launch
        notices = self.launches.advance(observable=self._window_observable())
        self._refresh_launch()
        if notices:
            for notice in notices:
                self.notify(notice)
        elif previous != self.app_launch:
            self._publish()

    def _dismiss_launch(self):
        self.launches.dismiss()
        self._refresh_launch()
        self._publish()

    def _close_loading(self):
        self._launch_closing = True
        self.launch_timer.stop()
        self.launches.requests.clear()
        self.launches.dismiss()
        self.launch_executor.shutdown(wait=False, cancel_futures=True)
