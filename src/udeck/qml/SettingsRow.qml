// SPDX-License-Identifier: GPL-2.0-or-later
import QtQuick
import QtQuick.Controls

Rectangle {
    id: row
    objectName: "settingOptionRow"
    property var option: ({})
    property var colors
    property string fontFamily
    property int fontSize: 22
    property int minimumHeight: 60
    property bool selected: false
    property string onLabel: ""
    property string offLabel: ""
    readonly property bool singleLine: true
    readonly property bool toggle: typeof option.checked === "boolean"
    signal activated()

    implicitHeight: Math.max(minimumHeight, label.implicitHeight + 22)
    radius: 8
    color: selected ? colors.menuSelected : "transparent"
    border.width: selected ? 3 : 0
    border.color: colors.accent
    opacity: option.disabled ? 0.45 : 1
    Accessible.role: toggle ? Accessible.CheckBox : Accessible.Button
    Accessible.name: label.text + (status.text ? ", " + status.text : "")
    Accessible.checkable: toggle
    Accessible.checked: toggle && !!option.checked
    Accessible.onPressAction: if (!option.disabled) row.activated()

    Image {
        id: icon
        objectName: "settingOptionIcon"
        visible: !!row.option.icon
        x: 14; anchors.verticalCenter: parent.verticalCenter
        width: height; height: label.implicitHeight
        source: visible ? "image://desktop/" + encodeURIComponent(row.option.icon) : ""
        sourceSize: Qt.size(Math.ceil(width * 2), Math.ceil(height * 2))
    }
    Text {
        id: label
        objectName: "settingOptionLabel"
        x: icon.visible ? icon.x + icon.width + 14 : 14
        width: Math.max(0, parent.width - x - 14 - (controls.visible ? controls.width + 18 : 0))
        anchors.verticalCenter: parent.verticalCenter
        text: row.option.title || ""
        textFormat: Text.PlainText
        font.family: row.fontFamily; font.pixelSize: row.fontSize
        color: row.colors.text
        wrapMode: Text.NoWrap; maximumLineCount: 1; elide: Text.ElideRight
    }
    Row {
        id: controls
        objectName: "settingOptionControls"
        visible: !!status.text || row.toggle || !!row.option.navigate
        anchors.right: parent.right; anchors.rightMargin: 14
        anchors.verticalCenter: parent.verticalCenter
        spacing: 12
        Text {
            id: status
            objectName: "settingOptionStatus"
            visible: !!text
            width: Math.min(implicitWidth, Math.max(0, (row.width - label.x - 14) * 0.52
                - (row.toggle ? settingSwitch.width + 12 : row.option.navigate ? chevron.width + 12 : 0)))
            anchors.verticalCenter: parent.verticalCenter
            text: (row.option.current ? "✓ " : "") + (row.option.subtitle || (row.toggle ? (row.option.checked ? row.onLabel : row.offLabel) : ""))
            textFormat: Text.PlainText; horizontalAlignment: Text.AlignRight
            font.family: row.fontFamily; font.pixelSize: row.fontSize
            color: row.colors.muted
            wrapMode: Text.NoWrap; maximumLineCount: 1
            elide: row.option.path ? Text.ElideMiddle : Text.ElideRight
        }
        Rectangle {
            id: settingSwitch
            objectName: "settingOptionSwitch"
            visible: row.toggle
            property bool checked: !!row.option.checked
            anchors.verticalCenter: parent.verticalCenter
            width: 54; height: 30; radius: height / 2
            color: checked ? row.colors.accent : row.colors.track
            border.width: 1; border.color: checked ? row.colors.accent : row.colors.muted
            Rectangle {
                width: 22; height: 22; radius: height / 2
                anchors.verticalCenter: parent.verticalCenter
                x: settingSwitch.checked ? settingSwitch.width - width - 4 : 4
                color: settingSwitch.checked ? row.colors.dialog : row.colors.text
            }
        }
        Text {
            id: chevron
            objectName: "settingOptionChevron"
            visible: !!row.option.navigate && !row.toggle
            anchors.verticalCenter: parent.verticalCenter
            text: "›"; textFormat: Text.PlainText
            font.family: row.fontFamily; font.pixelSize: row.fontSize
            color: row.colors.muted
        }
    }
    MouseArea {
        id: mouse
        anchors.fill: parent; enabled: !row.option.disabled
        hoverEnabled: true
        onClicked: row.activated()
    }
    ToolTip.visible: mouse.containsMouse && (label.truncated || status.truncated)
    ToolTip.delay: 700
    ToolTip.text: label.text + (status.text ? "\n" + status.text : "")
}
