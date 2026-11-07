// SPDX-License-Identifier: GPL-2.0-or-later
import QtQuick
import QtQuick.Window

Image {
    objectName: "inputPromptIcon"
    property string keyId: ""
    property int iconSize: 32
    width: iconSize
    height: iconSize
    source: keyId ? Qt.resolvedUrl("../assets/input-prompts/" + keyId + ".png") : ""
    // Pre-filter PNGs at their physical display size. Software rendering does
    // not use mipmaps, so scaling the full-size texture leaves jagged edges.
    sourceSize: Qt.size(Math.ceil(width * Screen.devicePixelRatio),
                        Math.ceil(height * Screen.devicePixelRatio))
    fillMode: Image.PreserveAspectFit
    smooth: true
    mipmap: true
    Accessible.ignored: true
}
