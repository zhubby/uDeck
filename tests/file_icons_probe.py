import hashlib
import json
import sys
from pathlib import Path

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QGuiApplication, QImage, QPainter

from udeck.file_icons import EXTENSION_GROUPS, FILE_ICON_PREFIX, ICON_PALETTES, ICON_SPECS
from udeck.main import IconProvider

output = Path(sys.argv[1])
output.mkdir(parents=True, exist_ok=True)
application = QGuiApplication([])
font_root = Path(__file__).resolve().parents[1] / "src/udeck/fonts"
for font in font_root.glob("*.ttf"):
    QFontDatabase.addApplicationFont(str(font))
provider = IconProvider()


def fail_fallback(name, dimension):
    raise AssertionError(f"Bundled SVG failed to render: {name} at {dimension}px")


provider._draw = fail_fallback
images, fingerprints = {}, {}
sizes = [48, 80, 144]
for category, (_asset, palette) in ICON_SPECS.items():
    for dimension in sizes:
        reported = QSize()
        rendered = provider.requestImage(FILE_ICON_PREFIX + category, reported, QSize(dimension, dimension))
        assert not rendered.isNull()
        assert reported == QSize(dimension, dimension)
        assert rendered.pixelColor(0, 0).alpha() == 0
        pixels = bytes(rendered.constBits())
        foreground = QColor(ICON_PALETTES[palette][1]).rgba().to_bytes(4, sys.byteorder)
        assert foreground in pixels, (category, dimension)
        fingerprints[category, dimension] = hashlib.sha256(pixels).hexdigest()
        if dimension == 80:
            images[category] = rendered

for first, second in (("pdf", "wordx"), ("jpeg", "png"), ("code", "json"), ("audio", "video"), ("archive", "zip"), ("font", "unknown")):
    assert fingerprints[first, 80] != fingerprints[second, 80]
reported = QSize()
unknown = provider.requestImage(FILE_ICON_PREFIX + "../../outside", reported, QSize(80, 80))
assert unknown == images["unknown"]

columns, cell_width, cell_height = 10, 144, 136
rows = (len(images) + columns - 1) // columns
sheet = QImage(columns * cell_width, 100 + rows * cell_height + 40, QImage.Format.Format_RGB32)
sheet.fill(QColor("#151719"))
painter = QPainter(sheet)
painter.setPen(QColor("#F1EEE7"))
painter.setFont(QFont("LXGW WenKai Screen", 24))
painter.drawText(QRect(24, 16, sheet.width() - 48, 38), Qt.AlignmentFlag.AlignVCenter, "uDeck · Tabler 文件类型图标")
painter.setPen(QColor("#B5BCBF"))
painter.setFont(QFont("LXGW WenKai Screen", 14))
painter.drawText(QRect(24, 55, sheet.width() - 48, 30), Qt.AlignmentFlag.AlignVCenter,
                 f"Tabler 3.51.0 · MIT · {len(images)} 类图标 · 本地离线渲染")
for index, (category, icon) in enumerate(images.items()):
    x_position = index % columns * cell_width
    y_position = 100 + index // columns * cell_height
    painter.drawImage(x_position + (cell_width - 80) // 2, y_position, icon)
    painter.setFont(QFont("LXGW WenKai Screen", 12 if len(category) > 9 else 14))
    painter.setPen(QColor("#F1EEE7"))
    painter.drawText(QRect(x_position, y_position + 83, cell_width, 22), Qt.AlignmentFlag.AlignCenter, category.upper())
    suffixes = EXTENSION_GROUPS.get(category, "").split()[:2]
    painter.setFont(QFont("LXGW WenKai Screen", 12))
    painter.setPen(QColor("#B5BCBF"))
    label = " / ".join("." + suffix for suffix in suffixes) or ("文件夹" if category == "folder" else "未识别类型")
    label = painter.fontMetrics().elidedText(label, Qt.TextElideMode.ElideMiddle, cell_width - 12)
    painter.drawText(QRect(x_position, y_position + 106, cell_width, 20), Qt.AlignmentFlag.AlignCenter, label)
painter.end()
assert sheet.save(str(output / "file-icons.png"))
print(json.dumps({"sizes": sizes, "allRendered": True, "categories": len(images)}))
