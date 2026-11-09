// SPDX-License-Identifier: GPL-2.0-or-later
import QtQuick
Rectangle {
    id: art
    required property var colors
    required property string fontFamily
    property string cover: ""
    property string label: ""
    property string kind: "music"
    radius: 7
    color: colors.artwork(kind)
    clip: true
    Rectangle { x: parent.width*0.58; y: -parent.height*0.1; width: parent.width*0.65; height: parent.height*1.2; rotation: 26; color: art.colors.artTint }
    Text { font.family: art.fontFamily; anchors.centerIn: parent; text: ({music:"♫",video:"▷",reader:"≡",emulator:"✚"})[art.kind] || "⌁"; color: art.colors.artText; font.pixelSize: Math.min(parent.width,parent.height)*0.4 }
    Image { anchors.fill: parent; source: art.cover; fillMode: Image.PreserveAspectCrop; asynchronous: true; sourceSize.width: 500; visible: status === Image.Ready }
}
