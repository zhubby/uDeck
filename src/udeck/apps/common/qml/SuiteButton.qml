// SPDX-License-Identifier: GPL-2.0-or-later
/*
[INPUT]: 依赖共享主题、输入提示和调用方提供的图标。
[OUTPUT]: 提供有文字或图标的操作按钮及无障碍名称。
[POS]: 独立应用共用按钮；焦点状态由控制器提供。
[PROTOCOL]: Update this header on change, then check AGENTS.md
*/
import QtQuick
import QtQuick.Controls
import "../../../qml" as Shared
Rectangle {
    id: button
    required property var colors
    required property string fontFamily
    property string text: ""
    property var promptKeys: []
    property Component iconComponent
    property Component leadingIcon
    property bool compact: false
    property bool selected: false
    property bool disabled: false
    signal activated()
    implicitWidth: iconComponent ? 56 : labelRow.implicitWidth + (compact ? 28 : 36)
    implicitHeight: compact ? 38 : 52
    radius: 8
    color: selected ? button.colors.buttonSelected : button.colors.button
    border.width: selected ? 3 : 1
    border.color: selected ? button.colors.accent : button.colors.buttonBorder
    opacity: disabled ? 0.45 : 1
    Accessible.role: Accessible.Button
    Accessible.name: text
    Accessible.onPressAction: if (enabled && !disabled) activated()
    Row {
        id: labelRow
        visible: !button.iconComponent
        anchors.centerIn: parent
        spacing: 8
        Loader {
            visible: !!button.leadingIcon
            anchors.verticalCenter: parent.verticalCenter
            sourceComponent: button.leadingIcon
        }
        Shared.InputPrompt {
            anchors.verticalCenter: parent.verticalCenter
            keys: button.promptKeys
            label: button.text
            fontFamily: button.fontFamily
            textColor: button.colors.text
            fontSize: button.compact ? 16 : 20
            iconSize: button.compact ? 22 : 30
        }
    }
    Loader { anchors.centerIn: parent; sourceComponent: button.iconComponent }
    MouseArea {
        id: pointer
        anchors.fill: parent
        enabled: !button.disabled
        hoverEnabled: !!button.iconComponent
        onClicked: button.activated()
    }
    ToolTip.visible: !!iconComponent && pointer.containsMouse
    ToolTip.delay: 650
    ToolTip.text: text
}
