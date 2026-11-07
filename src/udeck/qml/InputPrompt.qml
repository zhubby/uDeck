// SPDX-License-Identifier: GPL-2.0-or-later
import QtQuick

Row {
    id: prompt
    required property string fontFamily
    required property color textColor
    property var keys: []
    property string label: ""
    property int iconSize: 32
    property int fontSize: 20
    spacing: 6
    layoutDirection: Qt.LeftToRight
    Accessible.role: Accessible.StaticText
    Accessible.name: keys.map(keyName).join(" ") + " " + label

    function keyName(key) {
        return key.replace("gamecube_button_color_", "GameCube ")
                  .replace("gamecube_button_", "GameCube ")
                  .replace("gamecube_trigger_", "GameCube ")
                  .replace("keyboard_", "").replace(/_/g, " ")
    }

    Repeater {
        model: prompt.keys
        delegate: Item {
            required property string modelData
            property bool separator: modelData === "+" || modelData === "/"
            width: separator ? separatorText.implicitWidth : prompt.iconSize
            height: prompt.iconSize
            InputIcon { visible: !parent.separator; keyId: parent.separator ? "" : parent.modelData; iconSize: prompt.iconSize }
            Text {
                id: separatorText
                visible: parent.separator
                anchors.centerIn: parent
                text: parent.modelData
                color: prompt.textColor
                font.family: prompt.fontFamily
                font.pixelSize: prompt.fontSize
                Accessible.ignored: true
            }
        }
    }
    Text {
        visible: text.length > 0
        anchors.verticalCenter: parent.verticalCenter
        text: prompt.label
        color: prompt.textColor
        font.family: prompt.fontFamily
        font.pixelSize: prompt.fontSize
        textFormat: Text.PlainText
        Accessible.ignored: true
    }
}
