"""
[INPUT]: 依赖隔离桌面控制器、真实弹窗与启动遮罩。
[OUTPUT]: 验证退出画面、请求替换及尺寸过渡中途关闭。
[POS]: 动画连续性的独立进程探针，不连接设备服务。
[PROTOCOL]: Update this header on change, then check AGENTS.md
"""

import json
import os
import sys
from pathlib import Path

from PySide6.QtCore import QObject, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtTest import QTest
from shiboken6 import delete

from udeck import main
from udeck.controller import ShellController
from udeck.core import ConfigStore
from udeck.mock import MockBackend


def run():
    output, scenario, theme, reduced = sys.argv[1:]
    application = QGuiApplication([])
    controller = ShellController(MockBackend(), config=ConfigStore(Path(output) / "settings.json"), mock=True)
    controller.setLanguage("en")
    controller.setTheme(theme)
    reduced = reduced == "1"
    engine = QQmlApplicationEngine()
    errors = []
    engine.warnings.connect(lambda warnings: errors.extend(w.toString() for w in warnings))
    engine.addImageProvider("desktop", main.IconProvider())
    for name, value in (("controller", controller), ("windowedPreview", True), ("headlessPreview", True)):
        engine.rootContext().setContextProperty(name, value)
    engine.load(QUrl.fromLocalFile(str(Path(main.__file__).parent / "qml/Main.qml")))
    assert engine.rootObjects(), errors
    window = engine.rootObjects()[0]

    def item(name):
        result = window.findChild(QObject, name)
        assert result is not None, name
        return result

    def publish_launch():
        controller._refresh_launch()
        controller._publish()
        application.processEvents()
        QTest.qWait(2)

    try:
        QTest.qWait(200)
        if scenario == "loading":
            now = [0.0]
            controller.launches.clock = lambda: now[0]
            first = {"id": "first", "name": "First request", "icon": "utilities-terminal"}
            token, _ = controller.launches.begin(first, observable=True)
            now[0] = 0.3
            publish_launch()
            QTest.qWait(180)
            overlay = item("appLaunchOverlay")
            title = overlay.findChild(QObject, "loadingTitle")
            assert title.property("text") == "First request"
            controller.launches.finish(token)
            publish_launch()
            if not reduced:
                assert overlay.property("visible") and overlay.property("opacity") > 0
                assert title.property("text") == "First request", "closing overlay discarded its title"
                assert overlay.findChild(QObject, "loadingMessage").property("text"), "closing overlay discarded its message"
            next_token, _ = controller.launches.begin({"id": "next", "name": "Next request"}, observable=True)
            now[0] = 0.6
            publish_launch()
            QTest.qWait(150)
            assert title.property("text") == "Next request", "new request reused the outgoing title"
            assert overlay.property("shown") and overlay.property("opacity") == 1
            overlay.setProperty("immediateHide", True)
            application.processEvents()
            assert not overlay.property("visible"), "foreground handoff waited for loading fade"
            controller.launches.finish(next_token)
            publish_launch()
        elif scenario == "first-open":
            controller._menu("First menu", [{"label": f"Option {index}", "action": "unused"} for index in range(5)])
            application.processEvents()
            QTest.qWait(2)
            panel = item("dialogPanel")
            assert panel.width() > 0 and panel.height() > 0
            assert abs(panel.height() - panel.property("targetHeight")) < 1, "first opening resized from hidden placeholder"
        elif scenario == "mid-close":
            controller._menu("Short menu", [{"label": "One", "action": "unused"}])
            QTest.qWait(200)
            shade, panel = item("modalShade"), item("dialogPanel")
            controller._menu("Long menu", [{"label": f"Option {index}", "action": "unused"} for index in range(5)])
            QTest.qWait(35)
            before_close = panel.height()
            before_target = panel.property("targetHeight")
            if not reduced:
                assert before_close < panel.property("targetHeight") - 5
            closing_geometry = []
            shade.shownChanged.connect(lambda: closing_geometry.append(panel.height()) if not shade.property("shown") else None)
            controller.dispatch("back")
            controller.dispatch("back")
            application.processEvents()
            QTest.qWait(2)
            if not reduced:
                assert shade.property("visible") and shade.property("opacity") > 0
                assert closing_geometry, "closing state was not observed"
                retained_height = closing_geometry[-1]
                assert retained_height < before_target - 5
                assert abs(panel.height() - retained_height) < 1, ("closing resize jumped to target geometry", before_close, retained_height, panel.height())
                QTest.qWait(30)
                assert abs(panel.height() - retained_height) < 1, "closing panel changed retained geometry"
            else:
                assert not shade.property("visible")
            controller._menu("Reopened menu", [{"label": "Latest", "action": "unused"}])
            application.processEvents()
            QTest.qWait(2)
            assert abs(panel.height() - panel.property("targetHeight")) < 1
            QTest.qWait(180)
            assert shade.property("shown") and shade.property("opacity") == 1
        else:
            controller._menu("Short menu", [{"label": "One", "action": "unused"}])
            QTest.qWait(200)
            shade, panel = item("modalShade"), item("dialogPanel")
            start_height = panel.height()
            controller._menu("Long menu", [{"label": f"Option {index}", "action": "unused"} for index in range(5)])
            application.processEvents()
            QTest.qWait(2)
            first_height = panel.height()
            QTest.qWait(35)
            middle_height = panel.height()
            QTest.qWait(160)
            final_height = panel.height()
            assert final_height > start_height + 80
            if not reduced:
                assert first_height < final_height - 1, "submenu snapped to final height"
                assert start_height < middle_height < final_height, "submenu has no intermediate geometry"
            else:
                assert abs(first_height - final_height) < 1
            assert shade.property("opacity") == 1, "submenu restarted the scrim"
            controller.dispatch("back")
            QTest.qWait(20)
            controller._menu("Newest menu", [{"label": "Latest", "action": "unused"}])
            QTest.qWait(180)
            assert shade.property("shown") and shade.property("opacity") == 1
            assert shade.property("dialog").toVariant()["title"] == "Newest menu"
            controller.dispatch("back")
            controller.dispatch("back")
            application.processEvents()
            if not reduced:
                os.environ["UDECK_REDUCED_MOTION"] = "1"
                controller._publish()
                application.processEvents()
                assert not shade.property("visible"), "reduced motion left a closing dialog"
        assert not errors, errors
        print(json.dumps({"scenario": scenario, "qmlErrors": errors, "passed": True}))
    finally:
        delete(engine)
        controller.close()
        application.processEvents()


if __name__ == "__main__":
    run()
