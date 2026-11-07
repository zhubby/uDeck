// SPDX-License-Identifier: GPL-2.0-or-later
import QtQuick
import "../../qml" as Shared
Rectangle {
    id: button
    required property var colors
    required property string fontFamily
    property string text: ""
    property var promptKeys: []
    property bool selected: false
    property bool disabled: false
    signal activated()
    implicitWidth: label.implicitWidth + 36
    implicitHeight: 52
    radius: 8
    color: selected ? button.colors.buttonSelected : button.colors.button
    border.width: selected ? 3 : 1
    border.color: selected ? button.colors.accent : button.colors.buttonBorder
    opacity: disabled ? 0.45 : 1
    Shared.InputPrompt { id: label; anchors.centerIn: parent; keys: button.promptKeys; label: button.text; fontFamily: button.fontFamily; textColor: button.colors.text; fontSize: 20; iconSize: 30 }
    MouseArea { anchors.fill: parent; enabled: !button.disabled; onClicked: button.activated() }
}
