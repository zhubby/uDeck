// SPDX-License-Identifier: GPL-2.0-or-later
import QtQuick

Flow {
    id: hintFlow
    required property string fontFamily
    required property color textColor
    property var hints: []
    property int iconSize: 32
    property int fontSize: 20
    property int horizontalSpacing: 16
    property int verticalSpacing: 4
    spacing: 0

    Repeater {
        model: hintFlow.hints
        delegate: Item {
            required property var modelData
            width: prompt.implicitWidth + hintFlow.horizontalSpacing
            height: prompt.implicitHeight + hintFlow.verticalSpacing
            InputPrompt {
                id: prompt
                keys: parent.modelData.keys
                label: parent.modelData.label
                fontFamily: hintFlow.fontFamily
                textColor: hintFlow.textColor
                iconSize: hintFlow.iconSize
                fontSize: hintFlow.fontSize
            }
        }
    }
}
