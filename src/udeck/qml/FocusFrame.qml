/*
[INPUT]: 依赖当前代理、主题颜色与减少动画开关。
[OUTPUT]: 提供可立即改向的单一焦点边框。
[POS]: 列表内容层的覆盖视图，不截获输入或改变布局。
[PROTOCOL]: Update this header on change, then check AGENTS.md
*/
import QtQuick

Rectangle {
    id: frame
    property Item target: null
    required property color accent
    property bool active: true
    property bool reducedMotion: false
    property real leftInset: 0
    property real topInset: 0
    property real rightInset: 0
    property real bottomInset: 0
    MotionTimings { id: motion; reducedMotion: frame.reducedMotion }
    readonly property real targetX: target ? target.x + leftInset : 0
    readonly property real targetY: target ? target.y + topInset : 0
    width: target ? Math.max(0, target.width - leftInset - rightInset) : 0
    height: target ? Math.max(0, target.height - topInset - bottomInset) : 0
    visible: active && !!target
    z: 3
    radius: 10
    color: "transparent"
    border.width: 3
    border.color: accent
    function position() {
        moveX.stop(); moveY.stop()
        if (!visible || reducedMotion) { x = targetX; y = targetY }
        else {
            moveX.to = targetX; moveY.to = targetY
            moveX.start(); moveY.start()
        }
    }
    onTargetXChanged: position()
    onTargetYChanged: position()
    onReducedMotionChanged: position()
    onVisibleChanged: position()
    Component.onCompleted: position()
    NumberAnimation {
        id: moveX; target: frame; property: "x"
        duration: motion.focus; easing.type: Easing.OutCubic
    }
    NumberAnimation {
        id: moveY; target: frame; property: "y"
        duration: motion.focus; easing.type: Easing.OutCubic
    }
}
