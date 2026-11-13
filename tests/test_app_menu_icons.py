"""Application settings keep their own artwork when desktop themes change."""

import hashlib
from pathlib import Path

import pytest
from PySide6.QtCore import QObject, QSize, QUrl
from PySide6.QtGui import QColor, QIcon, QImage
from PySide6.QtQml import QQmlExpression
from PySide6.QtQuick import QQuickView
from PySide6.QtTest import QTest
from shiboken6 import delete

from udeck.file_icons import FILE_ICON_PREFIX, ICON_SPECS
from udeck.icons import IconProvider
from udeck.menu_icons import SETTING_ARTWORK, SETTING_ICON_PREFIX

ICONS = ("audio-card", "media-playlist-repeat", "folder", "window-close", "zoom-in", "zoom-out")
ROW = Path(__file__).resolve().parents[1] / "src/udeck/qml/SettingsRow.qml"


def theme(directory, name, color=None, icons=ICONS):
    root = directory / name
    assets = root / "64x64/apps"
    assets.mkdir(parents=True)
    (root / "index.theme").write_text(
        f"[Icon Theme]\nName={name}\nDirectories=64x64/apps\n"
        "[64x64/apps]\nSize=64\nType=Fixed\nContext=Applications\n"
    )
    if color:
        image = QImage(64, 64, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(QColor(color))
        for icon in icons:
            assert image.save(str(assets / (icon + ".png")))


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


@pytest.mark.parametrize("dimension", [48, 80, 144])
def test_all_icon_requests_keep_their_artwork_across_desktop_themes(tmp_path, dimension):
    names = sorted(set(SETTING_ARTWORK) | set(ICONS) | {
        "go-home", "view-grid", "view-list-details", "folder-new", "text-x-generic",
        "application-x-executable", "firefox-esr", "utilities-terminal", "geany",
        "audio-x-generic", "video-x-generic", "image-x-generic", "package-x-generic",
        "user-home", "user-trash", "drive-harddisk", "drive-removable-media",
        "input-mouse", "applications-system", "media-playback-start", "media-playback-stop",
        "io.github.zhubby.uDeck.Video", "org.example.CustomApplication",
    })
    identifiers = (names + [FILE_ICON_PREFIX + category for category in ICON_SPECS]
                   + [SETTING_ICON_PREFIX + asset + "/#e8cc9f" for asset in set(SETTING_ARTWORK.values())]
                   + ["udeck-app-menu:" + name for name in names])
    original = (QIcon.themeName(), QIcon.fallbackThemeName(), QIcon.themeSearchPaths())
    theme(tmp_path, "udeck-no-icons", icons=names)
    theme(tmp_path, "udeck-red-icons", "#ff0000", names)
    theme(tmp_path, "udeck-blue-icons", "#0000ff", names)

    def fingerprints():
        provider = IconProvider()
        rendered = {}
        for identifier in identifiers:
            size = QSize()
            image = provider.requestImage(identifier, size, QSize(dimension, dimension))
            assert not image.isNull(), identifier
            assert size == QSize(dimension, dimension), identifier
            rendered[identifier] = hashlib.sha256(bytes(image.constBits())).hexdigest()
        return rendered

    try:
        QIcon.setThemeSearchPaths([str(tmp_path)])
        QIcon.setFallbackThemeName("")
        QIcon.setThemeName("udeck-no-icons")
        assert not any(QIcon.hasThemeIcon(name) for name in names)
        built_in = fingerprints()
        for name in ("udeck-red-icons", "udeck-blue-icons"):
            QIcon.setThemeName(name)
            assert all(QIcon.hasThemeIcon(icon) for icon in names)
            assert fingerprints() == built_in
    finally:
        QIcon.setThemeSearchPaths(original[2])
        QIcon.setFallbackThemeName(original[1])
        QIcon.setThemeName(original[0])


def test_explicit_application_image_is_loaded_without_an_icon_theme(tmp_path):
    asset = QImage(80, 80, QImage.Format.Format_ARGB32_Premultiplied)
    asset.fill(QColor("#a345f1"))
    path = tmp_path / "application icon.png"
    assert asset.save(str(path))
    rendered = IconProvider().requestImage(str(path), QSize(), QSize(80, 80))
    assert rendered.convertToFormat(asset.format()) == asset
    missing = IconProvider().requestImage(str(tmp_path / "missing.png"), QSize(), QSize(80, 80))
    assert not missing.isNull()
