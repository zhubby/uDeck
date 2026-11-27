// SPDX-License-Identifier: GPL-2.0-or-later
/*
[INPUT]: 依赖选中身份、文字尺寸、前台状态与减少动画。
[OUTPUT]: 提供标题自然宽度与单次滚动；前台恢复保留完成状态。
[POS]: 选中卡片的主标题；次要文字保持静止。
[PROTOCOL]: Update this header on change, then check AGENTS.md
*/
import QtQuick

Item {
    id: title
    required property string fontFamily
    property string text: ""
    property color textColor: "white"
    property int pixelSize: 20
    property bool active: false
    property bool selected: active
    property bool reducedMotion: controller.reducedMotion
    property string resetKey: ""
    property real offset: 0
    property bool ready: false
    property bool completed: false
    readonly property real overflow: Math.max(0, label.implicitWidth - width)
    readonly property bool eligible: selected && active && visible && !reducedMotion && overflow > 0
    readonly property bool scrolling: eligible && !completed
    readonly property bool animating: scroll.running
    implicitWidth: label.implicitWidth
    implicitHeight: metrics.height
    clip: true

    function resume() {
        if (!ready) return
        scroll.stop()
        offset = 0
        if (eligible && !completed) scroll.start()
    }
    function scheduleResume() {
        if (!ready) return
        scroll.stop(); offset = 0
        Qt.callLater(resume)
    }
    function scheduleRestart() {
        if (!ready) return
        completed = false
        scheduleResume()
    }
    onEligibleChanged: scheduleResume()
    onSelectedChanged: scheduleRestart()
    onTextChanged: scheduleRestart()
    onWidthChanged: scheduleRestart()
    onOverflowChanged: scheduleRestart()
    onResetKeyChanged: scheduleRestart()
    Component.onCompleted: { ready = true; scheduleRestart() }

    FontMetrics { id: metrics; font.family: title.fontFamily; font.pixelSize: title.pixelSize }
    Text {
        id: label
        objectName: "cardTitleText"
        x: -title.offset
        width: title.scrolling ? implicitWidth : parent.width
        height: parent.height
        verticalAlignment: Text.AlignVCenter
        font.family: title.fontFamily
        font.pixelSize: title.pixelSize
        text: title.text.replace(/[\r\n\u2028\u2029]+/g, " ")
        textFormat: Text.PlainText
        color: title.textColor
        wrapMode: Text.NoWrap
        maximumLineCount: 1
        elide: Text.ElideRight
    }
    SequentialAnimation {
        id: scroll
        PauseAnimation { duration: 1200 }
        NumberAnimation {
            target: title; property: "offset"
            from: 0; to: title.overflow
            duration: Math.max(1, title.overflow * 1000 / 36)
        }
        PauseAnimation { duration: 1400 }
        NumberAnimation {
            target: title; property: "offset"; to: 0
            duration: Math.max(120, Math.min(360, title.overflow * 1000 / 180))
            easing.type: Easing.InOutCubic
        }
        onFinished: { title.offset = 0; title.completed = true }
    }
}
