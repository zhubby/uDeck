/*
[INPUT]: 依赖提示文字、主题、字体与减少动画开关。
[OUTPUT]: 提供保留退出文字的短过渡提示。
[POS]: 桌面与独立应用共用的非交互提示视图。
[PROTOCOL]: Update this header on change, then check AGENTS.md
*/
import QtQuick

MotionItem {
    id: root
    required property var colors
    required property string fontFamily
    property string message: ""
    property string retainedMessage: ""
    property color surfaceColor: colors.toast
    property color textColor: colors.text
    property int fontSize: 22
    property int maximumLines: 4
    property real maximumWidth: parent ? parent.width - 60 : 1000
    MotionTimings { id: motion; reducedMotion: root.reducedMotion }
    shown: !!message
    enterDuration: motion.notice
    leaveDuration: motion.notice
    enterY: 4
    enabled: false
    width: Math.min(maximumWidth, label.implicitWidth + 36)
    height: label.implicitHeight + 24
    onMessageChanged: if (message) retainedMessage = message
    onHidden: if (!message) retainedMessage = ""
    Rectangle {
        anchors.fill: parent; radius: 8
        color: root.surfaceColor; border.color: root.colors.toastBorder
    }
    Text {
        id: label; objectName: "toastMessage"
        x: 18; y: 12; width: parent.width - 36
        text: root.message || root.retainedMessage; textFormat: Text.PlainText
        font.family: root.fontFamily; font.pixelSize: root.fontSize; color: root.textColor
        wrapMode: Text.Wrap; maximumLineCount: root.maximumLines; elide: Text.ElideRight
    }
}
