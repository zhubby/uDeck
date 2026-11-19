/*
[INPUT]: 依赖当前代理、视觉偏移、主题与减少动画开关。
[OUTPUT]: 提供位置和尺寸同轨改向的单一焦点边框。
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
    property real visualOffsetX: 0
    property real visualOffsetY: 0
    property bool followTargetMotion: false
    property real leftInset: 0
    property real topInset: 0
    property real rightInset: 0
    property real bottomInset: 0
    MotionTimings { id: motion; reducedMotion: frame.reducedMotion }
    readonly property real targetX: target ? target.x + visualOffsetX + leftInset : 0
    readonly property real targetY: target ? target.y + visualOffsetY + topInset : 0
    readonly property real targetWidth: target ? Math.max(0, target.width - leftInset - rightInset) : 0
    readonly property real targetHeight: target ? Math.max(0, target.height - topInset - bottomInset) : 0
    property bool positioned: false
    property bool ready: false
    visible: active && !!target
    z: 3
    radius: 10
    color: "transparent"
    border.width: 3
    border.color: accent
    function position() {
        if (!ready) return
        movement.stop()
        if (!visible || reducedMotion || !positioned || followTargetMotion) {
            x = targetX; y = targetY
            width = targetWidth; height = targetHeight
        }
        else if (Math.abs(x - targetX) > 0.01 || Math.abs(y - targetY) > 0.01
                || Math.abs(width - targetWidth) > 0.01 || Math.abs(height - targetHeight) > 0.01) {
            moveX.to = targetX; moveY.to = targetY
            resizeWidth.to = targetWidth; resizeHeight.to = targetHeight
            movement.start()
        }
        positioned = visible
    }
    onTargetXChanged: position()
    onTargetYChanged: position()
    onTargetWidthChanged: position()
    onTargetHeightChanged: position()
    onFollowTargetMotionChanged: position()
    onReducedMotionChanged: position()
    onVisibleChanged: position()
    Component.onCompleted: { ready = true; position() }
    ParallelAnimation {
        id: movement
        NumberAnimation { id: moveX; target: frame; property: "x"; duration: motion.focus; easing.type: Easing.OutCubic }
        NumberAnimation { id: moveY; target: frame; property: "y"; duration: motion.focus; easing.type: Easing.OutCubic }
        NumberAnimation { id: resizeWidth; target: frame; property: "width"; duration: motion.focus; easing.type: Easing.OutCubic }
        NumberAnimation { id: resizeHeight; target: frame; property: "height"; duration: motion.focus; easing.type: Easing.OutCubic }
    }
}
