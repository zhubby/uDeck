"""Compare actual small InputIcon pixels with a smooth-resampling reference."""

import json
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow
from PySide6.QtTest import QTest


def run():
    output = Path(sys.argv[1])
    output.mkdir(parents=True, exist_ok=True)
    root = Path(__file__).resolve().parents[1]
    keys = ["gamecube_button_color_a", "gamecube_button_color_b", "gamecube_button_x",
            "gamecube_button_y", "keyboard_enter", "keyboard_arrows", "gamecube_trigger_l"]
    icons = [(key, size, 20 + column * 80, 12 + row * 48)
             for row, size in enumerate((24, 28, 32, 36)) for column, key in enumerate(keys)]
    items = "\n".join(
        f'InputIcon {{ x: {x}; y: {y}; iconSize: {size}; keyId: "{key}" }}'
        for key, size, x, y in icons
    )
    application = QGuiApplication([])
    engine = QQmlApplicationEngine()
    errors = []
    engine.warnings.connect(lambda warnings: errors.extend(error.toString() for error in warnings))
    engine.loadData(
        ('import QtQuick\nimport QtQuick.Window\n'
         'Window { width: 600; height: 200; visible: true; color: "#141718"\n'
         + items + '\n}').encode(),
        QUrl.fromLocalFile(str(root / "src/udeck/qml/input_probe.qml")),
    )
    assert engine.rootObjects(), errors
    window = engine.rootObjects()[0]
    assert isinstance(window, QQuickWindow)
    QTest.qWait(100)
    actual = window.grabWindow().convertToFormat(QImage.Format.Format_RGB32)
    ratio = window.devicePixelRatio()
    assert not actual.isNull() and not errors, errors
    assert actual.size().width() == round(window.width() * ratio)
    reference = QImage(actual.size(), QImage.Format.Format_RGB32)
    reference.fill(QColor("#141718"))
    painter = QPainter(reference)
    for key, size, x, y in icons:
        image = QImage(str(root / "src/udeck/assets/input-prompts" / (key + ".png")))
        assert not image.isNull(), key
        image = image.scaled(round(size * ratio), round(size * ratio),
                             Qt.AspectRatioMode.IgnoreAspectRatio,
                             Qt.TransformationMode.SmoothTransformation)
        painter.drawImage(round(x * ratio), round(y * ratio), image)
    painter.end()
    assert actual.save(str(output / "actual.png"))
    assert reference.save(str(output / "reference.png"))
    differences = []
    for key, size, x, y in icons:
        total = 0
        for py in range(round(y * ratio), round((y + size) * ratio)):
            for px in range(round(x * ratio), round((x + size) * ratio)):
                left, right = actual.pixelColor(px, py), reference.pixelColor(px, py)
                total += sum(abs(a - b) for a, b in zip(left.getRgb()[:3], right.getRgb()[:3], strict=True))
        error = total / (round(size * ratio) ** 2 * 3)
        differences.append({"key": key, "size": size, "meanChannelError": round(error, 4)})
    report = {"devicePixelRatio": ratio, "iconsChecked": len(icons),
              "maximumMeanChannelError": max(item["meanChannelError"] for item in differences),
              "qmlErrors": errors}
    print(json.dumps(report), flush=True)
    assert report["maximumMeanChannelError"] < 0.8, differences
    window.close()
    application.processEvents()


if __name__ == "__main__":
    run()
