// SPDX-License-Identifier: GPL-2.0-or-later
import QtQuick
import QtQuick.Window

Item {
    id: icon
    objectName: "inputPromptIcon"
    property string keyId: ""
    property int iconSize: 32
    // Normalize the visible height of wide keyboard caps to the square keys'
    // 96px artwork. Keep each PNG's proportions and transparent padding.
    readonly property real artworkScale: ({
        keyboard_ctrl: 96 / 72, keyboard_alt: 96 / 72, keyboard_tab: 96 / 72,
        keyboard_shift: 96 / 64, keyboard_space: 96 / 56, keyboard_arrows: 96 / 60
    })[keyId] || 1
    readonly property real pixelRatio: Screen.devicePixelRatio
    readonly property int canvasPixels: Math.ceil(iconSize * artworkScale * pixelRatio)
    readonly property real canvasSize: canvasPixels / pixelRatio
    readonly property url source: artwork.source
    readonly property int status: artwork.status
    implicitWidth: canvasSize
    implicitHeight: iconSize
    width: implicitWidth
    height: iconSize
    Accessible.ignored: true

    Image {
        id: artwork
        width: icon.canvasSize
        height: width
        y: Math.round((Math.round(icon.height * icon.pixelRatio) - icon.canvasPixels) / 2) / icon.pixelRatio
        source: icon.keyId ? Qt.resolvedUrl("../assets/input-prompts/" + icon.keyId + ".png") : ""
        // Pre-filter at physical display size, including the normalized caps.
        // The software renderer does not use mipmaps when shrinking images.
        sourceSize: Qt.size(icon.canvasPixels, icon.canvasPixels)
        fillMode: Image.PreserveAspectFit
        smooth: true
        mipmap: true
        Accessible.ignored: true
    }
}
