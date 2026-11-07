// SPDX-License-Identifier: GPL-2.0-or-later
import QtQuick

Image {
    objectName: "inputPromptIcon"
    property string keyId: ""
    property int iconSize: 32
    width: iconSize
    height: iconSize
    source: keyId ? Qt.resolvedUrl("../assets/input-prompts/" + keyId + ".png") : ""
    sourceSize: Qt.size(128, 128)
    fillMode: Image.PreserveAspectFit
    smooth: true
    mipmap: true
    Accessible.ignored: true
}
