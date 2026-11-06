"""An original 32 KiB Game Boy program run by the installed Gambatte core.

No commercial ROM, firmware or Nintendo logo is included. This checks the
emulator/serialization path, not physical controls, audio or game compatibility.
"""

import json
import sys
import time
from pathlib import Path

import pytest
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from udeck.apps.games import RetroEngine, SaveStore, file_hash, preflight


def original_rom(path):
    rom = bytearray(32768)
    rom[0x100:0x103] = bytes.fromhex("c3 50 01")
    rom[0x134:0x13e] = b"UDECK TEST"
    # Turn LCD off, draw a striped tile, enable LCD and cycle the palette.
    code = bytes.fromhex("f3 af e0 40 3e e4 e0 47 21 00 80 3e aa 06 10 22 05 20 fc 3e 91 e0 40 0e 00 06 ff 05 20 fd 0c 79 e0 47 18 f5")
    rom[0x150:0x150+len(code)] = code
    checksum = 0
    for byte in rom[0x134:0x14d]:
        checksum = (checksum - byte - 1) & 255
    rom[0x14d] = checksum
    rom[0x14e:0x150] = (sum(rom) & 65535).to_bytes(2,"big")
    path.write_bytes(rom)


def run(root):
    root.mkdir(parents=True,exist_ok=True)
    application = QApplication([])
    path = root / "Original stripes.gb"
    original_rom(path)
    item = {"id":"original-stripes", "path":str(path.resolve()), "platform":"GB", "format":"GB"}
    checks = preflight(item,{})
    assert checks["ready"],checks
    engine=RetroEngine()
    saves=SaveStore(root/"saves")
    errors,events=[],[]
    engine.failed.connect(errors.append)
    engine.saved.connect(lambda slot:events.append("saved:"+slot))
    engine.loaded.connect(lambda:events.append("loaded"))
    def wait(condition, seconds=20):
        deadline=time.monotonic()+seconds
        while not condition() and not errors and time.monotonic()<deadline:
            application.processEvents()
            QTest.qWait(15)
        if not condition() or errors:
            (root/"retroarch.log").write_text(engine.log)
            print(json.dumps({"status":engine.status,"errors":errors,"log":engine.log[-4500:]}),flush=True)
            if engine.running():
                engine.quit()
                engine.process.waitForFinished(3000)
            raise AssertionError("Native game operation failed")
    engine.start(item,checks,saves)
    wait(lambda:engine.status=="playing")
    for _ in range(20):
        application.processEvents()
        QTest.qWait(15)
    engine.pause()
    wait(lambda:engine.status=="paused")
    engine.save("1")
    with pytest.raises(RuntimeError, match="wait for the current operation"):
        engine.resume()
    wait(lambda:"saved:1" in events)
    state,metadata=saves.load("1",file_hash(path),file_hash(checks["core"]))
    assert state.stat().st_size>1000
    engine.resume()
    wait(lambda:engine.status=="playing")
    engine.pause()
    wait(lambda:engine.status=="paused")
    engine.load("1")
    with pytest.raises(RuntimeError, match="wait for the current operation"):
        engine.resume()
    wait(lambda:"loaded" in events)
    engine.save("auto")
    wait(lambda:"saved:auto" in events)
    assert set(saves.manifest())=={"1","auto"}
    engine.quit()
    wait(lambda:not engine.running())
    engine.start(item,checks,saves,resume=True)
    events.remove("loaded")
    wait(lambda:"loaded" in events and engine.status=="paused")
    engine.quit()
    wait(lambda:not engine.running())
    events.append("automatic-resume-after-process-restart")
    (root/"retroarch.log").write_text(engine.log)
    print(json.dumps({"engine":"RetroArch/Gambatte","stateBytes":state.stat().st_size,
                      "events":events,"errors":errors,"thumbnail":metadata["thumbnail"]}),flush=True)
    engine.close()


if __name__=="__main__":
    run(Path(sys.argv[1]))
