import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from PySide6.QtCore import QCoreApplication
from PySide6.QtDBus import QDBusConnection, QDBusInterface, QDBusMessage

from udeck.cli import INTERFACE, OBJECT, SERVICE


def main():
    parser = argparse.ArgumentParser(description="Measure a safe, real windowed shell without opening input devices")
    parser.add_argument("--seconds", type=float, default=20)
    parser.add_argument("--output", type=Path)
    options = parser.parse_args()
    application = QCoreApplication([])
    bus = QDBusConnection.sessionBus()
    if not bus.isConnected() or QDBusInterface(SERVICE, OBJECT, INTERFACE, bus).isValid():
        parser.error("A session bus and no existing uDeck shell are required")
    started = time.monotonic()
    process = subprocess.Popen(
        [sys.executable, "-m", "udeck.main", "--windowed", "--no-input",
         "--quit-after", str(options.seconds + 12)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )

    def diagnose():
        interface = QDBusInterface(SERVICE, OBJECT, INTERFACE, bus)
        if interface.isValid():
            response = interface.call("Diagnose")
            if response.type() != QDBusMessage.MessageType.ErrorMessage:
                return json.loads(response.arguments()[0])
        return {}

    def usage():
        fields = Path(f"/proc/{process.pid}/stat").read_text().split(") ", 1)[1].split()
        ticks = int(fields[11]) + int(fields[12])
        rss = next(line.split()[1] for line in Path(f"/proc/{process.pid}/status").read_text().splitlines() if line.startswith("VmRSS:"))
        return ticks, int(rss) / 1024

    try:
        report = {}
        while time.monotonic() - started < 10:
            application.processEvents()
            report = diagnose()
            if report.get("firstFrameSeconds") is not None:
                break
            if process.poll() is not None:
                raise RuntimeError("Shell exited before first frame")
            time.sleep(0.1)
        if report.get("firstFrameSeconds") is None:
            raise RuntimeError("No first frame within 10 seconds")
        launch_to_ready = time.monotonic() - started
        time.sleep(3)
        before, rss = usage()
        interval_started = time.monotonic()
        samples = [rss]
        for _sample in range(max(1, round(options.seconds))):
            time.sleep(1)
            ticks, rss = usage()
            samples.append(rss)
        elapsed = time.monotonic() - interval_started
        report = diagnose() | {
            "measurementMode": "real-windowed-no-input", "launchToReadySeconds": round(launch_to_ready, 3),
            "idleSampleSeconds": round(elapsed, 3),
            "idleCpuPercentOneCore": round((ticks - before) / os.sysconf("SC_CLK_TCK") / elapsed * 100, 3),
            "rssMiB": round(samples[-1], 2), "peakSampledRssMiB": round(max(samples), 2),
        }
        report["targetsMet"] = report["launchToReadySeconds"] <= 5 and report["firstFrameSeconds"] <= 5 and report["peakSampledRssMiB"] <= 250 and report["idleCpuPercentOneCore"] <= 3
        result = process.wait(timeout=15)
        output, errors = process.communicate()
        report["exitCode"] = result
        report["warnings"] = (output + errors).strip().splitlines()
        encoded = json.dumps(report, ensure_ascii=False, indent=2)
        print(encoded)
        if options.output:
            options.output.parent.mkdir(parents=True, exist_ok=True)
            options.output.write_text(encoded + "\n")
        return 0 if result == 0 and report["targetsMet"] else 1
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=5)


if __name__ == "__main__":
    raise SystemExit(main())
