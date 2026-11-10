#!/usr/bin/env python3
"""Compare controller updates with synthetic libraries; excludes QML parsing/rendering."""

import argparse
import json
import math
import statistics
import tempfile
import time
from pathlib import Path

from PySide6.QtCore import QCoreApplication

from udeck.apps.common.controller import AppController


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--items', nargs='+', type=int, default=[100, 1000, 10000])
    parser.add_argument('--samples', type=int, default=100)
    options = parser.parse_args()
    if options.samples < 1 or any(count < 1 for count in options.items):
        parser.error('Library sizes and sample count must be positive')
    application = QCoreApplication([])
    reports = []
    with tempfile.TemporaryDirectory(prefix='udeck-state-benchmark-') as directory:
        controller = AppController('reader', directory, Path(directory) / 'settings.json')
        try:
            compact = hasattr(type(controller), 'viewSnapshotJson')
            for count in options.items:
                controller.library.items = [{
                    'id': str(index), 'sourceId': 'synthetic-books', 'title': f'Original synthetic book {index}',
                    'format': 'PDF', 'folder': '/synthetic/Books', 'path': f'/synthetic/Books/Book {index}.pdf',
                    'stamp': [1048576, 1700000000000000000], 'cover': '', 'artist': '', 'album': '',
                    'metadata': 'Synthetic metadata for repeatable application state measurements.'
                } for index in range(count)]
                controller.publish()
                samples = []
                for index in range(options.samples):
                    started = time.perf_counter()
                    controller.select(str(index % count))
                    payload = controller.viewSnapshotJson if compact else controller.snapshotJson
                    samples.append((time.perf_counter() - started) * 1000)
                ordered = sorted(samples)
                reports.append({'items': count, 'samples': len(samples), 'compactView': compact,
                    'payloadBytes': len(payload.encode()), 'medianMs': statistics.median(samples),
                    'p95Ms': ordered[math.ceil(len(ordered) * .95) - 1]})
        finally:
            controller.close()
    print(json.dumps({'qmlParsingAndRenderingIncluded': False, 'updates': reports}, indent=2))
    assert application


if __name__ == '__main__':
    main()
