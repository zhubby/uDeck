"""Compare actual small InputIcon pixels with a smooth-resampling reference."""

import json
import math
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickItem, QQuickWindow
from PySide6.QtTest import QTest


def run():
    output = Path(sys.argv[1])
    output.mkdir(parents=True, exist_ok=True)
    root = Path(__file__).resolve().parents[1]
    keys = ["gamecube_button_color_a", "gamecube_button_color_b", "gamecube_button_x",
            "gamecube_button_y", "keyboard_enter", "keyboard_escape", "keyboard_ctrl",
            "keyboard_alt", "keyboard_shift", "keyboard_space", "keyboard_tab",
            "keyboard_arrows", "gamecube_trigger_l"]
    icons = [(key, size, 20 + column * 88, 12 + row * 48)
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
         'Window { width: 1200; height: 270; visible: true; color: "#141718"\n'
         + items + '\nInputPrompt { objectName: "normalizationCombo"; x: 20; y: 220; '
         'keys: ["keyboard_ctrl", "+", "keyboard_alt", "+", "keyboard_escape"]; '
         'label: "Home"; fontFamily: Qt.application.font.family; textColor: "white" }\n}').encode(),
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
    dimensions = {}
    for key, size, x, y in icons:
        image = QImage(str(root / "src/udeck/assets/input-prompts" / (key + ".png")))
        assert not image.isNull(), key
        # Derive the reference scale from actual opaque pixels, independently
        # of the component's per-key metrics. All keyboard caps should be as
        # tall as the original square keys (96 of the 128 source pixels).
        if key.startswith("keyboard_"):
            rows = [py for py in range(image.height())
                    if any(image.pixelColor(px, py).alpha() > 128 for px in range(image.width()))]
            scale = 96 / (max(rows) - min(rows) + 1)
        else:
            scale = 1
        side = math.ceil(size * ratio * scale)
        dimensions[key, size] = side
        image = image.scaled(side, side,
                             Qt.AspectRatioMode.IgnoreAspectRatio,
                             Qt.TransformationMode.SmoothTransformation)
        top = round(y * ratio) + math.floor((size * ratio - side) / 2 + 0.5)
        painter.drawImage(round(x * ratio), top, image)
    painter.end()
    assert actual.save(str(output / "actual.png"))
    assert reference.save(str(output / "reference.png"))
    differences = []
    keyboard_height_errors = []
    for key, size, x, y in icons:
        total = 0
        ink_rows = []
        for py in range(round(y * ratio), round((y + size) * ratio)):
            row_has_ink = False
            for px in range(round(x * ratio), round(x * ratio) + dimensions[key, size]):
                left, right = actual.pixelColor(px, py), reference.pixelColor(px, py)
                total += sum(abs(a - b) for a, b in zip(left.getRgb()[:3], right.getRgb()[:3], strict=True))
                row_has_ink |= max(abs(a - b) for a, b in zip(left.getRgb()[:3], (20, 23, 24), strict=True)) > 128
            if row_has_ink:
                ink_rows.append(py)
        error = total / (round(size * ratio) * dimensions[key, size] * 3)
        differences.append({"key": key, "size": size, "meanChannelError": round(error, 4)})
        if key.startswith("keyboard_"):
            assert ink_rows, (key, size, "Missing keycap")
            height_error = abs(max(ink_rows) - min(ink_rows) + 1 - size * ratio * 0.75)
            keyboard_height_errors.append(height_error)
    combo = window.findChild(QQuickItem, "normalizationCombo")
    slots = sorted((item for item in combo.childItems() if item.width() > 0 and item.isVisible()),
                   key=lambda item: item.x())
    for previous, following in zip(slots, slots[1:], strict=False):
        assert previous.x() + previous.width() <= following.x(), "Shortcut items overlap"
    for slot in slots:
        icon = slot.findChild(QQuickItem, "inputPromptIcon")
        if icon and icon.isVisible():
            assert icon.width() <= slot.width(), "Wide keycap overflows its shortcut slot"
    report = {"devicePixelRatio": ratio, "iconsChecked": len(icons),
              "maximumMeanChannelError": max(item["meanChannelError"] for item in differences),
              "maximumKeyboardHeightError": max(keyboard_height_errors),
              "comboSpacingPreserved": True, "qmlErrors": errors}
    print(json.dumps(report), flush=True)
    assert report["maximumMeanChannelError"] < 0.8, differences
    assert report["maximumKeyboardHeightError"] <= 1, keyboard_height_errors
    window.close()
    application.processEvents()


if __name__ == "__main__":
    run()
