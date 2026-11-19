"""
[INPUT]: 依赖 Qt 焦点对象、应用控制器和输入法预编辑状态。
[OUTPUT]: 判定语义按键是否归前台输入法所有。
[POS]: 桌面与应用共用的文本输入边界。
[PROTOCOL]: Update this header on change, then check AGENTS.md
"""

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
