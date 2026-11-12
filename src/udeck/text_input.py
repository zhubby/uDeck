"""Keep native button actions inside the foreground text input's ownership."""

from PySide6.QtCore import QCoreApplication


def composing_action_blocked(controller, action):
    if action not in {"accept", "back", "up", "down", "left", "right", "previous-page",
                      "next-page", "previous-tab", "next-tab"}:
        return False
    application = QCoreApplication.instance()
    if application is None or not hasattr(application, "focusObject"):
        return False
    focused_input = application.focusObject()
    return bool(focused_input and focused_input.property("inputController") is controller
                and focused_input.property("inputMethodComposing"))
