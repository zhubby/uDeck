"""Application settings keep their own artwork when desktop themes change."""

import hashlib
from pathlib import Path

from PySide6.QtCore import QObject, QUrl
from PySide6.QtGui import QColor, QIcon, QImage
from PySide6.QtQml import QQmlExpression
from PySide6.QtQuick import QQuickView
from PySide6.QtTest import QTest
from shiboken6 import delete

from udeck.icons import IconProvider

ICONS = ("audio-card", "media-playlist-repeat", "folder", "window-close", "zoom-in", "zoom-out")
ROW = Path(__file__).resolve().parents[1] / "src/udeck/qml/SettingsRow.qml"


def theme(directory, name, color=None):
    root = directory / name
    icons = root / "64x64/apps"
    icons.mkdir(parents=True)
    (root / "index.theme").write_text(
        f"[Icon Theme]\nName={name}\nDirectories=64x64/apps\n"
        "[64x64/apps]\nSize=64\nType=Fixed\nContext=Applications\n"
    )
    if color:
        image = QImage(64, 64, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(QColor(color))
        for name in ICONS:
            assert image.save(str(icons / (name + ".png")))


def render_settings_icons():
    result = {}
    for name in ICONS:
        view = QQuickView()
        view.engine().addImageProvider("desktop", IconProvider())
        try:
            view.setInitialProperties({
                "option": {"title": "Menu option", "icon": name},
                "colors": {"text": "#efe7d8", "muted": "#b7beb7", "accent": "#e8cc9f",
                           "track": "#394b4d", "dialog": "#18201e"},
                "fontFamily": "sans-serif", "width": 640, "height": 60,
            })
            view.setSource(QUrl.fromLocalFile(str(ROW)))
            assert view.status() == QQuickView.Status.Ready, view.errors()
            view.show()
            QTest.qWait(30)
            icon = view.rootObject().findChild(QObject, "settingOptionIcon")
            ready = QQmlExpression(view.engine().rootContext(), icon, "status === 1")
            assert ready.evaluate()[0], (name, ready.error().toString())
            image = view.grabWindow().convertToFormat(QImage.Format.Format_RGBA8888)
            assert not image.isNull(), name
            result[name] = hashlib.sha256(bytes(image.constBits())).hexdigest()
        finally:
            view.close()
            delete(view)
    return result


def test_settings_artwork_does_not_change_when_a_desktop_theme_supplies_the_icons(qt_application, tmp_path):
    original = (QIcon.themeName(), QIcon.fallbackThemeName(), QIcon.themeSearchPaths())
    theme(tmp_path, "udeck-no-icons")
    theme(tmp_path, "udeck-red-icons", "#ff0000")
    theme(tmp_path, "udeck-blue-icons", "#0000ff")
    try:
        QIcon.setThemeSearchPaths([str(tmp_path)])
        QIcon.setFallbackThemeName("")
        QIcon.setThemeName("udeck-no-icons")
        assert not any(QIcon.hasThemeIcon(name) for name in ICONS)
        built_in = render_settings_icons()
        for name in ("udeck-red-icons", "udeck-blue-icons"):
            QIcon.setThemeName(name)
            assert all(QIcon.hasThemeIcon(icon) for icon in ICONS)
            assert render_settings_icons() == built_in
    finally:
        QIcon.setThemeSearchPaths(original[2])
        QIcon.setFallbackThemeName(original[1])
        QIcon.setThemeName(original[0])
