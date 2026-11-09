"""Check installed launchers and session identities with an independent D-Bus client."""

import ast
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path


def main(app, directory):
    directory.mkdir(parents=True, exist_ok=True)
    identifier = "io.github.zhubby.uDeck." + app.title()
    session = "udeck-package-ipc"
    service = identifier + ".Session_" + hashlib.sha256(("session:" + session).encode()).hexdigest()[:16]
    env = {**os.environ, "XDG_SESSION_ID": session,
           "XDG_CONFIG_HOME": str(directory / "config"), "XDG_DATA_HOME": str(directory / "data")}
    env.pop("DISPLAY", None)
    env.pop("WAYLAND_DISPLAY", None)
    with (directory / "application.log").open("w") as log:
        process = subprocess.Popen(["udeck-" + app, "--no-input", "--windowed", "--quit-after", "6"],
                                   env=env, stdout=log, stderr=log)
        try:
            deadline = time.monotonic() + 15
            while True:
                response = subprocess.run(
                    ["gdbus", "call", "--session", "--dest", service, "--object-path",
                     "/" + identifier.replace(".", "/"), "--method", identifier + ".Control.Diagnose"],
                    env=env, text=True, capture_output=True, timeout=5)
                if response.returncode == 0:
                    break
                assert process.poll() is None, (directory / "application.log").read_text()
                assert time.monotonic() < deadline, response.stderr
                time.sleep(0.1)
            report = json.loads(ast.literal_eval(response.stdout)[0])
            assert report["app"] == app and report["state"]["app"] == app
            assert report["qmlErrors"] == []
            second = subprocess.run(["udeck-app", app, "--doctor"], env=env, text=True,
                                    capture_output=True, check=True, timeout=10)
            assert json.loads(second.stdout)["app"] == app
            subprocess.run(["udeck-" + app, "--no-input", "--windowed"], env=env,
                           capture_output=True, check=True, timeout=10)
            assert process.poll() is None, "Second launcher replaced the running application"
            assert process.wait(timeout=15) == 0, (directory / "application.log").read_text()
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=10)
    print(json.dumps({"app": app, "service": service, "installedIPC": "passed"}))


if __name__ == "__main__":
    main(sys.argv[1], Path(sys.argv[2]))
