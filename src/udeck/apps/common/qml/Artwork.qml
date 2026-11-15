// SPDX-License-Identifier: GPL-2.0-or-later
import QtQuick
Rectangle {
    id: art
    required property var colors
    required property string fontFamily
    property string cover: ""
    property string fallbackIcon: ""
    property string label: ""
    property string kind: "music"
    property bool iconOnly: false
    readonly property bool useFallbackIcon: kind === "emulator" && !iconOnly && coverImage.status !== Image.Ready
    radius: 7
    color: colors.artwork(kind)
    clip: true
    Rectangle { visible: !art.iconOnly && !art.useFallbackIcon; x: parent.width*0.58; y: -parent.height*0.1; width: parent.width*0.65; height: parent.height*1.2; rotation: 26; color: art.colors.artTint }
    Text { visible: !art.iconOnly && art.kind !== "emulator"; font.family: art.fontFamily; anchors.centerIn: parent; text: ({music:"♫",video:"▷",reader:"≡"})[art.kind] || "⌁"; color: art.colors.artText; font.pixelSize: Math.min(parent.width,parent.height)*0.4 }
    Image { objectName: "fallbackPlatformIcon"; anchors.fill: parent; anchors.margins: 14; source: art.fallbackIcon; fillMode: Image.PreserveAspectFit; asynchronous: true; sourceSize.width: 500; visible: art.useFallbackIcon && status === Image.Ready }
    Image { id: coverImage; objectName: art.iconOnly ? "platformIcon" : "coverImage"; anchors.fill: parent; anchors.margins: art.iconOnly ? 14 : 0; source: art.cover; fillMode: art.iconOnly || art.kind === "emulator" ? Image.PreserveAspectFit : Image.PreserveAspectCrop; asynchronous: true; sourceSize.width: 500; visible: status === Image.Ready }
}
