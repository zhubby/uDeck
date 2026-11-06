// SPDX-License-Identifier: GPL-2.0-or-later
import QtQuick
Rectangle {
    id: button
    property string text: ""
    property bool selected: false
    property bool disabled: false
    signal activated()
    implicitWidth: label.implicitWidth + 36
    implicitHeight: 52
    radius: 8
    color: selected ? "#3d3428" : "#292f31"
    border.width: selected ? 3 : 1
    border.color: selected ? "#edb866" : "#454b4b"
    opacity: disabled ? 0.45 : 1
    Text { id: label; anchors.centerIn: parent; text: button.text; color: "#f1eee7"; font.pixelSize: 20 }
    MouseArea { anchors.fill: parent; enabled: !button.disabled; onClicked: button.activated() }
}
