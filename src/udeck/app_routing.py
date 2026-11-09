"""Stable native application identities. Kept in the shell package.

SPDX-License-Identifier: GPL-2.0-or-later
"""

import hashlib
import os

APP_IDS = {name: "io.github.zhubby.uDeck." + name.title()
           for name in ("music", "video", "browser", "reader", "emulator")}
NATIVE_APPS = frozenset((*APP_IDS.values(), "io.github.zhubby.uDeck.Terminal"))


def service_name(app_id):
    identity = ("wayland:" + os.environ["WAYLAND_DISPLAY"] if os.environ.get("WAYLAND_DISPLAY")
                else "x11:" + os.environ["DISPLAY"] if os.environ.get("DISPLAY")
                else "session:" + os.environ.get("XDG_SESSION_ID", "headless"))
    return app_id + ".Session_" + hashlib.sha256(identity.encode()).hexdigest()[:16]


def object_path(app_id):
    return "/" + app_id.replace(".", "/")
