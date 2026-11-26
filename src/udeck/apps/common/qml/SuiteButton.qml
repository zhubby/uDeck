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
    property bool selected: false
    property bool disabled: false
    signal activated()
    implicitWidth: iconComponent ? 56 : label.implicitWidth + 36
    implicitHeight: 52
    radius: 8
    color: selected ? button.colors.buttonSelected : button.colors.button
    border.width: selected ? 3 : 1
    border.color: selected ? button.colors.accent : button.colors.buttonBorder
    opacity: disabled ? 0.45 : 1
    Accessible.role: Accessible.Button
    Accessible.name: text
    Accessible.onPressAction: if (!disabled) activated()
    Shared.InputPrompt { id: label; visible: !button.iconComponent; anchors.centerIn: parent; keys: button.promptKeys; label: button.text; fontFamily: button.fontFamily; textColor: button.colors.text; fontSize: 20; iconSize: 30 }
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
