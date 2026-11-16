// SPDX-License-Identifier: GPL-2.0-or-later
/*
[INPUT]: 依赖封面地址、平台图标、主题与减少动画开关。
[OUTPUT]: 提供异步封面淡入与加载期间的平台占位。
[POS]: 库卡片与内容视图共用的图像边界。
[PROTOCOL]: Update this header on change, then check AGENTS.md
*/
import QtQuick
import "../../../qml" as Shared
Rectangle {
    id: art
    required property var colors
    required property string fontFamily
    property string cover: ""
    property string fallbackIcon: ""
    property string label: ""
    property string kind: "music"
    property bool iconOnly: false
    property bool reducedMotion: controller.reducedMotion
    Shared.MotionTimings { id: motion; reducedMotion: art.reducedMotion }
    function revealCover() {
        reveal.stop()
        coverImage.opacity = 0
        if (coverImage.status === Image.Ready) {
            if (reducedMotion) coverImage.opacity = 1
            else reveal.start()
        }
    }
    onReducedMotionChanged: if (reducedMotion) { reveal.stop(); coverImage.opacity = coverImage.status === Image.Ready ? 1 : 0 }
    readonly property bool useFallbackIcon: kind === "emulator" && !iconOnly && (coverImage.status !== Image.Ready || coverImage.opacity < 1)
    radius: 7
    color: colors.artwork(kind)
    clip: true
    Rectangle { visible: !art.iconOnly && !art.useFallbackIcon; x: parent.width*0.58; y: -parent.height*0.1; width: parent.width*0.65; height: parent.height*1.2; rotation: 26; color: art.colors.artTint }
    Text { visible: !art.iconOnly && art.kind !== "emulator"; font.family: art.fontFamily; anchors.centerIn: parent; text: ({music:"♫",video:"▷",reader:"≡"})[art.kind] || "⌁"; color: art.colors.artText; font.pixelSize: Math.min(parent.width,parent.height)*0.4 }
    Image { objectName: "fallbackPlatformIcon"; anchors.fill: parent; anchors.margins: 14; source: art.fallbackIcon; fillMode: Image.PreserveAspectFit; asynchronous: true; sourceSize.width: 500; visible: art.useFallbackIcon && status === Image.Ready; opacity: coverImage.status === Image.Ready ? 1 - coverImage.opacity : 1 }
    Image { id: coverImage; objectName: art.iconOnly ? "platformIcon" : "coverImage"; anchors.fill: parent; anchors.margins: art.iconOnly ? 14 : 0; source: art.cover; fillMode: art.iconOnly || art.kind === "emulator" ? Image.PreserveAspectFit : Image.PreserveAspectCrop; asynchronous: true; sourceSize.width: 500; visible: status === Image.Ready; opacity: 0; onStatusChanged: art.revealCover() }
    NumberAnimation { id: reveal; target: coverImage; property: "opacity"; from: 0; to: 1; duration: motion.artwork; easing.type: Easing.OutCubic }
}
