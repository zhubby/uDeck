/*
[INPUT]: 依赖模态选择、确认文案、主题和鼠标启用边界。
[OUTPUT]: 提供带焦点短过渡的双按钮和选中索引。
[POS]: Main 模态容器的双按钮布局，复用键盘选择状态。
[PROTOCOL]: Update this header on change, then check AGENTS.md
*/
import QtQuick

Item {
    id: root
    required property var labels
    required property var colors
    required property string fontFamily
    required property int index
    required property bool mouseEnabled
    property bool reducedMotion: false
    signal chosen(int index)
    function syncActionFocus() { actionFocus.target = buttons.itemAt(root.index) }
    onIndexChanged: Qt.callLater(syncActionFocus)
    height: 58
    FocusFrame {
        id: actionFocus; active: root.visible
        accent: root.colors.accent; reducedMotion: root.reducedMotion; radius: 8
    }
    Row {
        width: parent.width; spacing: 14
        Repeater {
            id: buttons
            onItemAdded: function(index, item) { if (index === root.index) actionFocus.target = item }
            model: root.labels
            delegate: Rectangle {
                id: button
                required property string modelData
                required property int index
                readonly property bool selected: root.index === index
                objectName: "modalConfirm-" + index
                width: (root.width - 14) / 2; height: 58; radius: 8
                color: selected ? root.colors.buttonSelected : root.colors.button
                border.width: 1; border.color: root.colors.buttonBorder
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
}
