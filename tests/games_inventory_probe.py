"""Explicit installed-core inventory acceptance; loading is separate from gameplay."""

import json
import sys
import threading
import time
from pathlib import Path

from PySide6.QtCore import QCoreApplication

from udeck.apps.emulator.services import CoreInventoryTask


def run(root):
    root.mkdir(parents=True, exist_ok=True)
    application = QCoreApplication([])  # Keep Qt signal ownership alive for the probe.
    values, progress, completed = {}, [], []
    task = CoreInventoryTask(1, {}, {}, threading.Event())
    task.signals.discovered.connect(lambda generation, catalog: values.update(catalog=catalog))

    def update(generation, identifier, result):
        values["catalog"].apply_probe(identifier, result)
        progress.append(identifier)
        if len(progress) % 40 == 0:
            print(f"Checked {len(progress)} cores", flush=True)

    task.signals.progress.connect(update)
    task.signals.done.connect(lambda generation, cache: completed.append(cache))
    started = time.monotonic()
    task.run()
    application.processEvents()
    assert completed
    catalog = values["catalog"]
    report = {"installed": len(catalog.cores), "available": sum(c.status == "available" for c in catalog.cores.values()),
              "incompatible": {c.id: c.reason for c in catalog.cores.values() if c.status != "available"},
              "platforms": sum(bool(catalog.platform_cores(p)) for p in catalog.platforms),
              "unmapped": [c.id for c in catalog.cores.values() if not c.platforms],
              "seconds": round(time.monotonic() - started, 2)}
    (root / "inventory-cache.json").write_text(json.dumps(completed[0], indent=2))
    (root / "inventory-result.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report), flush=True)


if __name__ == "__main__":
    run(Path(sys.argv[1]).resolve())
