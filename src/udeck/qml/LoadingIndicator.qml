import QtQuick

Rectangle {
    id: track
    objectName: "loadingTrack"
    required property var colors
    property bool active: false
    property bool reducedMotion: false
    property real phase: 0.5
    readonly property bool animationRunning: motion.running
    width: 160
    height: 3
    radius: 1.5
    color: colors.track
    clip: true

    onActiveChanged: if (!active) phase = 0.5
    onReducedMotionChanged: if (reducedMotion) phase = 0.5

    Rectangle {
        objectName: "loadingSegment"
        width: 44
        height: track.height
        radius: track.radius
        x: (track.width - width) * track.phase
        color: track.colors.accent
    }

    SequentialAnimation {
        id: motion
        running: track.active && track.visible && !track.reducedMotion
        loops: Animation.Infinite
        NumberAnimation { target: track; property: "phase"; from: 0; to: 1; duration: 550; easing.type: Easing.InOutSine }
        NumberAnimation { target: track; property: "phase"; from: 1; to: 0; duration: 550; easing.type: Easing.InOutSine }
    }
}
