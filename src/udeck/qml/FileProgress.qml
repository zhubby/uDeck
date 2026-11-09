import QtQuick
import QtQuick.Controls

ProgressBar {
    id: root
    required property var colors
    property bool reducedMotion: false
    padding: 0
    background: Rectangle { implicitHeight: 8; radius: 4; color: root.colors.track }
    contentItem: Item {
        implicitHeight: 8
        Rectangle {
            objectName: "fileProgressFill"
            width: parent.width * (root.indeterminate ? 0.25 : root.visualPosition)
            height: parent.height; radius: 4; color: root.colors.accent
            property real travel: 0.5
            x: root.indeterminate ? travel * (parent.width - width) : 0
            SequentialAnimation on travel {
                running: root.visible && root.indeterminate && !root.reducedMotion
                loops: Animation.Infinite
                NumberAnimation { from: 0; to: 1; duration: 850; easing.type: Easing.InOutSine }
                NumberAnimation { from: 1; to: 0; duration: 850; easing.type: Easing.InOutSine }
            }
        }
    }
}
