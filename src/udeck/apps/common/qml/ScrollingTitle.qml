// SPDX-License-Identifier: GPL-2.0-or-later
import QtQuick

Item {
    id: title
    required property string fontFamily
    property string text: ""
    property color textColor: "white"
    property int pixelSize: 20
    property bool active: false
    property string resetKey: ""
    property real offset: 0
    property bool ready: false
    readonly property real overflow: Math.max(0, label.implicitWidth - width)
    readonly property bool scrolling: active && visible && overflow > 0
    implicitHeight: metrics.height
    clip: true

    function restart() {
        if (!ready) return
        scroll.stop()
        offset = 0
        if (scrolling) scroll.start()
    }
    onScrollingChanged: restart()
    onTextChanged: restart()
    onWidthChanged: restart()
    onOverflowChanged: restart()
    onResetKeyChanged: restart()
    Component.onCompleted: { ready = true; restart() }

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
        loops: Animation.Infinite
        PauseAnimation { duration: 1200 }
        NumberAnimation {
            target: title; property: "offset"
            from: 0; to: title.overflow
            duration: Math.max(1000, title.overflow * 1000 / 36)
        }
        PauseAnimation { duration: 1400 }
        PropertyAction { target: title; property: "offset"; value: 0 }
    }
}
