/*
[INPUT]: 依赖 PointerCursor 状态、主题配色和减少动画开关。
[OUTPUT]: 绘制精确圆点、细外环和一次性释放反馈。
[POS]: 桌面与内置窗口共用的非交互指针层。
[PROTOCOL]: Update this header on change, then check AGENTS.md
*/
import QtQuick

Item {
    id: layer
    property QtObject cursor: null
    required property QtObject colors
    property bool reducedMotion: cursor !== null && cursor.reducedMotion
    readonly property bool shown: cursor !== null && cursor.visible
    readonly property bool pressed: cursor !== null && cursor.pressed
    opacity: shown ? 1 : 0
    visible: opacity > 0
    enabled: false
    MotionTimings { id: motion; reducedMotion: layer.reducedMotion }

    Behavior on opacity {
        enabled: !layer.reducedMotion
        NumberAnimation { id: fade; duration: layer.shown ? motion.enter : motion.leave; easing.type: Easing.OutCubic }
    }
    onShownChanged: if (!shown) { clickAnimation.stop(); pulse.opacity = 0 }
    onReducedMotionChanged: if (reducedMotion) {
        fade.complete(); dotScale.complete(); ringScale.complete()
        clickAnimation.stop(); pulse.opacity = 0
    }

    Rectangle {
        id: ring
        objectName: "pointerRing"
        x: layer.cursor ? layer.cursor.position.x - width / 2 : 0
        y: layer.cursor ? layer.cursor.position.y - height / 2 : 0
        width: 20; height: width; radius: width / 2
        color: "transparent"; border.width: 1; border.color: layer.colors.accent
        opacity: 0.65; antialiasing: true
        scale: layer.shown ? (layer.pressed ? 0.8 : 1) : 0.7
        Behavior on scale {
            enabled: !layer.reducedMotion
            NumberAnimation { id: ringScale; duration: motion.press; easing.type: Easing.OutCubic }
        }
    }
    Rectangle {
        id: pulse
        objectName: "pointerClickPulse"
        width: 26; height: width; radius: width / 2
        color: "transparent"; border.width: 1; border.color: layer.colors.accent
        opacity: 0; antialiasing: true
    }

    Rectangle {
        id: orb
        objectName: "pointerOrb"
        x: layer.cursor ? layer.cursor.position.x - width / 2 : 0
        y: layer.cursor ? layer.cursor.position.y - height / 2 : 0
        width: layer.cursor ? layer.cursor.diameter : 8
        height: width
        radius: width / 2
        color: "#ffffff"; border.width: 1; border.color: "#b3000000"
        antialiasing: true
        scale: layer.shown ? (layer.pressed ? 0.7 : 1) : 0.75
        Behavior on scale {
            enabled: !layer.reducedMotion
            NumberAnimation { id: dotScale; duration: motion.press; easing.type: Easing.OutCubic }
        }
    }
    ParallelAnimation {
        id: clickAnimation
        objectName: "pointerPulseAnimation"
        NumberAnimation { target: pulse; property: "scale"; from: 0.65; to: 1.5; duration: motion.enter + motion.press; easing.type: Easing.OutCubic }
        NumberAnimation { target: pulse; property: "opacity"; from: 0.55; to: 0; duration: motion.enter + motion.press }
        onStopped: pulse.opacity = 0
    }
    Connections {
        target: layer.cursor
        function onClicked(position) {
            if (!layer.shown || layer.reducedMotion) return
            pulse.x = position.x - pulse.width / 2
            pulse.y = position.y - pulse.height / 2
            clickAnimation.restart()
        }
    }
}
