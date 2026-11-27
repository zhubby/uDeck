"""
[INPUT]: 依赖图形会话的 Wayland、X11 或会话标识。
[OUTPUT]: 提供内置应用白名单、会话 D-Bus 名和对象路径。
[POS]: 桌面与应用共用的路由身份约定。
[PROTOCOL]: Update this header on change, then check AGENTS.md

SPDX-License-Identifier: GPL-2.0-or-later
"""

import hashlib
import os

APP_IDS = {name: "io.github.zhubby.uDeck." + name.title()
           for name in ("music", "video", "browser", "reader", "emulator", "agent")}
NATIVE_APPS = frozenset((*APP_IDS.values(), "io.github.zhubby.uDeck.Terminal"))


def native_app_id(identifier):
    if not isinstance(identifier, str):
        return None
    app_id = identifier.removesuffix(".desktop")
    return app_id if app_id in NATIVE_APPS else None


def service_name(app_id):
    identity = ("wayland:" + os.environ["WAYLAND_DISPLAY"] if os.environ.get("WAYLAND_DISPLAY")
                else "x11:" + os.environ["DISPLAY"] if os.environ.get("DISPLAY")
                else "session:" + os.environ.get("XDG_SESSION_ID", "headless"))
    return app_id + ".Session_" + hashlib.sha256(identity.encode()).hexdigest()[:16]


def object_path(app_id):
    return "/" + app_id.replace(".", "/")
