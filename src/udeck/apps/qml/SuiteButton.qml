// SPDX-License-Identifier: GPL-2.0-or-later
import QtQuick
Rectangle {
    id: button
    required property var colors
    property string text: ""
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
    Text { id: label; anchors.centerIn: parent; text: button.text; color: button.colors.text; font.pixelSize: 20 }
    MouseArea { anchors.fill: parent; enabled: !button.disabled; onClicked: button.activated() }
}
