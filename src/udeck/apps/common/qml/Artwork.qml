// SPDX-License-Identifier: GPL-2.0-or-later
/*
[INPUT]: 依赖条目身份、规范化封面 URL、平台图标和主题。
[OUTPUT]: 提供身份隔离、同条目保留和异步封面交替。
[POS]: 图像双缓冲边界；迟到请求不改变当前条目。
[PROTOCOL]: Update this header on change, then check AGENTS.md
*/
import QtQuick
import "../../../qml" as Shared
Rectangle {
    id: art
    required property var colors
    required property string fontFamily
    property string identity: ""
    property string cover: ""
    property string fallbackIcon: ""
    property string label: ""
    property string kind: "music"
    property bool iconOnly: false
    readonly property url requestedSource: cover
    property bool reducedMotion: controller.reducedMotion
    property bool ready: false
    property int generation: 0
    property int activeBuffer: -1
    property int previousBuffer: -1
    property int pendingBuffer: -1
    property real blend: 1
    readonly property string contentIdentity: identity || cover
    readonly property string displayedIdentity: activeBuffer >= 0 ? imageAt(activeBuffer).requestIdentity : ""
    readonly property string displayedSource: activeBuffer >= 0 ? imageAt(activeBuffer).source.toString() : ""
    readonly property bool animating: reveal.running
    Shared.MotionTimings { id: motion; reducedMotion: art.reducedMotion }
    function imageAt(index) { return index === 0 ? first : second }
    function clearDisplay() {
        reveal.stop()
        activeBuffer = -1; previousBuffer = -1; blend = 1
    }
    function scheduleRequest() {
        if (ready) Qt.callLater(requestCover)
    }
    function cancelPending() {
        const index = pendingBuffer
        pendingBuffer = -1
        if (index >= 0 && index !== activeBuffer && index !== previousBuffer) {
            const image = imageAt(index)
            image.requestGeneration = -1
            image.source = ""
        }
    }
    function requestCover() {
        generation += 1
        cancelPending()
        if (!cover) { clearDisplay(); return }
        if (displayedIdentity !== contentIdentity) clearDisplay()
        if (displayedSource === requestedSource.toString()) return
        for (let index = 0; index < 2; index++) {
            const image = imageAt(index)
            if (image.status === Image.Ready && image.source.toString() === requestedSource.toString()) {
                image.requestIdentity = contentIdentity
                commit(index, true)
                return
            }
        }
        reveal.stop(); blend = 1; previousBuffer = -1
        const index = activeBuffer === 0 ? 1 : 0
        const image = imageAt(index)
        pendingBuffer = index
        image.requestGeneration = generation
        image.requestIdentity = contentIdentity
        image.source = cover
        if (image.status === Image.Ready) commit(index, true)
        else settle(index)
    }
    function settle(index) {
        const image = imageAt(index)
        if (pendingBuffer !== index || image.requestGeneration !== generation
                || image.requestIdentity !== contentIdentity || image.source.toString() !== requestedSource.toString()) return
        if (image.status === Image.Ready) commit(index, false)
        else if (image.status === Image.Error) pendingBuffer = -1
    }
    function commit(index, cached) {
        reveal.stop()
        previousBuffer = displayedIdentity === contentIdentity ? activeBuffer : -1
        activeBuffer = index; pendingBuffer = -1
        blend = reducedMotion || cached ? 1 : 0
        if (blend < 1) reveal.start()
        else previousBuffer = -1
    }
    onContentIdentityChanged: {
        generation += 1; cancelPending()
        if (displayedIdentity !== contentIdentity) clearDisplay()
        scheduleRequest()
    }
    onCoverChanged: scheduleRequest()
    onReducedMotionChanged: if (reducedMotion) { reveal.stop(); blend = 1; previousBuffer = -1 }
    Component.onCompleted: { ready = true; requestCover() }
    readonly property bool useFallbackIcon: kind === "emulator" && !iconOnly && (activeBuffer < 0 || blend < 1 && previousBuffer < 0)
    radius: 7
    color: colors.artwork(kind)
    clip: true
    Rectangle { visible: !art.iconOnly && !art.useFallbackIcon; x: parent.width*0.58; y: -parent.height*0.1; width: parent.width*0.65; height: parent.height*1.2; rotation: 26; color: art.colors.artTint }
    Text { visible: !art.iconOnly && art.kind !== "emulator"; font.family: art.fontFamily; anchors.centerIn: parent; text: ({music:"♫",video:"▷",reader:"≡"})[art.kind] || "⌁"; color: art.colors.artText; font.pixelSize: Math.min(parent.width,parent.height)*0.4 }
    Image { objectName: "fallbackPlatformIcon"; anchors.fill: parent; anchors.margins: 14; source: art.fallbackIcon; fillMode: Image.PreserveAspectFit; asynchronous: true; sourceSize.width: 500; visible: art.useFallbackIcon && status === Image.Ready; opacity: art.activeBuffer < 0 ? 1 : 1 - art.blend }
    Image {
        id: first
        objectName: art.activeBuffer <= 0 ? (art.iconOnly ? "platformIcon" : "coverImage") : "pendingCoverImage"
        property int requestGeneration: -1
        property string requestIdentity: ""
        anchors.fill: parent; anchors.margins: art.iconOnly ? 14 : 0
        fillMode: art.iconOnly || art.kind === "emulator" ? Image.PreserveAspectFit : Image.PreserveAspectCrop
        asynchronous: true; sourceSize.width: 500
        visible: status === Image.Ready && (art.activeBuffer === 0 || art.previousBuffer === 0)
        z: art.activeBuffer === 0 ? 1 : 0
        opacity: art.activeBuffer === 0 ? art.blend : 1
        onStatusChanged: art.settle(0)
    }
    Image {
        id: second
        objectName: art.activeBuffer === 1 ? (art.iconOnly ? "platformIcon" : "coverImage") : "pendingCoverImage"
        property int requestGeneration: -1
        property string requestIdentity: ""
        anchors.fill: parent; anchors.margins: art.iconOnly ? 14 : 0
        fillMode: art.iconOnly || art.kind === "emulator" ? Image.PreserveAspectFit : Image.PreserveAspectCrop
        asynchronous: true; sourceSize.width: 500
        visible: status === Image.Ready && (art.activeBuffer === 1 || art.previousBuffer === 1)
        z: art.activeBuffer === 1 ? 1 : 0
        opacity: art.activeBuffer === 1 ? art.blend : 1
        onStatusChanged: art.settle(1)
    }
    NumberAnimation {
        id: reveal; target: art; property: "blend"; from: 0; to: 1
        duration: motion.artwork; easing.type: Easing.OutCubic
        onFinished: art.previousBuffer = -1
    }
}
