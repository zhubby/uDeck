#!/usr/bin/env python3
"""Supply desktop activation on a private test bus, for uniquely tagged test windows."""

import argparse
import json
import signal
import time
from pathlib import Path

from PySide6.QtCore import ClassInfo, QCoreApplication, QObject, QTimer, Slot
from PySide6.QtDBus import QDBusConnection

from udeck.app_routing import NATIVE_APPS
from udeck.windows import WindowService


@ClassInfo(**{'D-Bus Interface': 'io.github.zhubby.uDeck.Control'})
class ActivationBridge(QObject):
    def __init__(self, windows, token):
        super().__init__()
        self.windows = windows
        self.token = token
        self.excluded = {entry['id'] for entry in windows.entries()}
        self.pending = {}
        self.timer = QTimer(self)
        self.timer.setInterval(10)
        self.timer.timeout.connect(self.activate_pending)
        windows.changed.connect(self.activate_pending)

    @Slot(str, result=str)
    def ActivateNativeApp(self, app_id):
        if app_id not in NATIVE_APPS:
            return 'Not a native application'
        self.pending[app_id] = time.monotonic() + 1
        self.timer.start()
        self.activate_pending()
        return ''

    def activate_pending(self, *_args):
        entries = self.windows.entries()
        for app_id, deadline in list(self.pending.items()):
            candidates = [entry for entry in entries if entry['id'] not in self.excluded
                          and entry['appId'] == app_id and self.token in entry['name']]
            if len(candidates) == 1:
                self.windows.request(candidates[0]['id'], 'activate')
                del self.pending[app_id]
            elif len(candidates) > 1 or time.monotonic() >= deadline:
                print(json.dumps({'activationRejected': app_id, 'matches': len(candidates)}), flush=True)
                del self.pending[app_id]
        if not self.pending:
            self.timer.stop()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--token', required=True)
    parser.add_argument('--ready', required=True, type=Path)
    options = parser.parse_args()
    if not options.token.startswith('udeck-perf-') or len(options.token) < 24:
        parser.error('Use a unique udeck-perf- token, also appended to the test window titles')
    application = QCoreApplication([])
    windows = WindowService()
    windows.start()
    if not windows.available:
        raise RuntimeError('Wayland foreign-toplevel activation is unavailable')
    bridge = ActivationBridge(windows, options.token)
    bus = QDBusConnection.sessionBus()
    if not bus.registerService('io.github.zhubby.uDeck'):
        raise RuntimeError('The private test bus already has a desktop service; refusing to continue')
    if not bus.registerObject('/io/github/zhubby/uDeck', 'io.github.zhubby.uDeck.Control',
                              bridge, QDBusConnection.RegisterOption.ExportAllSlots):
        raise RuntimeError('Cannot register the private activation bridge')
    signal.signal(signal.SIGTERM, lambda *_args: application.quit())
    heartbeat = QTimer()
    heartbeat.start(200)
    heartbeat.timeout.connect(lambda: None)
    options.ready.write_text(json.dumps({'ready': True, 'excludedWindowCount': len(bridge.excluded)}))
    try:
        application.exec()
    finally:
        windows.close()


if __name__ == '__main__':
    main()
