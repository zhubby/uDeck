/*
[INPUT]: 依赖模态选择、确认文案、主题和鼠标启用边界。
[OUTPUT]: 提供取消与确认按钮，并发出选中索引。
[POS]: Main 模态容器的双按钮布局，复用键盘选择状态。
[PROTOCOL]: Update this header on change, then check AGENTS.md
*/
import QtQuick

Row {
    id: root
    required property var labels
    required property var colors
    required property string fontFamily
    required property int index
    required property bool mouseEnabled
    signal chosen(int index)
    spacing: 14
    Repeater {
        model: root.labels
        delegate: Rectangle {
            id: button
            required property string modelData
            required property int index
            readonly property bool selected: root.index === index
            objectName: "modalConfirm-" + index
            width: (root.width - root.spacing) / 2; height: 58; radius: 8
            color: selected ? root.colors.buttonSelected : root.colors.button
            border.width: selected ? 3 : 1
            border.color: selected ? root.colors.accent : root.colors.buttonBorder
            Text {
                textFormat: Text.PlainText; anchors.centerIn: parent; text: button.modelData
                font.family: root.fontFamily; font.pixelSize: 25; color: root.colors.text
            }
            MouseArea {
                anchors.fill: parent; enabled: root.mouseEnabled; cursorShape: Qt.BlankCursor
                onClicked: root.chosen(button.index)
            }
        }
    }
}
