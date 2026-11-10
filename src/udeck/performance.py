"""Small, memory-only startup and activation diagnostics; never records user content."""

import os
import time
from pathlib import Path


def process_started():
    now = time.monotonic()
    try:
        fields = Path('/proc/self/stat').read_text().rsplit(')', 1)[1].split()
        ticks = int(fields[19]) / os.sysconf('SC_CLK_TCK')
        return now - (time.clock_gettime(time.CLOCK_BOOTTIME) - ticks)
    except (OSError, ValueError, AttributeError, IndexError):
        return now


class StartupTrace:
    def __init__(self, started=None, clock=time.monotonic):
        self.clock = clock
        self.started = process_started() if started is None else started
        self.stages = {}
        self.activation = {}
        self.generation = 0
        self.graphics_api = ''

    def mark(self, stage):
        self.stages.setdefault(stage, round(max(0, self.clock() - self.started), 6))

    def request_activation(self):
        self.generation += 1
        self.activation = {'generation': self.generation,
                           'requestedAt': self.clock() - self.started,
                           'toActiveMs': None, 'toFrameMs': None}

    def active_changed(self, active):
        if active and self.activation and self.activation['toActiveMs'] is None:
            self.activation['toActiveMs'] = round(
                (self.clock() - self.started - self.activation['requestedAt']) * 1000, 3)

    def frame_swapped(self):
        self.mark('firstFrame')
        if self.activation and self.activation['toFrameMs'] is None:
            self.activation['toFrameMs'] = round(
                (self.clock() - self.started - self.activation['requestedAt']) * 1000, 3)

    def snapshot(self):
        return {'clock': 'process start' if Path('/proc/self/stat').exists() else 'entry import',
                'startedAtMonotonic': self.started,
                'stages': dict(self.stages), 'activation': dict(self.activation),
                'graphicsApi': self.graphics_api}
