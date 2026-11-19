/*
[INPUT]: 依赖显示状态、淡入开关、时长与减少动画开关。
[OUTPUT]: 提供可立即结束的淡入淡出和连续改向位移。
[POS]: 页面、提示与应用菜单共用的视觉容器。
[PROTOCOL]: Update this header on change, then check AGENTS.md
*/
import QtQuick

Item {
    id: root
    property bool shown: true
    property bool reducedMotion: false
    property bool fadeEnabled: true
    property int enterDuration: 140
    property int leaveDuration: 110
    property real enterX: 0
    property real enterY: 0
    property alias offsetX: shift.x
    property alias offsetY: shift.y
    property bool ready: false
    readonly property bool closing: !shown && visible
    signal hidden()
    visible: shown || opacity > 0
    opacity: shown ? 1 : 0
    transform: Translate { id: shift }
    function finish() {
        transition.stop()
        opacity = shown ? 1 : 0
        shift.x = shown ? 0 : enterX
        shift.y = shown ? 0 : enterY
        if (!shown) hidden()
    }
    function animate() {
        if (!ready) return
        transition.stop()
        if (reducedMotion) { finish(); return }
        fade.to = shown || !fadeEnabled ? 1 : 0
        moveX.to = shown ? 0 : enterX
        moveY.to = shown ? 0 : enterY
        fade.duration = shown ? enterDuration : leaveDuration
        moveX.duration = fade.duration; moveY.duration = fade.duration
        transition.start()
    }
    function replay(direction = 1) {
        if (reducedMotion || !shown) { finish(); return }
        const moving = transition.running
        transition.stop()
        if (!moving) {
            opacity = fadeEnabled ? 0 : 1
            shift.x = enterX * direction; shift.y = enterY
        }
        animate()
    }
    onShownChanged: animate()
    onReducedMotionChanged: if (reducedMotion) finish()
    Component.onCompleted: { ready = true; finish() }
    ParallelAnimation {
        id: transition
        NumberAnimation { id: fade; target: root; property: "opacity"; easing.type: Easing.OutCubic }
        NumberAnimation { id: moveX; target: shift; property: "x"; easing.type: Easing.OutCubic }
        NumberAnimation { id: moveY; target: shift; property: "y"; easing.type: Easing.OutCubic }
        onFinished: if (!root.shown) root.hidden()
    }
}
